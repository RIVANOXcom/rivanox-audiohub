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


if __name__ == "__main__":
    unittest.main()
