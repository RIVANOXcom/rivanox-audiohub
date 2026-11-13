# SPDX-License-Identifier: AGPL-3.0-only
"""Offline operator WAV transfer: no overwrite, no links, explicit consent."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import music_transfer


class MusicTransferTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.music = self.root / "PrivateMusic"
        self.external = self.root / "PrivateExternal"
        self.music.mkdir(mode=0o700)
        self.external.mkdir(mode=0o700)
        self.music.chmod(0o700)
        self.external.chmod(0o700)
        self.name = "secret-artist.wav"
        self.wav = self.music / self.name
        with wave.open(str(self.wav), "wb") as track:
            track.setnchannels(2)
            track.setsampwidth(2)
            track.setframerate(48000)
            track.writeframes(b"\x00\x01\x00\x02" * 250)
        self.output = []

    def run_transfer(self, operation, *, allow=True, external=None, music=None,
                     resume=False, verify=False):
        with mock.patch.object(music_transfer.os, "geteuid", return_value=1000):
            return music_transfer.transfer(
                operation,
                str(self.external if external is None else external),
                music_dir=str(self.music if music is None else music),
                confirm=lambda: allow,
                out=self.output.append,
                require_terminal=False, resume=resume, verify=verify)

    def test_private_backup_then_restore_preserves_wav_without_overwrite(self):
        original = self.wav.read_bytes()
        self.assertTrue(self.run_transfer("backup"))
        archived = self.external / self.name
        self.assertEqual(archived.read_bytes(), original)
        self.assertEqual(self.wav.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(archived.stat().st_mode), 0o600)
        self.assertEqual(archived.stat().st_nlink, 1)
        text = "\n".join(self.output)
        self.assertIn("1 supported tracks", text)
        self.assertIn("Private transfer fingerprint", text)
        self.assertNotIn(self.name, text)
        self.assertNotIn(str(self.root), text)
        self.wav.unlink()  # ONLY the test fixture, never production transfer.
        self.output.clear()
        self.assertTrue(self.run_transfer("restore"))
        self.assertEqual(self.wav.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.wav.stat().st_mode), 0o600)
        self.assertEqual(archived.read_bytes(), original)
        self.assertNotIn(self.name, "\n".join(self.output))

    def test_any_nonexact_operator_confirmation_cancels_without_writes(self):
        for answer in (False, None, 0, "COPY", "copy"):
            with self.subTest(answer=answer):
                self.output.clear()
                self.assertFalse(self.run_transfer("backup", allow=answer))
                self.assertEqual(list(self.external.iterdir()), [])
                self.assertIn("Transfer cancelled", "\n".join(self.output))

    def test_second_backup_does_not_overwrite_any_existing_private_file(self):
        self.assertTrue(self.run_transfer("backup"))
        original = (self.external / self.name).read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_transfer("backup")
        self.assertEqual((self.external / self.name).read_bytes(), original)
        self.assertEqual(list(self.external.iterdir()), [self.external / self.name])

    def test_external_symlink_is_rejected_even_when_it_points_to_private_dir(self):
        alias = self.root / "private-alias"
        alias.symlink_to(self.external, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            self.run_transfer("backup", external=alias)
        self.assertEqual(list(self.external.iterdir()), [])

    def test_external_directory_must_exist_be_private_and_operator_owned(self):
        with self.assertRaises((OSError, PermissionError)):
            self.run_transfer("backup", external=self.root / "missing")
        # A private existing parent directory is valid as a directory;
        # make it actually public to verify the privacy refusal.
        self.root.chmod(0o755)
        with self.assertRaises(PermissionError):
            self.run_transfer("backup", external=self.root)
        self.external.chmod(0o755)
        with self.assertRaises(PermissionError):
            self.run_transfer("backup")
        self.assertEqual(list(self.external.iterdir()), [])

    def test_source_hardlink_refused_without_creating_copies(self):
        alias = self.music / "second.wav"
        os.link(self.wav, alias)
        with self.assertRaises(ValueError):
            self.run_transfer("backup")
        self.assertEqual(list(self.external.iterdir()), [])

    def test_source_symlink_refused_and_missing_wav_ignored(self):
        linked = self.music / "hidden-link.wav"
        linked.symlink_to(self.wav)
        with self.assertRaises(ValueError):
            self.run_transfer("backup")
        self.assertEqual(list(self.external.iterdir()), [])

    def test_invalid_wav_causes_no_backup_rather_than_silent_loss(self):
        (self.music / "broken.wav").write_bytes(b"garbage")
        with self.assertRaises(ValueError):
            self.run_transfer("backup")
        self.assertEqual(list(self.external.iterdir()), [])

    def test_first_sd_swap_can_restore_from_read_only_old_music_source(self):
        # PR258 has no transfer CLI. The owner may mount the old SD
        # separately read-only, then restore from its original WAV directory.
        original = self.wav.read_bytes()
        self.assertTrue(self.run_transfer("backup"))
        archived = self.external / self.name
        self.wav.unlink()  # test fixture only, not production.
        self.external.chmod(0o500)
        self.output.clear()
        self.assertTrue(self.run_transfer("restore"))
        self.assertEqual(self.wav.read_bytes(), original)
        self.assertEqual(archived.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.external.stat().st_mode), 0o500)
        self.assertEqual(stat.S_IMODE(self.wav.stat().st_mode), 0o600)

    def test_cancel_restoration_leaves_existing_music_unchanged(self):
        self.assertTrue(self.run_transfer("backup"))
        self.wav.unlink()  # test fixture only
        self.assertFalse(self.run_transfer("restore", allow=False))
        self.assertFalse(self.wav.exists())
        self.assertTrue((self.external / self.name).exists())

    def test_reject_same_source_and_destination_before_any_write(self):
        with self.assertRaises(ValueError):
            self.run_transfer("backup", external=self.music)
        self.assertEqual(list(self.music.iterdir()), [self.wav])

    def test_explicit_copy_fails_closed_on_insufficient_capacity(self):
        with mock.patch.object(music_transfer, "_check_available",
                               side_effect=OSError("full disk")):
            with self.assertRaises(OSError):
                self.run_transfer("backup")
        self.assertEqual(list(self.external.iterdir()), [])

    def test_nonroot_and_terminal_guards(self):
        with mock.patch.object(music_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                music_transfer.transfer("backup", str(self.external),
                                        music_dir=str(self.music),
                                        confirm=lambda: True,
                                        require_terminal=False)
        with mock.patch.object(music_transfer.os, "geteuid", return_value=1000), \
             mock.patch.object(music_transfer.sys, "stdin",
                               mock.Mock(isatty=lambda: False)):
            with self.assertRaises(PermissionError):
                music_transfer.transfer("backup", str(self.external),
                                        music_dir=str(self.music),
                                        confirm=lambda: True)
        self.assertEqual(list(self.external.iterdir()), [])

    def test_resume_skips_verified_files_without_overwriting(self):
        original = self.wav.read_bytes()
        self.assertTrue(self.run_transfer("backup"))
        fingerprint = [s for s in self.output if "fingerprint" in s][-1]
        st_before = (self.external / self.name).stat()
        self.output.clear()
        self.assertTrue(self.run_transfer("backup", resume=True))
        self.assertEqual((self.external / self.name).read_bytes(), original)
        self.assertEqual((self.external / self.name).stat().st_ino,
                         st_before.st_ino)
        self.assertIn("1 verified existing, 0 new", "\n".join(self.output))
        self.assertIn("0 new WAV copies", "\n".join(self.output))
        self.assertIn(fingerprint, self.output)

    def test_resume_interrupted_partial_library_and_verify(self):
        second = self.music / "private-two.wav"
        with wave.open(str(second), "wb") as track:
            track.setnchannels(1)
            track.setsampwidth(2)
            track.setframerate(44100)
            track.writeframes(b"\x00\x02" * 250)
        original = self.wav.read_bytes()
        second_original = second.read_bytes()
        # Simulate one already committed file from an interrupted copy:
        (self.external / self.name).write_bytes(original)
        (self.external / self.name).chmod(0o600)
        self.output.clear()
        self.assertTrue(self.run_transfer("backup", resume=True))
        self.assertIn("1 verified existing, 1 new", "\n".join(self.output))
        self.assertEqual((self.external / self.name).read_bytes(), original)
        self.assertEqual((self.external / second.name).read_bytes(), second_original)
        self.output.clear()
        self.assertTrue(self.run_transfer("backup", verify=True, allow=False))
        self.assertIn("2 source WAVs match destination", "\n".join(self.output))
        self.assertNotIn("Type exact uppercase COPY", "\n".join(self.output))
        self.assertEqual(second.read_bytes(), second_original)

    def test_resume_conflicting_target_aborts_before_any_new_file(self):
        second = self.music / "private-two.wav"
        with wave.open(str(second), "wb") as track:
            track.setnchannels(2)
            track.setsampwidth(2)
            track.setframerate(48000)
            track.writeframes(b"\x00\x03\x00\x04" * 250)
        conflict = self.external / self.name
        conflict.write_bytes(self.wav.read_bytes()[:-1] + b"\xff")
        conflict.chmod(0o600)
        with self.assertRaises(ValueError):
            self.run_transfer("backup", resume=True)
        self.assertFalse((self.external / second.name).exists())
        self.assertEqual(conflict.read_bytes()[-1:], b"\xff")
        with self.assertRaises(ValueError):
            self.run_transfer("backup", verify=True)

    def test_resume_rejects_symlink_hardlink_and_public_target(self):
        dest = self.external / self.name
        dest.symlink_to(self.wav)
        with self.assertRaises(OSError):
            self.run_transfer("backup", resume=True)
        dest.unlink()  # Fixture cleanup only.
        dest.write_bytes(self.wav.read_bytes())
        dest.chmod(0o644)
        with self.assertRaises(ValueError):
            self.run_transfer("backup", resume=True)
        dest.chmod(0o600)
        link = self.root / "extra-hardlink"
        os.link(dest, link)
        with self.assertRaises(ValueError):
            self.run_transfer("backup", resume=True)

    def test_verify_requires_all_source_files_and_cannot_change_files(self):
        with self.assertRaises(FileNotFoundError):
            self.run_transfer("backup", verify=True, allow=True)
        self.assertEqual(list(self.external.iterdir()), [])
        self.assertTrue(self.run_transfer("backup"))
        snapshot = (self.external / self.name).stat()
        self.output.clear()
        self.assertTrue(self.run_transfer("backup", verify=True, allow=False))
        self.assertEqual((self.external / self.name).stat().st_ino, snapshot.st_ino)
        self.assertEqual((self.external / self.name).stat().st_mtime_ns,
                         snapshot.st_mtime_ns)
        # Restore-side verification requires restored data, and is read-only.
        self.assertTrue(self.run_transfer("restore", verify=True, allow=False))
        self.assertNotIn("Type exact uppercase COPY", "\n".join(self.output))

    def test_restore_resume_from_read_only_old_sd_source(self):
        self.assertTrue(self.run_transfer("backup"))
        self.external.chmod(0o500)
        self.output.clear()
        self.assertTrue(self.run_transfer("restore", resume=True))
        self.assertIn("1 verified existing, 0 new", "\n".join(self.output))
        self.assertTrue(self.run_transfer("restore", verify=True))
        self.assertEqual(stat.S_IMODE(self.external.stat().st_mode), 0o500)

    def test_no_empty_library_claims_verified_migration(self):
        self.wav.unlink()  # Fixture only.
        with self.assertRaises(ValueError):
            self.run_transfer("backup", resume=True)
        with self.assertRaises(ValueError):
            self.run_transfer("backup", verify=True)
        self.assertEqual(list(self.external.iterdir()), [])

    def test_resume_guard_refuses_changed_existing_source_before_copies(self):
        self.assertTrue(self.run_transfer("backup"))
        self.wav.write_bytes(self.wav.read_bytes()[:-1] + b"\x07")
        with self.assertRaises(ValueError):
            self.run_transfer("backup", resume=True)
        self.assertEqual((self.external / self.name).read_bytes()[-1:],
                         b"\x02")

    def test_resume_and_verify_cli_parsing(self):
        with mock.patch.object(music_transfer, "transfer", return_value=True) as fn:
            self.assertEqual(music_transfer.main(["backup", "/private", "--resume"]), 0)
            self.assertEqual(fn.call_args.kwargs, {"resume": True, "verify": False})
            self.assertEqual(music_transfer.main(["verify-restore", "/private"]), 0)
            self.assertEqual(fn.call_args.kwargs, {"resume": False, "verify": True})
            self.assertEqual(music_transfer.main(["verify-backup", "/private"]), 0)
            self.assertEqual(fn.call_args.kwargs, {"resume": False, "verify": True})
            self.assertEqual(music_transfer.main(
                ["verify-backup", "/private", "--resume"]), 2)

    def test_shell_wrapper_help_and_bad_arguments(self):
        wrapper = (Path(__file__).resolve().parents[1] /
                   "image/stage-audiohub/01-install/files/bin/audiohub-music-transfer")
        result = subprocess.run(["/bin/sh", "-n", str(wrapper)],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("audiohub.music_transfer", text)
        self.assertNotIn("sudo ", text)
        self.assertNotIn("eval ", text)
        for args in ([], ["backup"], ["invalid", "/tmp"],
                     ["backup", "relative"], ["backup", "--play"]):
            with self.subTest(args=args):
                result = subprocess.run(["/bin/sh", str(wrapper), *args],
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)

    def test_native_image_stages_transfer_command_and_owner_only_music_folder(self):
        root = Path(__file__).resolve().parents[1]
        install = (root / "image/stage-audiohub/01-install/00-run.sh").read_text()
        audit = (root / "image/stage-audiohub/02-audit/00-run.sh").read_text()
        self.assertIn('install -m755 files/bin/audiohub-music-transfer', install)
        self.assertIn('audiohub-music-transfer --help', install)
        self.assertIn('test -x "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer"', audit)
        self.assertIn('test ! -L "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer"', audit)
        self.assertIn("PrivateMusic", install)

    def test_cli_help_is_offline_and_does_not_open_music(self):
        self.assertEqual(music_transfer.main(["--help"]), 0)
        self.assertEqual(music_transfer.main([]), 2)


if __name__ == "__main__":
    unittest.main()
