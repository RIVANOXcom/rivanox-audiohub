"""Offline Pi4 music-library picker: real local files, no playback until opt-in."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
import wave
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import local_music, music_library

# Preserve the real implementation for unit tests while legacy guided-picker
# tests have a deterministic always-ready simulator for absent Pi hardware.
REAL_GUIDED_ALBUM_PREFLIGHT = music_library.guided_playback_readiness


class LocalMusicLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "Private Music"
        self.root.mkdir(mode=0o700)
        self.b = self.root / "B favorite.wav"
        self.a = self.root / "a demo.wav"
        self.make_wav(self.b, 200)
        self.make_wav(self.a, 100)
        # Existing picker tests exercise album choices, not real Pi hardware.
        # The new prerequisite helper gets separate positive/negative tests.
        readiness = mock.patch.object(music_library, "guided_playback_readiness",
                                      return_value=True)
        readiness.start()
        self.addCleanup(readiness.stop)

    def make_wav(self, target, frames):
        with wave.open(str(target), "wb") as track:
            track.setnchannels(2)
            track.setsampwidth(2)
            track.setframerate(48000)
            track.writeframes(b"\x00\x01\x00\x01" * frames)

    def test_sorted_numbered_library_no_private_names_by_default(self):
        records, omitted = music_library.discover_library(self.root)
        self.assertEqual(omitted, 0)
        self.assertEqual([p for p, _ in records], [self.a, self.b])
        result = music_library.display_library(records)
        self.assertIn("Track 1", result)
        self.assertIn("Track 2", result)
        self.assertIn("stereo", result)
        self.assertIn("Names hidden", result)
        self.assertIn("then add --play only when ready.", result)
        self.assertNotIn(self.root.name, result)
        self.assertNotIn(self.a.name, result)
        self.assertNotIn(self.b.name, result)
        self.assertNotIn(str(self.root), result)
        self.assertNotIn("path", result.lower())
        self.assertFalse((self.root / "playlist.json").exists())

    def test_title_display_only_when_explicit_sanitized(self):
        bad = self.root / "\x1b[31mSecret.wav"
        self.make_wav(bad, 100)
        records, _ = music_library.discover_library(self.root)
        safe = music_library.display_library(records, show_titles=True)
        self.assertNotIn("\x1b", safe)
        self.assertNotIn("[31mSecret", safe)
        self.assertNotIn(str(self.root), safe)
        self.assertIn("a demo", safe)
        self.assertIn("B favorite", safe)
        self.assertIn("THIS local terminal", safe)
        private = music_library.display_library(records)
        self.assertNotIn("Secret", private)
        self.assertNotIn("favorite", private)

    def test_explicit_selection_bounds_and_order(self):
        items, _ = music_library.discover_library(self.root)
        paths, report = music_library.selected_paths(items, "2,1", max_minutes=1)
        self.assertEqual(paths, [self.b, self.a])
        self.assertEqual(report["files"], 2)
        self.assertEqual(report["input_slot"], "music")
        self.assertFalse(report["playback_started"])
        self.assertNotIn(str(self.root), repr(report))
        for bad in ("", "0", "3", "1,1", "1,,2", "  ", "1,2,3",
                    "1,💿", "-1", "+1", "01", "1.", "1;2", "9"*70):
            with self.subTest(selection=bad):
                with self.assertRaises(ValueError):
                    music_library.parse_track_numbers(bad, 2)

    def test_directory_symlink_and_world_write_refused(self):
        alias = self.root.parent / "shortcut"
        alias.symlink_to(self.root, target_is_directory=True)
        for candidate in (alias, Path("relative"), self.root / ".." / "Private Music"):
            with self.assertRaises((ValueError, OSError)):
                music_library.discover_library(candidate)
        self.root.chmod(0o777)
        try:
            with self.assertRaises(PermissionError):
                music_library.discover_library(self.root)
        finally:
            self.root.chmod(0o700)

    def test_invalid_and_linked_wavs_skipped_not_public(self):
        symlink = self.root / "secret-link.wav"
        symlink.symlink_to(self.a)
        bad = self.root / "private-secret.wav"
        bad.write_text("This is not WAV")
        (self.root / ".hidden.wav").write_bytes(b"not a wav")
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.root / "fifo.wav")
        rows, skipped = music_library.discover_library(self.root)
        self.assertEqual(len(rows), 2)
        self.assertGreaterEqual(skipped, 2)
        message = music_library.display_library(rows)
        for private in ("secret-link", "private-secret", ".hidden", "fifo"):
            self.assertNotIn(private, message)

    def test_folder_inventory_is_bounded_and_rejects_empty(self):
        empty = self.root.parent / "Empty"
        empty.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "No supported"):
            music_library.discover_library(empty)
        for index in range(music_library.MAX_SCANNED + 1):
            (empty / ("file-%03d.txt" % index)).touch()
        with self.assertRaisesRegex(ValueError, "Too many"):
            music_library.discover_library(empty)

    def test_empty_first_boot_folder_is_normal_in_readonly_view_only(self):
        empty = self.root.parent / "FreshPrivateMusic"
        empty.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "No supported local WAV"):
            music_library.discover_library(empty)
        records, skipped = music_library.discover_library(
            empty, allow_empty=True)
        self.assertEqual((records, skipped), ([], 0))
        display = music_library.display_library(records)
        for phrase in ("Local music library: 0 valid WAV",
                       "EMPTY PRIVATE WAV LIBRARY",
                       "audiohub-music --speaker-check",
                       "audiohub-music --speaker-guide",
                       "audiohub-music-transfer --help",
                       "No automatic import occurs",
                       "No playback started"):
            self.assertIn(phrase, display)
        self.assertNotIn(str(empty), display)
        self.assertNotIn(str(self.root), display)
        self.assertEqual(len(display.splitlines()), 8)
        for invalid in (None, "yes", 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    music_library.discover_library(empty, allow_empty=invalid)

    def test_empty_library_cli_list_is_success_but_play_selection_is_denied(self):
        empty = self.root.parent / "FreshEmpty"
        empty.mkdir(mode=0o700)
        with mock.patch.object(local_music, "play_playlist") as player, \
             mock.patch.object(local_music, "music_sink_available") as graph, \
             mock.patch("builtins.print") as output:
            self.assertEqual(local_music.main([
                "--library", str(empty)]), 0)
            self.assertEqual(local_music.main([
                "--library", str(empty), "--show-titles"]), 0)
            self.assertEqual(local_music.main([
                "--library", str(empty), "--tracks", "1"]), 2)
            self.assertEqual(local_music.main([
                "--library", str(empty), "--tracks", "1", "--play"]), 2)
            self.assertEqual(local_music.main([
                "--library", str(empty), "--play"]), 2)
        graph.assert_not_called()
        player.assert_not_called()
        rendered = "\n".join(" ".join(map(str, a.args))
                             for a in output.call_args_list)
        self.assertIn("EMPTY PRIVATE WAV LIBRARY", rendered)
        self.assertIn("audiohub-music --speaker-check", rendered)
        self.assertNotIn(str(empty), rendered)

    def test_guided_first_use_empty_library_aborts_without_play_or_tty_read(self):
        empty = self.root.parent / "FreshDefault"
        empty.mkdir(mode=0o700)
        outputs, attempted = [], []
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=1000), \
             mock.patch.object(local_music, "play_playlist") as player:
            result = music_library.guided_session(
                empty, preflight=lambda **kw: True,
                read_line=lambda: attempted.append("read"),
                out=outputs.append,
                runner=lambda *a, **kw: attempted.append("run"))
        self.assertFalse(result)
        self.assertEqual(attempted, [])
        player.assert_not_called()
        message = "\n".join(outputs)
        self.assertIn("EMPTY PRIVATE WAV LIBRARY", message)
        self.assertIn("ALBUM SETUP INCOMPLETE", message)
        self.assertIn("no audio started", message)
        self.assertNotIn(str(empty), message)
        self.assertNotIn("Type exact uppercase PLAY then Enter", message)

    def test_unsafe_empty_directory_remains_rejected_with_no_media(self):
        empty = self.root.parent / "FreshUnsafe"
        empty.mkdir(mode=0o777)
        empty.chmod(0o777)
        shortcut = self.root.parent / "FreshLink"
        shortcut.symlink_to(empty, target_is_directory=True)
        for folder in (empty, shortcut, Path("relative/folder")):
            with self.subTest(folder=str(folder)):
                with self.assertRaises((ValueError, PermissionError, OSError)):
                    music_library.discover_library(folder, allow_empty=True)
        bad_wav = self.root.parent / "UnsafeOnly"
        bad_wav.mkdir(mode=0o700)
        (bad_wav / "private-content.wav").write_text("not PCM")
        records, skipped = music_library.discover_library(
            bad_wav, allow_empty=True)
        self.assertEqual(records, [])
        self.assertEqual(skipped, 1)
        self.assertNotIn("private-content", music_library.display_library(records))

    def test_large_wav_library_requires_selection_not_bulk_play(self):
        for index in range(42):
            self.make_wav(self.root / ("Extra-%02d.wav" % index), 60)
        with self.assertRaisesRegex(ValueError, "40"):
            music_library.discover_library(self.root)

    def test_cli_folder_browse_defaults_to_no_pipewire_no_sound(self):
        with mock.patch.object(local_music, "play_playlist") as player, \
             mock.patch("builtins.print") as output, \
             mock.patch.object(local_music, "bounded_command_output") as capture:
            self.assertEqual(local_music.main(["--library", str(self.root)]), 0)
            self.assertEqual(local_music.main(
                ["--library", str(self.root), "--tracks", "2,1"]), 0)
            capture.assert_not_called()
            player.assert_not_called()
        rendered = "\n".join(" ".join(map(str, call.args))
                             for call in output.call_args_list)
        self.assertIn("Track 1", rendered)
        self.assertIn("Selection: 2 track(s)", rendered)
        self.assertIn("Preview only", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(self.b.name, rendered)

    def test_cli_explicit_play_uses_exact_selected_paths_only(self):
        with mock.patch.object(local_music, "play_playlist", return_value=True) as play, \
             mock.patch("builtins.print") as output:
            self.assertEqual(local_music.main([
                "--library", str(self.root), "--tracks", "2",
                "--minutes", "1", "--play"
            ]), 0)
        play.assert_called_once_with([self.b], max_minutes=1)
        self.assertNotIn(str(self.root), str(output.call_args_list))

    def test_cli_refuses_implicit_library_autoplay_and_conflicting_modes(self):
        for args in (
            ["--library", str(self.root), "--play"],
            ["--library", str(self.root), str(self.a)],
            ["--tracks", "1", str(self.a)],
            ["--show-titles", str(self.a)],
            ["--library", str(self.root), "--tracks", "1,1", "--play"],
        ):
            with self.subTest(args=args):
                with mock.patch.object(local_music, "play_playlist") as play, \
                     mock.patch("builtins.print") as printer:
                    self.assertEqual(local_music.main(args), 2)
                    play.assert_not_called()
                    self.assertNotIn(str(self.root), str(printer.call_args_list))

    def test_no_recursive_scanning_and_no_unapproved_files(self):
        nested = self.root / "nested"
        nested.mkdir()
        self.make_wav(nested / "third.wav", 20)
        (self.root / "notes.txt").write_text("PRIVATE")
        items, _ = music_library.discover_library(self.root)
        self.assertEqual(len(items), 2)
        self.assertNotIn("PRIVATE", music_library.display_library(items))



    def guided(self, lines, *, show_titles=False, max_minutes=1):
        output, runs = [], []
        choices = iter(lines)
        def runner(paths, *, max_minutes):
            runs.append((paths, max_minutes))
            return True
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=1000):
            finished = music_library.guided_session(
                self.root, max_minutes=max_minutes,
                show_titles=show_titles, read_line=lambda: next(choices),
                out=output.append, runner=runner)
        return finished, runs, "\n".join(output)

    def test_real_guided_album_precheck_is_readonly_and_independent(self):
        output = []
        with mock.patch.object(local_music, "music_sink_available",
                               return_value=True) as graph, \
             mock.patch.object(local_music, "play_playlist") as player, \
             mock.patch.object(music_library, "discover_library") as scan:
            ok = REAL_GUIDED_ALBUM_PREFLIGHT(
                capture=lambda *a, **kw: None,
                which=lambda _: "/usr/bin/pw-cat", out=output.append)
        self.assertTrue(ok)
        graph.assert_called_once()
        player.assert_not_called()
        scan.assert_not_called()
        report = "\n".join(output)
        for phrase in ("LOCAL ALBUM PRECHECK", "Private music input: READY",
                       "Local playback tool: AVAILABLE",
                       "READY FOR MANUAL SELECTION", "No WAV opened",
                       "UNVERIFIED"):
            self.assertIn(phrase, report)
        for private in (self.a.name, self.b.name, str(self.root)):
            self.assertNotIn(private, report)

    def test_precheck_reports_both_missing_prerequisites_without_sound(self):
        output = []
        with mock.patch.object(local_music, "music_sink_available",
                               return_value=False), \
             mock.patch.object(local_music, "play_playlist") as player:
            self.assertFalse(REAL_GUIDED_ALBUM_PREFLIGHT(
                which=lambda _: None, out=output.append))
        player.assert_not_called()
        report = "\n".join(output)
        self.assertIn("Private music input: NEEDS ATTENTION", report)
        self.assertIn("Local playback tool: NEEDS ATTENTION", report)
        self.assertIn("NOT READY", report)
        self.assertIn("--check or --list", report)
        self.assertNotIn(str(self.root), report)

    def test_precheck_independently_checks_sink_and_tool_failure(self):
        for sink, tool in ((True, None), (False, "/usr/bin/pw-cat")):
            with self.subTest(sink=sink, tool=tool):
                output = []
                with mock.patch.object(local_music, "music_sink_available",
                                       return_value=sink):
                    self.assertFalse(REAL_GUIDED_ALBUM_PREFLIGHT(
                        which=lambda _: tool, out=output.append))
                report = "\n".join(output)
                self.assertIn("READY" if sink else "NEEDS ATTENTION", report)
                self.assertIn("AVAILABLE" if tool else
                              "Local playback tool: NEEDS ATTENTION", report)

    def test_private_backend_errors_never_leak_to_album_precheck(self):
        output = []
        def fail_capture(*args, **kw):
            raise RuntimeError("PRIVATE_WAV_NAME")
        def fail_tool(name):
            raise OSError("PRIVATE_DEVICE_MAC")
        with mock.patch.object(local_music, "music_sink_available",
                               side_effect=fail_capture):
            self.assertFalse(REAL_GUIDED_ALBUM_PREFLIGHT(
                which=fail_tool, out=output.append))
        report = "\n".join(output)
        self.assertIn("NOT READY", report)
        self.assertNotIn("PRIVATE_", report)
        self.assertNotIn(str(self.root), report)

    def test_guided_precheck_failure_aborts_before_private_library_scan_or_play(self):
        for choice in ("missing_sink", "missing_tool", "exception"):
            with self.subTest(choice=choice):
                called, output = [], []
                def preflight(*, out):
                    called.append("preflight")
                    out("Local playback tool: NEEDS ATTENTION")
                    if choice == "exception":
                        raise RuntimeError("SECRET-ALBUM-PATH")
                    return False
                with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
                     mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
                     mock.patch.object(os, "geteuid", return_value=1000), \
                     mock.patch.object(music_library, "discover_library") as scan, \
                     mock.patch.object(local_music, "play_playlist") as sound:
                    self.assertFalse(music_library.guided_session(
                        self.root, preflight=preflight,
                        read_line=lambda: called.append("read"),
                        out=output.append,
                        runner=lambda *a, **kw: called.append("runner")))
                self.assertEqual(called, ["preflight"])
                scan.assert_not_called()
                sound.assert_not_called()
                report = "\n".join(output)
                self.assertIn("GUIDED ALBUM STOPPED BEFORE SELECTION OR PLAY", report)
                self.assertIn("no WAVs were scanned", report)
                self.assertNotIn(str(self.root), report)
                self.assertNotIn("SECRET-ALBUM-PATH", report)

    def test_guided_album_requires_explicit_play_and_preserves_chosen_order(self):
        ok, runs, output = self.guided(["2,1", "PLAY"])
        self.assertTrue(ok)
        self.assertEqual(runs, [([self.b, self.a], 1)])
        self.assertIn("GUIDED LOCAL MODE", output)
        self.assertIn("Next: choose numbers, ALL (up to 8), or SHUFFLE", output)
        self.assertNotIn("then add --play", output)
        self.assertIn("Selected 2 WAV track(s)", output)
        self.assertIn("Explicit PLAY confirmed", output)
        self.assertNotIn(self.a.name, output)
        self.assertNotIn(self.b.name, output)
        self.assertNotIn(str(self.root), output)

    def test_guided_select_cancellation_never_spawns_player(self):
        for replies in ([""], [None], ["2,1", ""],
                        ["2,1", "play"], ["2,1", "PLAY "],
                        ["2,1", "y"], ["2,1", None]):
            with self.subTest(replies=replies):
                ok, runs, output = self.guided(replies)
                self.assertFalse(ok)
                self.assertEqual(runs, [])
                self.assertIn("No playback started", output)
                self.assertNotIn(str(self.root), output)

    def test_guided_invalid_selection_retries_without_audio(self):
        ok, runs, output = self.guided(["1,1", "99", "2", "PLAY"])
        self.assertTrue(ok)
        self.assertEqual(runs, [([self.b], 1)])
        self.assertEqual(output.count("Invalid selection or duration"), 2)
        self.assertNotIn(self.root.name, output)

    def test_guided_three_invalid_selections_fail_closed(self):
        for attempts in (["1,1", "3", "x"],
                         [" " * 65, "3", "2,2"]):
            ok, runs, output = self.guided(attempts)
            self.assertFalse(ok)
            self.assertEqual(runs, [])
            self.assertIn("Selection limit reached", output)
            self.assertNotIn(self.a.name, output)

    def test_guided_cannot_autoplay_through_wrong_or_too_long_confirmation(self):
        for answer in ("PLAY\n", "PLAY!" * 15, "PLAYNOW", "PLaY", " PLAY"):
            ok, runs, output = self.guided(["1", answer])
            self.assertFalse(ok)
            self.assertEqual(runs, [])
            self.assertIn("cancelled", output.lower())

    def test_explicit_private_title_display_still_opt_in(self):
        done, runs, output = self.guided(["1", ""], show_titles=True)
        self.assertFalse(done)
        self.assertEqual(runs, [])
        self.assertIn("a demo", output)
        self.assertNotIn(str(self.root), output)
        self.assertIn("THIS local terminal", output)

    def test_guided_refuses_nonterminal_and_root_before_folder_scan(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: False)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_library, "discover_library") as discover:
            with self.assertRaises(PermissionError):
                music_library.guided_session(self.root, read_line=lambda: "PLAY")
            discover.assert_not_called()
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=0), \
             mock.patch.object(music_library, "discover_library") as discover:
            with self.assertRaises(PermissionError):
                music_library.guided_session(self.root, read_line=lambda: "PLAY")
            discover.assert_not_called()

    def test_bounded_terminal_input_rejects_eof_controls_and_truncation(self):
        import io
        with mock.patch("sys.stdin", io.StringIO("PLAY\n")):
            self.assertEqual(music_library._terminal_line(), "PLAY")
        for input_string in ("", "x" * 100 + "\n", "PLAY"):
            with self.subTest(raw=input_string[:12]), \
                 mock.patch("sys.stdin", io.StringIO(input_string)):
                self.assertIsNone(music_library._terminal_line())
        with mock.patch("sys.stdin", io.StringIO("PLAY\r\n")):
            self.assertEqual(music_library._terminal_line(), "PLAY")

    def test_guided_right_stereo_mode_is_reviewed_before_exact_play(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=1000):
            choices = iter(["2,1", "PLAY"])
            calls, shown = [], []
            def runner(paths, **kw):
                calls.append((paths, kw))
                return True
            self.assertTrue(music_library.guided_session(
                self.root, max_minutes=4, level="quiet", channel="right",
                read_line=lambda: next(choices),
                out=shown.append, runner=runner))
            self.assertEqual(calls, [([self.b, self.a], {
                "max_minutes": 4, "level": "quiet", "channel": "right"})])
            text = "\n".join(shown)
            self.assertIn("channel RIGHT", text)
            self.assertIn("opposite stereo PCM channel", text)
            self.assertIn("QUIET", text)
            self.assertIn("Type exact uppercase PLAY", text)
            self.assertNotIn(self.b.name, text)
            self.assertNotIn(str(self.root), text)

    def test_mono_selection_in_one_sided_mode_retries_without_playing_mono(self):
        mono = self.root / "c private-mono.wav"
        with wave.open(str(mono), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(b"\x01\x02" * 120)
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=1000):
            choices = iter(["3", "1", "PLAY"])
            calls, shown = [], []
            self.assertTrue(music_library.guided_session(
                self.root, max_minutes=4, channel="left",
                read_line=lambda: next(choices), out=shown.append,
                runner=lambda paths, **kw: calls.append((paths, kw)) or True))
            self.assertEqual(calls, [([self.a], {
                "max_minutes": 4, "channel": "left"})])
            text = "\n".join(shown)
            self.assertIn("LEFT/RIGHT requires stereo WAVs", text)
            self.assertNotIn("c private-mono", text)
            self.assertNotIn(str(self.root), text)

    def test_guided_channel_mode_wrong_confirmation_never_starts_sound(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=1000):
            calls = []
            self.assertFalse(music_library.guided_session(
                self.root, channel="left", read_line=iter(["1", "play"]).__next__,
                out=lambda _: None,
                runner=lambda *args, **kw: calls.append(True)))
            self.assertEqual(calls, [])

    def test_guided_cli_forwards_stereo_mode_only_when_explicitly_chosen(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_library, "guided_session",
                               return_value=True) as guided:
            self.assertEqual(local_music.main([
                "--library", str(self.root), "--guided",
                "--minutes", "5", "--channel", "left"]), 0)
            guided.assert_called_once_with(
                str(self.root), max_minutes=5, show_titles=False, channel="left")

    def test_guided_quiet_level_is_reviewed_and_requires_exact_play(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(os, "geteuid", return_value=1000):
            choices = iter(["1", "PLAY"])
            sessions = []
            output = []
            def runner(paths, **kwargs):
                sessions.append((paths, kwargs))
                return True
            self.assertTrue(music_library.guided_session(
                self.root, max_minutes=4, level="quiet",
                read_line=lambda: next(choices),
                out=output.append, runner=runner))
            self.assertEqual(sessions, [([self.a],
                                         {"max_minutes": 4, "level": "quiet"})])
            shown = "\n".join(output)
            self.assertIn("QUIET", shown)
            self.assertIn("not calibrated speaker loudness", shown)
            self.assertNotIn(self.a.name, shown)
            self.assertNotIn(str(self.root), shown)
            denied = []
            choices = iter(["1", "play"])
            self.assertFalse(music_library.guided_session(
                self.root, max_minutes=4, level="soft",
                read_line=lambda: next(choices),
                out=lambda _: None, runner=lambda *a, **kw: denied.append(True)))
            self.assertEqual(denied, [])

    def test_cli_guided_opt_in_quiet_level_and_no_autoplay(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_library, "guided_session",
                               return_value=True) as guided:
            self.assertEqual(local_music.main([
                "--library", str(self.root), "--guided",
                "--minutes", "7", "--level", "quiet"]), 0)
            guided.assert_called_once_with(
                str(self.root), max_minutes=7, show_titles=False, level="quiet")

    def test_cli_guided_needs_only_library_and_never_implicit_play(self):
        with mock.patch("sys.stdin", mock.Mock(isatty=lambda: True)), \
             mock.patch("sys.stdout", mock.Mock(isatty=lambda: True)), \
             mock.patch.object(music_library, "guided_session", return_value=True) as guided:
            self.assertEqual(local_music.main(
                ["--library", str(self.root), "--guided", "--minutes", "1"]), 0)
            guided.assert_called_once_with(
                str(self.root), max_minutes=1, show_titles=False)

    def test_cli_guided_rejects_ambiguous_legacy_play_flags(self):
        combinations = (
            ["--guided"],
            ["--guided", "--library", str(self.root), "--play"],
            ["--guided", "--library", str(self.root), "--interactive"],
            ["--guided", "--library", str(self.root), "--tracks", "1"],
            ["--guided", "--library", str(self.root), str(self.a)],
        )
        with mock.patch.object(music_library, "guided_session") as guided, \
             mock.patch("builtins.print") as log:
            for arguments in combinations:
                with self.subTest(arguments=arguments):
                    self.assertEqual(local_music.main(arguments), 2)
                    guided.assert_not_called()
            self.assertNotIn(str(self.a), str(log.call_args_list))


    def test_guided_all_plays_ordered_small_album_only_after_play(self):
        done, calls, output = self.guided(["ALL", "PLAY"])
        self.assertTrue(done)
        self.assertEqual(calls, [([self.a, self.b], 1)])
        self.assertIn("Selected library track numbers: 1,2", output)
        self.assertNotIn(str(self.root), output)
        self.assertNotIn("favorite", output)

    def test_guided_all_rejects_album_larger_than_max_files(self):
        for number in range(7):
            self.make_wav(self.root / ("Extra%02d.wav" % number), 15)
        done, calls, output = self.guided(["ALL", "ALL", "ALL"])
        self.assertFalse(done)
        self.assertEqual(calls, [])
        self.assertIn("Selection limit reached", output)
        self.assertNotIn(self.a.name, output)

    def test_shuffle_uses_validated_selected_set_without_printing_names(self):
        records, _ = music_library.discover_library(self.root)
        files, report, numbers = music_library.guided_choice(
            records, "SHUFFLE", max_minutes=1,
            shuffle=lambda positions: positions.reverse())
        self.assertEqual(files, [self.b, self.a])
        self.assertEqual(numbers, "2,1")
        self.assertEqual(report["files"], 2)
        self.assertNotIn(str(self.root), repr(report))

    def test_shuffle_in_guided_mode_still_requires_explicit_play(self):
        with mock.patch("secrets.SystemRandom") as random_instance:
            random_instance.return_value.shuffle.side_effect = lambda positions: positions.reverse()
            done, calls, output = self.guided(["SHUFFLE", "PLAY"])
        self.assertTrue(done)
        self.assertEqual(calls, [([self.b, self.a], 1)])
        self.assertIn("Selected library track numbers: 2,1", output)
        self.assertNotIn(self.b.name, output)

    def test_shuffle_no_play_without_confirmation(self):
        with mock.patch("secrets.SystemRandom") as random_instance:
            random_instance.return_value.shuffle.side_effect = lambda positions: positions.reverse()
            done, calls, output = self.guided(["SHUFFLE", "cancel"])
        self.assertFalse(done)
        self.assertEqual(calls, [])
        self.assertIn("No playback started", output)

    def test_shuffle_time_budget_keeps_only_wavs_that_fit(self):
        records, _ = music_library.discover_library(self.root)
        fake = [(records[0][0], {**records[0][1], "duration_ms":40000}),
                (records[1][0], {**records[1][1], "duration_ms":40000}),
                (records[0][0], {**records[0][1], "duration_ms":10000})]
        def fake_selected(_items, numbers, *, max_minutes):
            self.assertEqual(numbers, "1,3")
            self.assertEqual(max_minutes, 1)
            return [self.a, self.a], {"files":2}
        with mock.patch.object(music_library, "selected_paths",
                               side_effect=fake_selected) as picked:
            paths, report, numbers = music_library.guided_choice(
                fake, "SHUFFLE", max_minutes=1,
                shuffle=lambda positions: None)
        self.assertEqual(numbers, "1,3")
        self.assertEqual(paths, [self.a, self.a])
        self.assertEqual(report["files"], 2)
        picked.assert_called_once()

    def test_change_resets_selection_without_playing_old_choice(self):
        done, calls, output = self.guided(["2", "CHANGE", "1,2", "PLAY"])
        self.assertTrue(done)
        self.assertEqual(calls, [([self.a, self.b], 1)])
        self.assertIn("Selection cleared", output)
        self.assertIn("Selected library track numbers: 2", output)
        self.assertIn("Selected library track numbers: 1,2", output)
        self.assertNotIn(self.a.name, output)

    def test_repeated_change_cancels_without_playback(self):
        done, calls, output = self.guided(
            ["1", "CHANGE", "2", "CHANGE", "1", "CHANGE"])
        self.assertFalse(done)
        self.assertEqual(calls, [])
        self.assertIn("Change limit reached", output)

    def test_unexpected_selection_tokens_do_not_start_audio(self):
        done, calls, output = self.guided(["all", "shuffle ", "CHANGE"])
        self.assertFalse(done)
        self.assertEqual(calls, [])
        self.assertIn("Selection limit reached", output)

    def test_all_and_shuffle_reject_invalid_session_time(self):
        rows, _ = music_library.discover_library(self.root)
        for minutes in (0, 31, True, "10", None):
            for keyword in ("ALL", "SHUFFLE", "1"):
                with self.subTest(minutes=minutes, keyword=keyword):
                    with self.assertRaises(ValueError):
                        music_library.guided_choice(
                            rows, keyword, max_minutes=minutes)

    def test_legacy_browser_prompt_keeps_explicit_flags(self):
        rows, _ = music_library.discover_library(self.root)
        classic = music_library.display_library(rows)
        wizard = music_library.display_library(rows, guided=True)
        self.assertIn("--tracks 1,3", classic)
        self.assertNotIn("--tracks 1,3", wizard)
        self.assertIn("Next: choose numbers, ALL (up to 8), or SHUFFLE", wizard)


if __name__ == "__main__":
    unittest.main()
