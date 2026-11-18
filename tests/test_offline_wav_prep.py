"""Offline PC music preparation: no overwrites, no network, no source edits."""
import contextlib
import hashlib
import io
import json
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

    def test_completed_wav_requires_final_readback_and_safe_failure_cleanup(self):
        original = self.source.read_bytes()
        inspect_final = prep.verify_local_wav
        with mock.patch.object(prep.shutil, 'which', return_value='ffmpeg'), \
             mock.patch.object(prep.subprocess, 'Popen',
                               side_effect=lambda *a, **k: FakeProcess(self.pcm)), \
             mock.patch.object(prep, 'verify_local_wav', wraps=inspect_final) as inspect:
            result = prep._convert(self.source, self.destination)
            inspect.assert_called_once_with(self.destination)
        self.assertEqual(result['sha256'], inspect_final(self.destination)['sha256'])
        self.destination.unlink()

        for failure in ('hash_mismatch', 'size_mismatch', 'unreadable'):
            with self.subTest(failure=failure):
                def bad_readback(path):
                    if failure == 'unreadable':
                        raise ValueError('Simulated damaged published WAV')
                    good = inspect_final(path)
                    if failure == 'hash_mismatch':
                        good['sha256'] = 'f' * 64
                    else:
                        good['bytes'] += 1
                    return good
                with mock.patch.object(prep.shutil, 'which', return_value='ffmpeg'), \
                     mock.patch.object(prep.subprocess, 'Popen',
                                       side_effect=lambda *a, **k: FakeProcess(self.pcm)), \
                     mock.patch.object(prep, 'verify_local_wav',
                                       side_effect=bad_readback):
                    with self.assertRaises(ValueError):
                        prep._convert(self.source, self.destination)
                self.assertFalse(self.destination.exists())
                self.assertEqual(self.source.read_bytes(), original)

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


    def test_local_wav_folder_checks_multiple_owned_tracks_without_writes(self):
        originals = {}
        for name in ("private-song-b.wav", "private-song-a.wav"):
            path = self.root / name
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                writer.writeframes(self.pcm)
            originals[name] = path.read_bytes()
        output = io.StringIO()
        with mock.patch.object(prep.subprocess, "Popen") as decoder, \
             contextlib.redirect_stdout(output):
            self.assertEqual(prep.main(["--verify-folder", str(self.root)]), 0)
            first = prep.verify_local_wav_folder(self.root)
            self.assertEqual(first, prep.verify_local_wav_folder(self.root))
            decoder.assert_not_called()
        self.assertEqual(first["files"], 2)
        self.assertEqual(first["bytes"], sum(map(len, originals.values())))
        self.assertIn(first["collection_sha256"], output.getvalue())
        self.assertNotIn("private-song", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())
        for name, before in originals.items():
            self.assertEqual((self.root / name).read_bytes(), before)

    def test_compare_two_private_wav_folders_matches_and_detects_differences(self):
        original = self.root / "first-private-copy"
        copied = self.root / "second-private-copy"
        original.mkdir()
        copied.mkdir()
        for folder, name, frames in (
                (original, "do-not-disclose-source.wav", self.pcm),
                (copied, "do-not-disclose-copy.wav", self.pcm)):
            with wave.open(str(folder / name), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                writer.writeframes(frames)
        original_path = next(original.glob("*.wav"))
        copied_path = next(copied.glob("*.wav"))
        original_bytes = original_path.read_bytes()
        copied_bytes = copied_path.read_bytes()
        with mock.patch.object(prep.subprocess, "Popen") as decoder:
            report = prep.compare_local_wav_folders(original, copied)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(prep.main(["--compare-folders", str(original),
                                            str(copied)]), 0)
            decoder.assert_not_called()
        self.assertTrue(report["matched"])
        self.assertEqual(report["source"]["files"], 1)
        self.assertIn("LOCAL WAV COPY MATCH", out.getvalue())
        self.assertNotIn(str(original), out.getvalue())
        self.assertNotIn("do-not-disclose", out.getvalue())
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(copied_path.read_bytes(), copied_bytes)

        # A valid different PCM payload is a clean nonmatching comparison,
        # not a damaged-file exception or a write to either original.
        with wave.open(str(copied_path), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(48000)
            writer.writeframes(b"\x01\x02\x03\x04" * 480)
        changed_bytes = copied_path.read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(prep.main(["--compare-folders", str(original),
                                        str(copied)]), 1)
        self.assertIn("LOCAL WAV COPY DIFFERS", out.getvalue())
        self.assertNotIn("do-not-disclose", out.getvalue())
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(copied_path.read_bytes(), changed_bytes)

    def test_copy_comparison_ignores_filename_order_and_preserves_duplicate_counts(self):
        first = self.root / "original-private"
        second = self.root / "renamed-private"
        first.mkdir()
        second.mkdir()
        sound_a = self.pcm
        sound_b = b"\x10\x20\x30\x40" * 480

        def write_wav(folder, name, frames):
            target = folder / name
            with wave.open(str(target), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                writer.writeframes(frames)
            return target

        a = write_wav(first, "a-original.wav", sound_a)
        b = write_wav(first, "b-original.wav", sound_b)
        # Filename sorting gives B,A on copy but A,B on source.
        other_b = write_wav(second, "a-copy-renamed.wav", sound_b)
        other_a = write_wav(second, "z-copy-renamed.wav", sound_a)
        first_bytes = {p.name: p.read_bytes() for p in (a, b)}
        copy_bytes = {p.name: p.read_bytes() for p in (other_b, other_a)}
        report = prep.compare_local_wav_folders(first, second)
        self.assertTrue(report["matched"])
        self.assertNotEqual(report["source"]["collection_sha256"],
                            report["copy"]["collection_sha256"])
        self.assertEqual(report["source"]["copy_content_sha256"],
                         report["copy"]["copy_content_sha256"])
        self.assertEqual(prep.main(["--compare-folders", str(first), str(second)]), 0)
        self.assertEqual({p.name: p.read_bytes() for p in (a, b)}, first_bytes)
        self.assertEqual({p.name: p.read_bytes() for p in (other_b, other_a)},
                         copy_bytes)

        # Same file count, but one missing track replaced by a duplicate:
        # a set-based checker would miss this, a multiset must refuse.
        write_wav(second, "a-copy-renamed.wav", sound_a)
        changed = prep.compare_local_wav_folders(first, second)
        self.assertFalse(changed["matched"])
        self.assertEqual(changed["source"]["files"], changed["copy"]["files"])
        self.assertEqual(prep.main(["--compare-folders", str(first), str(second)]), 1)
        self.assertEqual({p.name: p.read_bytes() for p in (a, b)}, first_bytes)

    def test_compare_wav_folders_refuses_same_folder_and_unsafe_copy(self):
        first = self.root / "original-folder"
        second = self.root / "copy-folder"
        first.mkdir()
        second.mkdir()
        with wave.open(str(first / "first.wav"), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(48000)
            writer.writeframes(self.pcm)
        with self.assertRaises(ValueError):
            prep.compare_local_wav_folders(first, first)
        (second / "bad.wav").write_bytes(b"not valid WAV data")
        with self.assertRaises(ValueError):
            prep.compare_local_wav_folders(first, second)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(prep.main(["--compare-folders", str(first),
                                        str(second)]), 2)
            with self.assertRaises(SystemExit):
                prep.main(["--compare-folders", str(first), str(second),
                           "--convert"])
        self.assertTrue((first / "first.wav").exists())
        self.assertEqual((second / "bad.wav").read_bytes(), b"not valid WAV data")

    def test_read_only_folder_progress_and_operator_cancel_do_not_change_wavs(self):
        import threading
        paths = []
        for name in ("private-one.wav", "private-two.wav"):
            target = self.root / name
            with wave.open(str(target), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                writer.writeframes(self.pcm)
            paths.append(target)
        old = [path.read_bytes() for path in paths]
        event = threading.Event()
        progress = []
        def ask_stop(done, total):
            progress.append((done, total))
            event.set()
        with self.assertRaises(prep.ScanCancelled):
            prep.verify_local_wav_folder(self.root, cancel=event, progress=ask_stop)
        self.assertEqual(progress, [(1, 2)])
        self.assertEqual([path.read_bytes() for path in paths], old)
        event.clear()
        progress.clear()
        result = prep.verify_local_wav_folder(
            self.root, cancel=event,
            progress=lambda done, total: progress.append((done, total)))
        self.assertEqual(result["files"], 2)
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertEqual([path.read_bytes() for path in paths], old)

    def test_wav_copy_scan_reports_only_anonymous_counts_and_cancel_phase(self):
        import threading
        original, copied = self.root / "original-only", self.root / "copy-only"
        original.mkdir()
        copied.mkdir()
        for folder, name in ((original, "secret-source.wav"),
                             (copied, "another-secret-name.wav")):
            with wave.open(str(folder / name), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                writer.writeframes(self.pcm)
        inputs = [next(folder.glob("*.wav")) for folder in (original, copied)]
        initial = [path.read_bytes() for path in inputs]
        phases = []
        event = threading.Event()
        report = prep.compare_local_wav_folders(
            original, copied, cancel=event,
            progress=lambda phase, done, total: phases.append(
                (phase, done, total)))
        self.assertTrue(report["matched"])
        self.assertEqual(phases, [("original", 1, 1), ("copy", 1, 1)])
        self.assertTrue(all("secret" not in repr(item) for item in phases))
        self.assertEqual([path.read_bytes() for path in inputs], initial)

        phases.clear()
        def stop_before_copy(phase, done, total):
            phases.append((phase, done, total))
            if phase == "original":
                event.set()
        with self.assertRaises(prep.ScanCancelled):
            prep.compare_local_wav_folders(
                original, copied, cancel=event, progress=stop_before_copy)
        self.assertEqual(phases, [("original", 1, 1)])
        self.assertEqual([path.read_bytes() for path in inputs], initial)

    def test_cancelled_wav_file_scan_rejects_before_any_hash_or_write(self):
        import threading
        with wave.open(str(self.destination), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(48000)
            writer.writeframes(self.pcm)
        original = self.destination.read_bytes()
        event = threading.Event()
        event.set()
        with mock.patch.object(prep.hashlib, "sha256") as hash_func:
            with self.assertRaises(prep.ScanCancelled):
                prep.verify_local_wav(self.destination, cancel=event)
            hash_func.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), original)

    def test_synthetic_offline_demo_works_from_cli_without_user_music_or_codecs(self):
        original = self.source.read_bytes()
        out = io.StringIO()
        with mock.patch.object(prep.subprocess, "Popen") as decoder, \
             mock.patch.object(prep.shutil, "which",
                               side_effect=AssertionError("No FFmpeg check in demo")), \
             contextlib.redirect_stdout(out):
            code = prep.main(["--demo"])
        self.assertEqual(code, 0)
        self.assertIn("SYNTHETIC WAV DEMO PASS: 2", out.getvalue())
        self.assertIn("DIFFERS", out.getvalue())
        self.assertIn("Stop", out.getvalue())
        self.assertNotIn("private-original", out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())
        decoder.assert_not_called()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.destination.exists())

    def test_synthetic_demo_only_creates_and_cleans_its_private_temp_folder(self):
        real_temp = tempfile.TemporaryDirectory
        used = []
        def capture_directory(*args, **kwargs):
            instance = real_temp(*args, **kwargs)
            used.append(instance.name)
            return instance
        with mock.patch.object(prep.tempfile, "TemporaryDirectory",
                               side_effect=capture_directory):
            report = prep.run_offline_wav_demo()
        self.assertEqual(report["tracks"], 2)
        self.assertTrue(report["match"])
        self.assertTrue(report["difference"])
        self.assertTrue(report["cancel"])
        self.assertIs(report["private_media_used"], False)
        self.assertEqual(len(used), 1)
        self.assertFalse(Path(used[0]).exists())
        self.assertEqual(self.source.read_bytes(), b'private-owned-audio-bytes')

    def test_synthetic_demo_rejects_false_match_and_does_not_claim_pass(self):
        fake = {"matched": False, "source": {"files": 2}}
        out = io.StringIO()
        with mock.patch.object(prep, "compare_local_wav_folders",
                               return_value=fake), \
             contextlib.redirect_stderr(out):
            self.assertEqual(prep.main(["--demo"]), 2)
        self.assertIn("SYNTHETIC WAV DEMO FAILED", out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertFalse(self.destination.exists())

    def test_synthetic_demo_disallows_combining_with_file_selection_or_gui(self):
        for incompatible in (
                ["--source", str(self.source)],
                ["--output", str(self.destination)],
                ["--gui"], ["--convert"], ["--verify-folder", str(self.root)],
                ["--compare-folders", str(self.root), str(self.root)],
                ["--check-local"]):
            with self.subTest(option=incompatible), \
                 mock.patch.object(prep, "run_offline_wav_demo") as demo, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    prep.main(["--demo", *incompatible])
                demo.assert_not_called()
        self.assertFalse(self.destination.exists())

    def _make_synthetic_portable_for_check(self, root):
        # Exercise the real manifest verifier without relying on GitHub
        # network, operator music files, or the packaging workflow.
        manifest = {
            "schema": "rivanox-audiohub-windows-portable-alpha/1",
            "classification": "UNVERIFIED_ALPHA_TEST_ONLY",
            "source_sha": "a" * 40,
            "hardware_verified": False,
            "public_release_ready": False,
            "source_files": {},
        }
        for name in sorted(prep.PORTABLE_CONTENT_FILES):
            target = root.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = ("synthetic package member:" + name).encode("ascii")
            target.write_bytes(payload)
            manifest["source_files"][name] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source_path": "example/" + name,
            }
        (root / "SOURCE-MANIFEST.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return manifest

    def test_portable_version_and_all_files_match_synthetic_manifest_readonly(self):
        portable = self.root / "extracted-Windows-ALPHA"
        portable.mkdir()
        manifest = self._make_synthetic_portable_for_check(portable)
        before = {
            name: (portable.joinpath(*name.split("/"))).read_bytes()
            for name in prep.PORTABLE_CONTENT_FILES
        }
        first = prep.inspect_local_portable_package(portable)
        self.assertEqual(first, {
            "source_sha": manifest["source_sha"],
            "files": len(prep.PORTABLE_CONTENT_FILES), "checked": True,
        })
        label = prep.inspect_local_portable_package(
            portable, verify_files=False)
        self.assertEqual(label["source_sha"], "a" * 40)
        self.assertIs(label["checked"], False)
        self.assertEqual({
            name: portable.joinpath(*name.split("/")).read_bytes()
            for name in prep.PORTABLE_CONTENT_FILES
        }, before)
        self.assertEqual(self.source.read_bytes(), b"private-owned-audio-bytes")

    def test_portable_integrity_rejects_changed_or_missing_member_and_manifest(self):
        portable = self.root / "unpacked-package"
        portable.mkdir()
        self._make_synthetic_portable_for_check(portable)
        member = portable / "audiohub" / "offline_wav_prep.py"
        original = member.read_bytes()
        member.write_bytes(original[:-1] + b"Z")
        with self.assertRaises(ValueError):
            prep.inspect_local_portable_package(portable)
        member.write_bytes(original)
        member.unlink()
        with self.assertRaises((ValueError, OSError)):
            prep.inspect_local_portable_package(portable)
        (portable / "SOURCE-MANIFEST.json").unlink()
        with self.assertRaises((ValueError, OSError)):
            prep.inspect_local_portable_package(portable)
        self.assertEqual(self.source.read_bytes(), b"private-owned-audio-bytes")

    def test_portable_verifier_refuses_renamed_missing_inventory_and_symlinks(self):
        portable = self.root / "incomplete-portable"
        portable.mkdir()
        manifest = self._make_synthetic_portable_for_check(portable)
        manifest["source_files"].pop("LICENSE")
        (portable / "SOURCE-MANIFEST.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            prep.inspect_local_portable_package(portable)
        # A linked package directory must be refused, not followed.
        link = self.root / "portable-link"
        try:
            link.symlink_to(portable, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(ValueError):
                prep.inspect_local_portable_package(link)

    def test_package_check_cli_reports_source_sha_and_refuses_mixed_actions(self):
        report = {"source_sha": "b" * 40, "files": 18, "checked": True}
        out = io.StringIO()
        with mock.patch.object(prep, "inspect_local_portable_package",
                               return_value=report) as inspector, \
             contextlib.redirect_stdout(out):
            self.assertEqual(prep.main(["--package-check"]), 0)
            inspector.assert_called_once_with()
        self.assertIn("LOCAL PORTABLE PACKAGE MATCH", out.getvalue())
        self.assertIn("b" * 40, out.getvalue())
        self.assertIn("SELF-CHECK ONLY", out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())
        with mock.patch.object(prep, "inspect_local_portable_package",
                               side_effect=ValueError("private path")) as inspector, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(prep.main(["--package-check"]), 2)
            inspector.assert_called_once_with()
        self.assertIn("LOCAL PORTABLE PACKAGE REFUSED", errors.getvalue())
        self.assertNotIn("private path", errors.getvalue())
        for incompatible in (["--gui"], ["--demo"],
                             ["--source", str(self.source)],
                             ["--output", str(self.destination)],
                             ["--check-local"], ["--convert"],
                             ["--verify-folder", str(self.root)],
                             ["--verify-wav", str(self.destination)],
                             ["--compare-folders", str(self.root), str(self.root)]):
            with self.subTest(incompatible=incompatible), \
                 mock.patch.object(prep, "inspect_local_portable_package") as inspector, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    prep.main(["--package-check", *incompatible])
                inspector.assert_not_called()

    def test_local_wav_folder_rejects_corrupt_links_empty_and_excess(self):
        with self.assertRaises(ValueError):
            prep.verify_local_wav_folder(self.root)
        bad = self.root / "private-bad.wav"
        bad.write_bytes(b"not-a-wav")
        with self.assertRaises(ValueError):
            prep.verify_local_wav_folder(self.root)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(prep.main(["--verify-folder", str(self.root)]), 2)
            with self.assertRaises(SystemExit):
                prep.main(["--verify-folder", str(self.root), "--convert"])
        bad.unlink()
        good = self.root / "valid.wav"
        with wave.open(str(good), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(48000)
            writer.writeframes(self.pcm)
        alias = self.root / "private-linked.wav"
        try:
            alias.symlink_to(good)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(ValueError):
                prep.verify_local_wav_folder(self.root)
            alias.unlink()
        for index in range(40):
            (self.root / ("extra-" + str(index) + ".wav")).write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            prep.verify_local_wav_folder(self.root)
        self.assertEqual(good.read_bytes()[:4], b"RIFF")

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
