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

    def test_guided_album_requires_explicit_play_and_preserves_chosen_order(self):
        ok, runs, output = self.guided(["2,1", "PLAY"])
        self.assertTrue(ok)
        self.assertEqual(runs, [([self.b, self.a], 1)])
        self.assertIn("GUIDED LOCAL MODE", output)
        self.assertIn("Next: enter up to 8 track numbers", output)
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
        self.assertEqual(output.count("Invalid track numbers"), 2)
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

if __name__ == "__main__":
    unittest.main()
