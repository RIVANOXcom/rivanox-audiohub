"""Offline PC music preparation: no overwrites, no network, no source edits."""
import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import offline_wav_prep as prep


class FakeProcess:
    def __init__(self, audio, status=0, on_wait=None):
        self.stdout = io.BytesIO(audio)
        self.status = status
        self.on_wait = on_wait
        self.killed = False
    def wait(self, timeout=None):
        if self.on_wait:
            self.on_wait()
        return self.status
    def poll(self):
        return self.status
    def kill(self):
        self.killed = True


class OfflineWavPreparationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / 'private-original.flac'
        self.source.write_bytes(b'private-owned-audio-bytes')
        self.destination = self.root / 'new-private-export.wav'
        self.pcm = b'\x00\x01\x00\x02' * 480

    def test_readonly_preview_stays_private_without_ffmpeg_or_files(self):
        before = self.source.read_bytes()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), mock.patch.object(
                prep.subprocess, 'Popen') as p:
            self.assertEqual(prep.main(['--source', str(self.source),
                                        '--output', str(self.destination)]), 0)
            p.assert_not_called()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.destination.exists())
        self.assertNotIn('private-original', stdout.getvalue())
        self.assertNotIn(str(self.root), stdout.getvalue())
        self.assertIn('OFFLINE AUDIO PREVIEW', stdout.getvalue())

    def test_unused_wav_hint_suggests_new_filename_without_writes(self):
        before = self.source.read_bytes()
        first = prep.suggest_unused_wav(self.source)
        self.assertEqual(first, self.root / 'private-original-AudioHub.wav')
        self.assertFalse(first.exists())
        self.assertEqual(self.source.read_bytes(), before)
        # Never overwrite an existing suggestion; use a bounded suffix.
        first.write_bytes(b'already-existing-private-file')
        second = prep.suggest_unused_wav(self.source)
        self.assertEqual(second, self.root / 'private-original-AudioHub-2.wav')
        self.assertFalse(second.exists())
        prep._plan(self.source, second)
        self.assertEqual(first.read_bytes(), b'already-existing-private-file')
        self.assertFalse(self.destination.exists())

    def test_unused_wav_hint_rejects_unsafe_and_exhausted_sources(self):
        for invalid in ('private.mp3', self.root / 'unexpected.txt'):
            with self.subTest(path=str(invalid)), self.assertRaises(ValueError):
                prep.suggest_unused_wav(invalid)
        alias = self.root / 'linked.flac'
        try:
            alias.symlink_to(self.source)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(ValueError):
                prep.suggest_unused_wav(alias)
        for number in range(1, 101):
            suffix = '-AudioHub' if number == 1 else '-AudioHub-' + str(number)
            (self.root / ('private-original' + suffix + '.wav')).write_bytes(b'occupied')
        with self.assertRaises(ValueError):
            prep.suggest_unused_wav(self.source)
        self.assertFalse(self.destination.exists())

    def test_pcm16_wav_export_uses_only_private_ffmpeg_and_no_overwrite(self):
        old = self.source.read_bytes()
        captured = []
        def spawn(argv, **kw):
            captured.append((argv, kw))
            return FakeProcess(self.pcm)
        with mock.patch.object(prep.shutil, 'which', return_value='/usr/bin/ffmpeg'), \
             mock.patch.object(prep.subprocess, 'Popen', side_effect=spawn):
            result = prep._convert(self.source, self.destination)
        self.assertEqual(self.source.read_bytes(), old)
        self.assertEqual(result['duration_seconds'], 0.01)
        self.assertEqual(self.destination.stat().st_size, 44 + len(self.pcm))
        import os
        if os.name != "nt":
            self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256(self.destination.read_bytes()).hexdigest(), result['sha256'])
        with wave.open(str(self.destination), 'rb') as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (2,2,48000))
            self.assertEqual(w.readframes(480), self.pcm)
        self.assertEqual(captured[0][1]['shell'], False)
        self.assertIs(captured[0][1]['stdin'], subprocess.DEVNULL)
        self.assertIs(captured[0][1]['stderr'], subprocess.DEVNULL)
        self.assertEqual(captured[0][0][captured[0][0].index('-f')+1], 'flac')
        self.assertIn('-protocol_whitelist', captured[0][0])
        self.assertIn('file,pipe', captured[0][0])
        self.assertNotIn('-y', captured[0][0])
        with mock.patch.object(prep.subprocess, 'Popen') as p:
            with self.assertRaises(ValueError):
                prep._convert(self.source, self.destination)
            p.assert_not_called()
        self.assertEqual(self.source.read_bytes(), old)

    def test_refuse_unsafe_paths_before_any_ffmpeg(self):
        for input_path, output in [
            (self.source, self.source),
            (self.source, self.root / 'already.wav'),
            (self.source, Path('relative.wav')),
            (Path('private.mp3'), self.destination),
            (self.root/'private.txt', self.destination),
        ]:
            if str(output).endswith('already.wav'):
                output.write_bytes(b'existing')
            if str(input_path).endswith('private.txt'):
                input_path.write_bytes(b'some data')
            with self.subTest(input_path=input_path, output=output):
                with self.assertRaises(ValueError):
                    prep._plan(input_path, output)
        alias = self.root / 'secret-alias.flac'
        try:
            alias.symlink_to(self.source)
        except (OSError, NotImplementedError):
            # Unprivileged Windows may not allow making symlinks.
            pass
        else:
            with self.assertRaises(ValueError):
                prep._plan(alias, self.destination)
        self.assertFalse(self.destination.exists())

    def test_broken_decode_rejects_without_new_wav_or_source_mutation(self):
        before = self.source.read_bytes()
        for data, status in ((b'',1), (self.pcm,1), (self.pcm,0)):
            with self.subTest(code=status, length=len(data)):
                with mock.patch.object(prep.shutil, 'which', return_value='ffmpeg'):
                    with mock.patch.object(prep.subprocess, 'Popen',
                                           return_value=FakeProcess(data,status)):
                        if status == 0:
                            with mock.patch.object(prep, 'OUTPUT_BYTES_MAX', 100):
                                with self.assertRaises(ValueError):
                                    prep._convert(self.source, self.destination)
                        else:
                            with self.assertRaises(ValueError):
                                prep._convert(self.source, self.destination)
                self.assertEqual(self.source.read_bytes(), before)
                self.assertFalse(self.destination.exists())

    def test_cancel_and_noninteractive_convert_never_create_files(self):
        with mock.patch.object(prep.sys.stdin, 'isatty', return_value=False), \
             mock.patch.object(prep.subprocess, 'Popen') as p:
            self.assertEqual(prep.main(['--source',str(self.source),
                                        '--output',str(self.destination), '--convert']),2)
            p.assert_not_called()
        self.assertFalse(self.destination.exists())


    def test_offline_pc_readiness_is_anonymous_and_never_runs_codec(self):
        import importlib.util
        for present in (False, True):
            with self.subTest(ffmpeg_found=present), \
                 mock.patch.object(importlib.util, "find_spec", return_value=object()), \
                 mock.patch.object(prep.shutil, "which",
                                   return_value="ffmpeg.exe" if present else None), \
                 mock.patch.object(prep.subprocess, "Popen") as run:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(prep.main(["--check-local"]), 0)
                run.assert_not_called()
                self.assertIn("Tk file-picker library: DETECTED", out.getvalue())
                self.assertIn("FFmpeg on PATH: " + (
                    "DETECTED" if present else "NOT FOUND"), out.getvalue())
                self.assertNotIn(str(self.root), out.getvalue())
                self.assertFalse(self.destination.exists())
        with mock.patch.object(prep.subprocess, "Popen") as proc:
            with contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                prep.main(["--check-local", "--convert"])
            proc.assert_not_called()

    def test_read_only_wav_verify_cli_and_hash_without_decoder_or_edits(self):
        with wave.open(str(self.destination), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(48000)
            writer.writeframes(self.pcm)
        before = self.destination.read_bytes()
        with mock.patch.object(prep.subprocess, "Popen") as decoder:
            verified = prep.verify_local_wav(self.destination)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(prep.main(["--verify-wav", str(self.destination)]), 0)
            decoder.assert_not_called()
        self.assertEqual(verified["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(verified["bytes"], len(before))
        self.assertEqual(verified["duration_seconds"], 0.01)
        self.assertNotIn(str(self.destination), stdout.getvalue())
        self.assertEqual(self.destination.read_bytes(), before)

    def test_read_only_wav_verify_rejects_truncation_and_links(self):
        with wave.open(str(self.destination), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(48000)
            writer.writeframes(self.pcm)
        complete = self.destination.read_bytes()
        for invalid in (complete[:50], complete[:43], b"this is not WAV"):
            with self.subTest(size=len(invalid)):
                self.destination.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    prep.verify_local_wav(self.destination)
                self.assertEqual(self.destination.read_bytes(), invalid)
        self.destination.write_bytes(complete)
        with self.assertRaises(ValueError):
            prep.verify_local_wav(Path("relative.wav"))
        alias = self.root / "linked.wav"
        try:
            alias.symlink_to(self.destination)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(ValueError):
                prep.verify_local_wav(alias)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(prep.main(["--verify-wav",
                                        str(self.root / "absent.wav")]), 2)
            with self.assertRaises(SystemExit):
                prep.main(["--verify-wav", str(self.destination), "--convert"])
        self.assertEqual(self.destination.read_bytes(), complete)

    def test_gui_only_opt_in_and_never_autostarts_converter(self):
        with mock.patch.object(prep, "launch_gui", return_value=0) as gui, \
             mock.patch.object(prep, "_convert") as converter:
            self.assertEqual(prep.main(["--gui"]), 0)
            gui.assert_called_once_with()
            converter.assert_not_called()
        with mock.patch.object(prep, "launch_gui") as gui:
            for extra in (["--convert"], ["--source", str(self.source)],
                          ["--output", str(self.destination)]):
                with self.subTest(extra=extra), \
                     contextlib.redirect_stderr(io.StringIO()), \
                     self.assertRaises(SystemExit):
                    prep.main(["--gui", *extra])
            gui.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_gui_unavailable_refuses_without_mutating_original(self):
        untouched = self.source.read_bytes()
        with mock.patch.object(prep, "launch_gui", side_effect=RuntimeError("headless")), \
             mock.patch.object(prep.subprocess, "Popen") as converter, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(prep.main(["--gui"]), 2)
            converter.assert_not_called()
        self.assertEqual(self.source.read_bytes(), untouched)
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'external FFmpeg not installed on test host')
    def test_real_local_ffmpeg_mp3_flac_to_wav_when_available(self):
        source_wav = self.root / 'synthetic.wav'
        with wave.open(str(source_wav),'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b'\x00\x10\x00\x10' * 48000)
        for ext in ('.flac','.mp3'):
            with self.subTest(format=ext):
                encoded = self.root/('test-input'+ext)
                make = subprocess.run(['ffmpeg','-nostdin','-loglevel','error',
                                       '-i',str(source_wav),str(encoded)],
                                      capture_output=True,timeout=20)
                self.assertEqual(make.returncode,0)
                hash_before = hashlib.sha256(encoded.read_bytes()).hexdigest()
                dst = self.root/('encoded-'+ext[1:]+'.wav')
                out = prep._convert(encoded,dst)
                self.assertEqual(out['bytes'], dst.stat().st_size)
                self.assertEqual(hashlib.sha256(encoded.read_bytes()).hexdigest(),hash_before)
                with wave.open(str(dst),'rb') as w:
                    self.assertEqual((w.getnchannels(),w.getsampwidth(),w.getframerate()),(2,2,48000))
                    self.assertGreater(w.getnframes(),0)


if __name__ == '__main__':
    unittest.main()
