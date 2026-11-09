"""User-facing local WAV playback: manual opt-in, fixed music sink and bounded input."""
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import local_music


class CapturedSink(io.BytesIO):
    def close(self):
        # Observe the sent PCM after the playback protocol closes its pipe.
        self.saved = self.getvalue()
        super().close()


class FakePlayer:
    def __init__(self, code=0):
        self.stdin = CapturedSink()
        self.code = code
        self.waited = False
        self.terminated = False

    def wait(self, timeout=None):
        self.waited = True
        return self.code

    def poll(self):
        return self.code if self.waited else None

    def terminate(self):
        self.terminated = True
        self.waited = True

    def kill(self):
        self.terminated = True
        self.waited = True


class LocalMusicTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.wav = self.root / "one.wav"
        self.samples = b"\x01\x02\x03\x04" * 120
        self.make_wav(self.wav, self.samples)
        self.events = []
        self.players = []

    def make_wav(self, path, data, *, channels=2, rate=48000, width=2):
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(channels)
            stream.setsampwidth(width)
            stream.setframerate(rate)
            stream.writeframes(data)

    def captured_graph(self, name="audiohub.music"):
        raw = json.dumps([{
            "type":"PipeWire:Interface:Node","id":17,
            "info":{"props":{"media.class":"Audio/Sink","node.name":name}}
        }])
        return mock.Mock(returncode=0, stdout=raw)

    def capture(self, argv, **kwargs):
        self.events.append(("capture", argv, kwargs))
        return self.captured_graph()

    def spawn(self, argv, **kwargs):
        self.events.append(("spawn", argv, kwargs))
        proc = FakePlayer()
        self.players.append(proc)
        return proc

    def test_preview_reads_wav_but_never_opens_pipewire(self):
        with mock.patch.object(local_music.subprocess, "Popen") as popen, \
             mock.patch.object(local_music, "bounded_command_output") as capture:
            snapshot = local_music.inspect_playlist([self.wav], max_minutes=1)
            popen.assert_not_called()
            capture.assert_not_called()
        self.assertEqual(snapshot["input_slot"], "music")
        self.assertEqual(snapshot["files"], 1)
        self.assertFalse(snapshot["playback_started"])
        self.assertFalse(snapshot["audible_sound_verified"])
        self.assertFalse(snapshot["release_ready"])
        self.assertEqual(snapshot["tracks"][0]["channels"], 2)
        self.assertEqual(snapshot["tracks"][0]["duration_ms"], 3)
        self.assertNotIn(str(self.wav), repr(snapshot))
        self.assertNotIn("one.wav", repr(snapshot))
        self.assertFalse((self.root / "report.json").exists())

    def test_explicit_play_only_with_private_exact_music_target(self):
        with mock.patch.object(local_music.os, "geteuid", return_value=1000):
            self.assertTrue(local_music.play_playlist(
                [self.wav], max_minutes=1, spawn=self.spawn,
                capture=self.capture, notify=lambda text: self.events.append(("message", text))))
        self.assertEqual(self.players[0].stdin.saved, self.samples)
        self.assertTrue(self.players[0].waited)
        self.assertEqual(self.events[0][0], "capture")
        self.assertEqual(self.events[0][1], ["pw-dump"])
        spawn = next(x for x in self.events if x[0] == "spawn")
        self.assertEqual(spawn[1], [
            "pw-cat", "--playback", "--raw", "--target=audiohub.music",
            "--rate=48000", "--channels=2", "--format=s16",
            "--volume=0.20", "-"
        ])
        self.assertIs(spawn[2]["shell"], False)
        self.assertIs(spawn[2]["stderr"], local_music.subprocess.DEVNULL)
        self.assertTrue(spawn[2]["start_new_session"])
        text = repr(self.events)
        self.assertNotIn("one.wav", text)
        self.assertNotIn(str(self.root), text)

    def test_two_track_playlist_played_in_order(self):
        second = self.root / "two.wav"
        self.make_wav(second, b"\x05\x06\x07\x08" * 50)
        with mock.patch.object(local_music.os, "geteuid", return_value=1000):
            self.assertTrue(local_music.play_playlist(
                [self.wav, second], max_minutes=1, spawn=self.spawn,
                capture=self.capture, notify=lambda _: None))
        self.assertEqual(len(self.players), 2)
        self.assertEqual([p.stdin.saved for p in self.players],
                         [self.samples, b"\x05\x06\x07\x08" * 50])

    def test_no_target_fails_without_fallback_or_spawn(self):
        def missing(*args, **kwargs):
            return self.captured_graph("not-audiohub.music")
        with mock.patch.object(local_music.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "music sink unavailable"):
                local_music.play_playlist([self.wav], max_minutes=1,
                                          spawn=self.spawn, capture=missing)
        self.assertFalse(self.players)

    def test_root_is_not_allowed_to_play(self):
        with mock.patch.object(local_music.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                local_music.play_playlist([self.wav], spawn=self.spawn,
                                          capture=self.capture)
        self.assertFalse(self.events)

    def test_manual_cancel_terminates_spawned_player(self):
        stop = mock.Mock(is_set=mock.Mock(return_value=True))
        with mock.patch.object(local_music.os, "geteuid", return_value=1000):
            with self.assertRaises(InterruptedError):
                local_music.play_playlist(
                    [self.wav], max_minutes=1, spawn=self.spawn,
                    capture=self.capture, stop=stop, notify=lambda _: None)
        self.assertTrue(self.players[0].terminated)
        self.assertTrue(self.players[0].stdin.closed)

    def test_failed_pipewire_player_stops_queue(self):
        def spawn(*args, **kwargs):
            proc = FakePlayer(17)
            self.players.append(proc)
            return proc
        with mock.patch.object(local_music.os, "geteuid", return_value=1000):
            with self.assertRaises(RuntimeError):
                local_music.play_playlist([self.wav], max_minutes=1,
                                          spawn=spawn, capture=self.capture)
        self.assertEqual(len(self.players), 1)

    def test_symlinks_fifo_and_bad_paths_rejected_before_pipewire(self):
        alias = self.root / "alias.wav"
        alias.symlink_to(self.wav)
        for path in (alias, Path("relative.wav"), self.root / "missing.wav",
                     self.root / "../sneaky.wav", self.root / "song.mp3"):
            with self.subTest(path=str(path)):
                with self.assertRaises((ValueError, OSError)):
                    local_music.inspect_playlist([path])
        if hasattr(os, "mkfifo"):
            fifo = self.root / "fifo.wav"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                local_music.inspect_playlist([fifo])

    def test_bad_formats_and_world_writable_file_rejected(self):
        for channels, rate, width in ((3,48000,2),(2,500,2),(2,48000,1)):
            bad = self.root / ("bad" + str(channels) + str(rate) + str(width) + ".wav")
            self.make_wav(bad, self.samples, channels=channels,rate=rate,width=width)
            with self.assertRaises(ValueError):
                local_music.inspect_playlist([bad])
        bad = self.root / "truncated.wav"
        self.make_wav(bad,self.samples)
        raw = bad.read_bytes()
        bad.write_bytes(raw[:55])
        with self.assertRaises(ValueError):
            local_music.inspect_playlist([bad])
        self.wav.chmod(0o666)
        with self.assertRaises(ValueError):
            local_music.inspect_playlist([self.wav])

    def test_playlist_and_session_caps(self):
        for paths, limit in (([],1),([self.wav]*9,1),([self.wav],0),([self.wav],31)):
            with self.assertRaises(ValueError):
                local_music.inspect_playlist(paths,max_minutes=limit)
        big = self.root / "long.wav"
        # 48k mono x 61 seconds: under size limit but > 1 minute.
        self.make_wav(big, b"\x00\x00" * (48000*61), channels=1)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            local_music.inspect_playlist([big],max_minutes=1)

    def test_cli_default_is_inspect_only_and_errors_redacted(self):
        with mock.patch.object(local_music, "play_playlist") as play, \
             mock.patch("builtins.print") as output:
            self.assertEqual(local_music.main([str(self.wav)]),0)
            play.assert_not_called()
            self.assertIn("no playback yet", output.call_args_list[0].args[0])
        with mock.patch.object(local_music, "play_playlist",
                               side_effect=RuntimeError("SECRET PATH /private")), \
             mock.patch("builtins.print") as output:
            self.assertEqual(local_music.main([str(self.wav),"--play"]),2)
            self.assertNotIn("SECRET PATH",str(output.call_args_list))
            self.assertNotIn(str(self.wav),str(output.call_args_list))


if __name__ == "__main__":
    unittest.main()
