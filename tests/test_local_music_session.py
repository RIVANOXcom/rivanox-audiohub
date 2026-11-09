"""Interactive local Pi4 WAV session: terminal-only skip, status, stop, safety."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import local_music, music_session


class FakeChild:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.exit_code = None

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = -15

    def kill(self):
        self.killed = True
        self.exit_code = -9


class MusicSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.paths = [self.dir / "secret-title-1.wav",
                      self.dir / "secret-title-2.wav"]
        for path in self.paths:
            with wave.open(str(path), "wb") as track:
                track.setnchannels(2)
                track.setsampwidth(2)
                track.setframerate(48000)
                track.writeframes(b"\x00\x01\x00\x02" * 120)
        self.out = []
        self.children = []
        self.played = []

    def waiting_playback(self, paths, *, max_minutes, stop, on_player,
                         session_deadline, notify):
        self.played.append(paths[0])
        child = FakeChild()
        self.children.append(child)
        on_player(child)
        while not stop.wait(0.002):
            pass
        raise InterruptedError("stopped privately")

    def run_with(self, commands, *, paths=None, playback=None):
        commands = iter(commands)

        def read(_timeout):
            try:
                return next(commands)
            except StopIteration:
                return None
        with mock.patch.object(local_music, "music_sink_available", return_value=True), \
             mock.patch.object(local_music.os, "geteuid", return_value=1000):
            return music_session.run_session(
                self.paths if paths is None else paths,
                max_minutes=1, read_command=read,
                playback=self.waiting_playback if playback is None else playback,
                out=self.out.append, require_tty=False,
            )

    def test_explicit_quit_terminates_our_child_with_no_private_titles(self):
        self.assertFalse(self.run_with(["s", "h", "q"]))
        self.assertEqual(self.played, [self.paths[0]])
        self.assertTrue(self.children[0].terminated)
        report = "\n".join(self.out)
        self.assertIn("Music track 1/2", report)
        self.assertIn("session remaining", report)
        self.assertIn("status", report)
        self.assertIn("stopped by operator", report)
        self.assertNotIn("secret-title", report)
        self.assertNotIn(str(self.dir), report)

    def test_skip_stops_first_player_before_second_and_quit_stops_second(self):
        self.assertFalse(self.run_with(["n", "s", "q"]))
        self.assertEqual(self.played, self.paths)
        self.assertEqual(len(self.children), 2)
        self.assertTrue(all(child.terminated for child in self.children))
        text = "\n".join(self.out)
        self.assertIn("Track skipped", text)
        self.assertIn("Music track 2/2", text)

    def test_automatic_completion_plays_next_track_and_ends(self):
        def play(paths, **kwargs):
            self.played.append(paths[0])
            return True
        self.assertTrue(self.run_with([], playback=play))
        self.assertEqual(self.played, self.paths)
        text = "\n".join(self.out)
        self.assertIn("Track 1/2 finished", text)
        self.assertIn("Local music session ended", text)
        self.assertNotIn("secret-title", text)

    def test_failing_player_is_reported_without_private_identity(self):
        def play(paths, **kwargs):
            raise ValueError("private /secret-file.wav")
        with self.assertRaisesRegex(RuntimeError, "player failed") as context:
            self.run_with([], playback=play)
        self.assertNotIn("secret-file", str(context.exception))
        self.assertNotIn("secret-title", "\n".join(self.out))

    def test_root_and_missing_private_music_sink_refuse_before_spawning(self):
        with mock.patch.object(local_music.os, "geteuid", return_value=0), \
             mock.patch.object(local_music, "music_sink_available") as sink:
            with self.assertRaises(PermissionError):
                music_session.run_session(self.paths, out=self.out.append,
                                          require_tty=False)
            sink.assert_not_called()
        with mock.patch.object(local_music.os, "geteuid", return_value=1000), \
             mock.patch.object(local_music, "music_sink_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "sink unavailable"):
                music_session.run_session(self.paths, out=self.out.append,
                                          require_tty=False)
        self.assertEqual(self.played, [])

    def test_nonterminal_refuses_even_if_track_valid_and_play_enabled(self):
        with mock.patch.object(music_session.sys, "stdin",
                               mock.Mock(isatty=mock.Mock(return_value=False))), \
             mock.patch.object(music_session.sys, "stdout",
                               mock.Mock(isatty=mock.Mock(return_value=True))):
            with self.assertRaises(PermissionError):
                music_session.run_session(self.paths, out=self.out.append,
                                          playback=self.waiting_playback)
        self.assertEqual(self.played, [])

    def test_cli_needs_both_play_and_interactive_and_a_real_tty(self):
        with mock.patch("builtins.print") as output, \
             mock.patch.object(music_session, "run_session") as session:
            self.assertEqual(local_music.main(
                [str(self.paths[0]), "--interactive"]), 2)
            session.assert_not_called()
            self.assertNotIn("secret-title", str(output.call_args_list))
        with mock.patch.object(local_music.sys, "stdin",
                               mock.Mock(isatty=lambda: False)), \
             mock.patch.object(local_music.sys, "stdout",
                               mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_session, "run_session") as session:
            self.assertEqual(local_music.main(
                [str(self.paths[0]), "--interactive", "--play"]), 2)
            session.assert_not_called()

    def test_library_and_direct_paths_keep_preview_without_session(self):
        with mock.patch.object(local_music, "play_playlist") as old_play, \
             mock.patch.object(music_session, "run_session") as new_session, \
             mock.patch("builtins.print"):
            self.assertEqual(local_music.main([str(self.paths[0])]), 0)
            self.assertEqual(local_music.main([str(self.paths[0]), "--play"]), 0)
            new_session.assert_not_called()
            old_play.assert_called_once_with([str(self.paths[0])], max_minutes=15)

    def test_explicit_direct_and_library_interactive_pass_selected_paths(self):
        from audiohub import music_library
        with mock.patch.object(local_music.sys, "stdin",
                               mock.Mock(isatty=lambda: True)), \
             mock.patch.object(local_music.sys, "stdout",
                               mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_session, "run_session") as session, \
             mock.patch("builtins.print"):
            self.assertEqual(local_music.main([
                "--interactive", "--play", str(self.paths[0])]), 0)
            session.assert_called_with([str(self.paths[0])], max_minutes=15)
            self.assertEqual(local_music.main([
                "--interactive", "--play", "--library", str(self.dir),
                "--tracks", "2,1", "--minutes", "2"]), 0)
            self.assertEqual(session.call_args.args[0],
                             [self.paths[1], self.paths[0]])
            self.assertEqual(session.call_args.kwargs, {"max_minutes": 2})

    def test_terminal_command_input_is_bounded_unknown_and_eof_quits(self):
        with mock.patch.object(music_session.select, "select",
                               return_value=([1], [], [])):
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("N\n")), "n")
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("s\n")), "s")
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("PASSWORD-PRIVATE-KEY\n")), "?")
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("")), "q")
        with mock.patch.object(music_session.select, "select",
                               return_value=([], [], [])):
            self.assertIsNone(music_session.read_terminal_command(
                stream=io.StringIO("q\n")))
        with mock.patch.object(music_session.select, "select",
                               side_effect=OSError("unavailable tty")):
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("q\n")), "q")

    def test_running_session_limit_displays_only_aggregate_counts(self):
        msg = music_session.status_message(1, 4, 100, 160, clock=lambda:125.4)
        self.assertEqual(msg,
                         "Music track 1/4 | elapsed 25 s | session remaining 35 s"
                         " | local only; audio not physically verified.")
        self.assertNotIn("wav", msg)

    def test_original_player_waits_past_old_ten_second_poll_budget(self):
        from audiohub import local_music
        class DelayedPlayer:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.waits = 0
                self.exited = False
            def wait(self, timeout):
                self.waits += 1
                if self.waits <= 3:
                    raise subprocess.TimeoutExpired("pw-cat", timeout)
                self.exited = True
                return 0
            def poll(self):
                return 0 if self.exited else None
        player = DelayedPlayer()
        # Fake wait(0.25) timeouts complete without actual sleep.
        local_music._play_one(
            self.paths[0], local_music._open_wav(self.paths[0]),
            deadline=time.monotonic()+30, spawn=lambda *a, **kw:player)
        self.assertEqual(player.waits, 4)


if __name__ == "__main__":
    unittest.main()
