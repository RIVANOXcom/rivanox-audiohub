"""Interactive local Pi4 WAV session: terminal-only skip, status, stop, safety."""
import io
import signal
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
        self.sent_signals = []

    def send_signal(self, number):
        self.sent_signals.append(number)

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

    def test_quieter_level_follows_each_owned_track_and_is_not_persisted(self):
        observed = []
        def player(paths, *, max_minutes, stop, on_player,
                   session_deadline, notify, level):
            observed.append((paths[0], level))
            child = FakeChild()
            self.children.append(child)
            on_player(child)
            while not stop.wait(0.002):
                pass
            raise InterruptedError("test stop")
        with mock.patch.object(local_music, "music_sink_available",
                               return_value=True), \
             mock.patch.object(local_music.os, "geteuid", return_value=1000):
            commands = iter(["n", "q"])
            self.assertFalse(music_session.run_session(
                self.paths, max_minutes=1, read_command=lambda _: next(commands, None),
                playback=player, out=self.out.append, require_tty=False,
                level="quiet"))
        self.assertEqual(observed, [(self.paths[0], "quiet"),
                                    (self.paths[1], "quiet")])
        self.assertTrue(all(c.terminated for c in self.children))
        log = "\n".join(self.out)
        self.assertIn("QUIET stream level", log)
        self.assertNotIn("secret-title", log)
        self.assertNotIn(str(self.dir), log)

    def test_unsupported_interactive_level_is_rejected_before_audio_sink(self):
        with mock.patch.object(local_music, "music_sink_available") as sink:
            with self.assertRaises(ValueError):
                music_session.run_session(
                    self.paths, level="loud", require_tty=False,
                    out=self.out.append)
            sink.assert_not_called()

    def test_cli_interactive_quiet_level_reaches_session_only_after_play(self):
        with mock.patch.object(local_music.sys, "stdin",
                               mock.Mock(isatty=lambda: True)), \
             mock.patch.object(local_music.sys, "stdout",
                               mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_session, "run_session") as session, \
             mock.patch("builtins.print"):
            self.assertEqual(local_music.main([
                "--interactive", "--level", "soft", "--play",
                str(self.paths[0])]), 0)
            session.assert_called_once_with([str(self.paths[0])],
                                            max_minutes=15, level="soft")

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


    def test_replay_current_track_without_exposing_private_names(self):
        self.assertFalse(self.run_with(["r", "s", "q"]))
        self.assertEqual(self.played, [self.paths[0], self.paths[0]])
        self.assertTrue(all(x.terminated for x in self.children))
        display = "\n".join(self.out)
        self.assertIn("Replaying selected track", display)
        self.assertIn("Music track 1/2", display)
        self.assertNotIn("secret-title", display)
        self.assertNotIn(str(self.dir), display)

    def test_previous_track_from_second_goes_back_to_first(self):
        self.assertFalse(self.run_with(["n", "p", "q"]))
        self.assertEqual(self.played, [self.paths[0], self.paths[1], self.paths[0]])
        self.assertTrue(all(x.terminated for x in self.children))
        self.assertIn("Playing prior selected track", "\n".join(self.out))

    def test_previous_at_first_track_restarts_first_without_underflow(self):
        self.assertFalse(self.run_with(["p", "q"]))
        self.assertEqual(self.played, [self.paths[0], self.paths[0]])
        self.assertIn("replaying track 1", "\n".join(self.out))

    def test_direct_number_jumps_backwards_and_forwards_in_private_queue(self):
        third = self.dir / "private-third.wav"
        with wave.open(str(third), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(b"\x00\x01\x00\x02" * 80)
        selected = [self.paths[0], self.paths[1], third]
        self.assertFalse(self.run_with(["3", "1", "q"], paths=selected))
        self.assertEqual(self.played, [self.paths[0], third, self.paths[0]])
        self.assertTrue(all(x.terminated for x in self.children))
        output = "\n".join(self.out)
        self.assertIn("Jumping to selected queue track 3", output)
        self.assertIn("Jumping to selected queue track 1", output)
        self.assertNotIn("private-third", output)

    def test_invalid_jump_does_not_end_player_or_change_selection(self):
        self.assertFalse(self.run_with(["8", "9", "q"]))
        self.assertEqual(self.played, [self.paths[0]])
        output = "\n".join(self.out)
        self.assertIn("Track number outside this local queue", output)
        self.assertIn("Unknown local command", output)
        self.assertNotIn(str(self.paths[0]), output)

    def test_queue_overview_is_anonymous_and_marks_selected_track(self):
        self.assertFalse(self.run_with(["l", "n", "l", "q"]))
        summary = "\n".join(self.out)
        self.assertIn("Selected WAV queue: track 1/2", summary)
        self.assertIn("1*=00:01", summary)
        self.assertIn("2*=00:01", summary)
        self.assertIn("NOT live progress", summary)
        self.assertNotIn("secret-title", summary)
        self.assertNotIn(str(self.dir), summary)

    def test_command_decoder_accepts_navigation_but_never_echoes_garbage(self):
        with mock.patch.object(music_session.select, "select",
                               return_value=([1], [], [])):
            for command in ("p", "r", "l", "1", "8"):
                self.assertEqual(music_session.read_terminal_command(
                    stream=io.StringIO(command.upper() + "\n")), command)
            for garbage in ("10", "0", "\x1b[31m", "SECURE-CODE", "2,3"):
                self.assertEqual(music_session.read_terminal_command(
                    stream=io.StringIO(garbage + "\n")), "?")

    def test_invalid_queue_metadata_rejected_before_display(self):
        base = local_music.inspect_playlist(self.paths, max_minutes=1)
        self.assertRaises(ValueError, music_session.queue_message, base, 0)
        self.assertRaises(ValueError, music_session.queue_message, base, 3)
        bad = {**base, "tracks":[{"duration_ms":-5}, base["tracks"][1]]}
        self.assertRaises(ValueError, music_session.queue_message, bad, 1)



    def run_paused(self, commands):
        """Drive a session only after the worker owns an actual fake child."""
        commands = iter(commands)
        def read(_timeout):
            until = time.monotonic() + 2
            while not self.children and time.monotonic() < until:
                time.sleep(0.001)
            if not self.children:
                raise AssertionError("player was never spawned")
            return next(commands, None)
        with mock.patch.object(local_music, "music_sink_available",
                               return_value=True), \
             mock.patch.object(local_music.os, "geteuid", return_value=1000):
            return music_session.run_session(
                self.paths, max_minutes=1, read_command=read,
                playback=self.waiting_playback, out=self.out.append,
                require_tty=False)

    def test_pause_and_resume_signal_only_owned_child(self):
        self.assertFalse(self.run_paused(["u", "s", "u", "q"]))
        self.assertEqual(self.played, [self.paths[0]])
        self.assertEqual(self.children[0].sent_signals,
                         [signal.SIGSTOP, signal.SIGCONT])
        self.assertTrue(self.children[0].terminated)
        status = "\n".join(self.out)
        self.assertIn("PAUSED", status)
        self.assertIn("RESUMED", status)
        self.assertIn("PAUSED (owned player only)", status)
        self.assertNotIn("secret-title", status)
        self.assertNotIn(str(self.dir), status)

    def test_quit_while_paused_resumes_before_child_termination(self):
        self.assertFalse(self.run_paused(["u", "q"]))
        self.assertEqual(self.children[0].sent_signals,
                         [signal.SIGSTOP, signal.SIGCONT])
        self.assertTrue(self.children[0].terminated)
        self.assertNotIn("secret-title", "\n".join(self.out))

    def test_child_pause_signal_failure_does_not_claim_paused(self):
        class RejectPause(FakeChild):
            def send_signal(self, number):
                raise OSError("permission details /private/ignored.wav")

        def playback(paths, *, max_minutes, stop, on_player,
                     session_deadline, notify):
            child = RejectPause()
            self.children.append(child)
            on_player(child)
            while not stop.wait(0.002):
                pass
            raise InterruptedError("operator cancel")

        commands = iter(["u", "q"])
        def read(_timeout):
            until = time.monotonic() + 2
            while not self.children and time.monotonic() < until:
                time.sleep(0.001)
            return next(commands, None)
        with mock.patch.object(local_music, "music_sink_available", return_value=True), \
             mock.patch.object(local_music.os, "geteuid", return_value=1000):
            self.assertFalse(music_session.run_session(
                self.paths, max_minutes=1, read_command=read,
                playback=playback, out=self.out.append, require_tty=False))
        self.assertTrue(self.children[0].terminated)
        self.assertNotIn("permission details", "\n".join(self.out))
        self.assertNotIn("PAUSED; session", "\n".join(self.out))

    def test_pause_is_optional_and_regular_next_and_status_unchanged(self):
        self.assertFalse(self.run_with(["s", "n", "q"]))
        self.assertEqual(len(self.children), 2)
        self.assertTrue(all(not x.sent_signals for x in self.children))
        self.assertNotIn("PAUSED", "\n".join(self.out))
        self.assertIn("session remaining", "\n".join(self.out))

    def test_decoder_accepts_u_without_echoing_untrusted_input(self):
        with mock.patch.object(music_session.select, "select",
                               return_value=([1], [], [])):
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("U\n")), "u")
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("SECRET-WIFI-PASSPHRASE\n")), "?")

    def test_status_paused_is_explicit_and_keeps_wall_clock_deadline(self):
        text = music_session.status_message(
            2, 4, 100, 180, clock=lambda: 150, paused=True)
        self.assertIn("PAUSED (owned player only)", text)
        self.assertIn("session remaining 30 s", text)
        self.assertIn("Music track 2/4", text)
        self.assertNotIn("secret-title", text)
        self.assertNotIn("PAUSED", music_session.status_message(
            2, 4, 100, 180, clock=lambda: 150))


    def test_repeat_mode_cycles_only_defined_local_values(self):
        self.assertEqual(music_session.next_repeat_mode("off"), "track")
        self.assertEqual(music_session.next_repeat_mode("track"), "all")
        self.assertEqual(music_session.next_repeat_mode("all"), "off")
        for bad in ("ALL", "", "none", 0, True, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                music_session.next_repeat_mode(bad)

    def test_repeat_mode_key_decodes_without_echoing_private_commands(self):
        with mock.patch.object(music_session.select, "select",
                               return_value=([1], [], [])):
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("M\n")), "m")
            self.assertEqual(music_session.read_terminal_command(
                stream=io.StringIO("secret-access-token\n")), "?")

    def test_live_repeat_mode_is_visible_but_never_persisted_or_discloses_paths(self):
        self.assertFalse(self.run_with(["m", "s", "l", "m", "s",
                                        "m", "s", "q"]))
        text = "\n".join(self.out)
        self.assertIn("Local repeat mode: TRACK", text)
        self.assertIn("Local repeat mode: ALL", text)
        self.assertIn("Local repeat mode: OFF", text)
        self.assertIn("repeating track", text)
        self.assertIn("repeating all", text)
        self.assertNotIn(str(self.dir), text)
        self.assertNotIn("secret-title", text)
        self.assertTrue(all(child.terminated for child in self.children))
        self.out.clear()
        self.assertFalse(self.run_with(["s", "q"]))
        self.assertNotIn("repeating all", "\n".join(self.out))
        self.assertNotIn("repeating track", "\n".join(self.out))

    def test_repeat_modes_remain_in_bounded_status_and_private_queue(self):
        report = local_music.inspect_playlist(self.paths, max_minutes=1)
        text = music_session.queue_message(report, 1, repeat_mode="all")
        self.assertIn("Repeat: all", text)
        self.assertNotIn("secret-title", text)
        self.assertIn("repeating track", music_session.status_message(
            1, 2, 0, 60, clock=lambda: 30, repeat_mode="track"))
        for bad in ("random", 12, None):
            with self.subTest(bad=bad):
                self.assertRaises(ValueError, music_session.queue_message,
                                  report, 1, repeat_mode=bad)
                self.assertRaises(ValueError, music_session.status_message,
                                  1, 2, 0, 60, repeat_mode=bad)

    def test_repeat_track_restarts_after_natural_completion_and_quit_stops(self):
        first = threading.Event()
        release = threading.Event()
        played = []
        children = []
        def playback(paths, *, max_minutes, stop, session_deadline,
                     on_player, notify):
            played.append(paths[0])
            if len(played) == 1:
                first.set()
                if not release.wait(2):
                    raise RuntimeError("Test timed out before repeat command")
                return True
            child = FakeChild()
            children.append(child)
            on_player(child)
            while not stop.wait(.001):
                pass
            raise InterruptedError("test stop")
        reads = [0]
        def read(_timeout):
            self.assertTrue(first.wait(2))
            reads[0] += 1
            if reads[0] == 1:
                return "m"  # repeat current
            if reads[0] == 2:
                release.set()
                return None
            if len(played) < 2:
                return None
            return "q"
        with mock.patch.object(local_music, "music_sink_available", return_value=True), \
             mock.patch.object(local_music.os, "geteuid", return_value=1000):
            self.assertFalse(music_session.run_session(
                self.paths, max_minutes=1, read_command=read,
                playback=playback, out=self.out.append, require_tty=False))
        self.assertEqual(played, [self.paths[0], self.paths[0]])
        self.assertTrue(children[0].terminated)
        self.assertIn("Repeating current selected track", "\n".join(self.out))

    def test_repeat_all_wraps_after_last_track_but_never_skips_quit(self):
        first = threading.Event()
        release = threading.Event()
        played = []
        children = []
        def playback(paths, *, max_minutes, stop, session_deadline,
                     on_player, notify):
            played.append(paths[0])
            if len(played) == 1:
                first.set()
                if not release.wait(2):
                    raise RuntimeError("Test timed out before repeat command")
                return True
            if len(played) == 2:
                return True
            child = FakeChild()
            children.append(child)
            on_player(child)
            while not stop.wait(.001):
                pass
            raise InterruptedError("test stop")
        reads = [0]
        def read(_timeout):
            self.assertTrue(first.wait(2))
            reads[0] += 1
            if reads[0] in (1, 2):
                return "m"  # off -> track -> all
            if reads[0] == 3:
                release.set()
                return None
            if len(played) < 3:
                return None
            return "q"
        with mock.patch.object(local_music, "music_sink_available", return_value=True), \
             mock.patch.object(local_music.os, "geteuid", return_value=1000):
            self.assertFalse(music_session.run_session(
                self.paths, max_minutes=1, read_command=read,
                playback=playback, out=self.out.append, require_tty=False))
        self.assertEqual(played, [self.paths[0], self.paths[1], self.paths[0]])
        self.assertTrue(children[0].terminated)
        self.assertIn("Repeating selected queue", "\n".join(self.out))
        self.assertNotIn(str(self.dir), "\n".join(self.out))

    def test_repeat_does_not_remove_session_deadline(self):
        mode = music_session.next_repeat_mode("track")
        self.assertEqual(mode, "all")
        # The existing wall-clock deadline remains visible even when paused
        # or repeat is selected, and does not reset on a repeat.
        out = music_session.status_message(
            1, 2, 100.0, 130.0, clock=lambda: 129.1,
            paused=True, repeat_mode=mode)
        self.assertIn("session remaining 1 s", out)
        self.assertIn("repeating all", out)
        self.assertIn("PAUSED", out)


if __name__ == "__main__":
    unittest.main()
