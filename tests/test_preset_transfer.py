# SPDX-License-Identifier: AGPL-3.0-only
"""Private offline EQ and inactive volume profile transfer; no secrets or sound."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import mixer_control, preset_transfer, music_transfer
from audiohub.mixer import defaults


@unittest.skipIf(os.geteuid() == 0, "Requires unprivileged filesystem owner")
class PresetTransferTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.old = self.root / "old"
        self.new = self.root / "new"
        self.media = self.root / "PrivateBackup"
        self.old.mkdir(mode=0o700)
        self.media.mkdir(mode=0o700)
        self.old.chmod(0o700)
        self.media.chmod(0o700)
        self.old_settings = self.old / "settings.json"
        self.old_profiles = self.old / "volume-profiles.json"
        self.new_settings = self.new / "settings.json"
        self.new_profiles = self.new / "volume-profiles.json"
        mixer_control.change({
            "master": 35,
            "music": {"volume": 56, "bass": 3, "mid": 1, "treble": -2},
            "laptop": {"bass": -1, "mid": 2, "treble": 3, "mute": True}},
            path=self.old_settings, confirmed=True)
        mixer_control.save_volume_profile(
            "private-one", 20, 38, 31, 23, path=self.old_profiles, confirmed=True)
        self.logs = []

    def export(self, allow=True):
        return preset_transfer.export_presets(
            str(self.media), settings_path=self.old_settings,
            profile_path=self.old_profiles, confirm=lambda: allow,
            out=self.logs.append, require_terminal=False)

    def preview(self):
        return preset_transfer.inspect(
            str(self.media), settings_path=self.new_settings,
            profile_path=self.new_profiles, out=self.logs.append,
            require_terminal=False)

    def import_profiles(self, allow=True):
        return preset_transfer.restore_profiles(
            str(self.media), profile_path=self.new_profiles,
            confirm=lambda: allow, out=self.logs.append,
            require_terminal=False)

    def import_eq(self, allow=True):
        return preset_transfer.restore_eq(
            str(self.media), settings_path=self.new_settings,
            confirm=lambda: allow, out=self.logs.append,
            require_terminal=False)

    def verify(self):
        return preset_transfer.verify(
            str(self.media), settings_path=self.new_settings,
            profile_path=self.new_profiles, out=self.logs.append,
            require_terminal=False)

    def plan_merge(self):
        return preset_transfer.plan_profiles(
            str(self.media), profile_path=self.new_profiles,
            out=self.logs.append, require_terminal=False)

    def merge(self, allow=True):
        return preset_transfer.merge_profiles(
            str(self.media), profile_path=self.new_profiles,
            confirm=lambda: allow, out=self.logs.append, require_terminal=False)

    def verify_merge(self):
        return preset_transfer.verify_merged(
            str(self.media), settings_path=self.new_settings,
            profile_path=self.new_profiles, out=self.logs.append,
            require_terminal=False)

    def test_profile_merge_preserves_existing_catalog_and_active_volume(self):
        self.assertTrue(self.export())
        mixer_control.save_volume_profile(
            "new-local", 9, 15, 20, 25, path=self.new_profiles, confirmed=True)
        existing = mixer_control.list_volume_profiles(path=self.new_profiles)["profiles"]
        self.assertEqual(self.plan_merge()["new"], 1)
        self.assertFalse(self.new_settings.exists())
        self.assertTrue(self.merge())
        result = mixer_control.list_volume_profiles(path=self.new_profiles)["profiles"]
        self.assertEqual(result["new-local"], existing["new-local"])
        self.assertEqual(result["private-one"]["master"], 20)
        self.assertFalse(self.new_settings.exists())
        self.assertTrue(self.import_eq())
        self.assertTrue(self.verify_merge())
        with self.assertRaises(ValueError):
            self.verify()  # The old exact-mode refuses extra local profiles.
        self.assertEqual(mixer_control.show(path=self.new_settings)["master"], 70)
        self.assertNotIn("new-local", "\n".join(self.logs))
        self.assertNotIn("private-one", "\n".join(self.logs))

    def test_merge_works_into_missing_catalog_and_is_repeatable_without_writes(self):
        self.assertTrue(self.export())
        self.assertEqual(self.plan_merge()["new"], 1)
        self.assertFalse(self.new.exists())
        self.assertTrue(self.merge())
        before = self.new_profiles.read_bytes()
        inode = self.new_profiles.stat().st_ino
        self.assertTrue(self.merge(allow=False))
        self.assertEqual(self.new_profiles.read_bytes(), before)
        self.assertEqual(self.new_profiles.stat().st_ino, inode)
        self.assertEqual(self.plan_merge()["identical"], 1)

    def test_merge_matching_existing_profile_skips_without_replacing_file(self):
        self.assertTrue(self.export())
        mixer_control.save_volume_profile(
            "private-one", 20, 38, 31, 23,
            path=self.new_profiles, confirmed=True)
        before = self.new_profiles.read_bytes()
        inode = self.new_profiles.stat().st_ino
        self.assertTrue(self.plan_merge()["can_merge"])
        self.assertTrue(self.merge())
        self.assertEqual(self.new_profiles.read_bytes(), before)
        self.assertEqual(self.new_profiles.stat().st_ino, inode)

    def test_merge_conflicting_profile_never_replaces_existing_value(self):
        self.assertTrue(self.export())
        mixer_control.save_volume_profile(
            "private-one", 90, 38, 31, 23,
            path=self.new_profiles, confirmed=True)
        previous = self.new_profiles.read_bytes()
        plan = self.plan_merge()
        self.assertEqual(plan["conflicts"], 1)
        self.assertFalse(plan["can_merge"])
        with self.assertRaises(ValueError):
            self.merge()
        self.assertEqual(self.new_profiles.read_bytes(), previous)
        self.assertNotIn("private-one", "\n".join(self.logs))

    def test_merge_refuses_limit_overflow_before_any_write(self):
        self.assertTrue(self.export())
        for index in range(mixer_control.MAX_CUSTOM_PROFILES):
            mixer_control.save_volume_profile(
                "new-" + str(index), 10, 20, 30, 40,
                path=self.new_profiles, confirmed=True)
        before = self.new_profiles.read_bytes()
        plan = self.plan_merge()
        self.assertEqual(plan["resulting"], mixer_control.MAX_CUSTOM_PROFILES + 1)
        self.assertFalse(plan["can_merge"])
        with self.assertRaises(ValueError):
            self.merge()
        self.assertEqual(self.new_profiles.read_bytes(), before)

    def test_cancel_merge_makes_no_new_catalog_or_active_request(self):
        self.assertTrue(self.export())
        self.assertFalse(self.merge(allow=False))
        self.assertFalse(self.new.exists())
        self.assertEqual(list(self.media.iterdir()),
                         [self.media / preset_transfer.FILENAME])

    def test_merge_rejects_modified_archive_after_preview_and_confirmation(self):
        self.assertTrue(self.export())
        source_file = self.media / preset_transfer.FILENAME
        original = source_file.read_bytes()
        def mutate():
            source_file.write_bytes(original + b" ")
            source_file.chmod(0o600)
            return True
        with self.assertRaises(OSError):
            preset_transfer.merge_profiles(
                str(self.media), profile_path=self.new_profiles,
                confirm=mutate, out=self.logs.append, require_terminal=False)
        self.assertFalse(self.new.exists())

    def test_verify_merge_refuses_missing_archive_profiles_or_different_eq(self):
        self.assertTrue(self.export())
        self.assertTrue(self.merge())
        with self.assertRaises(ValueError):
            self.verify_merge()  # EQ not yet restored.
        self.assertTrue(self.import_eq())
        self.assertTrue(self.verify_merge())
        mixer_control.change({"music": {"bass": 0}},
                             path=self.new_settings, confirmed=True)
        with self.assertRaises(ValueError):
            self.verify_merge()

    def test_merge_rejects_root_and_non_tty_before_filesystem_work(self):
        self.assertTrue(self.export())
        with mock.patch.object(preset_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.plan_merge()
            with self.assertRaises(PermissionError):
                self.merge()
        with mock.patch.object(preset_transfer.sys.stdin, "isatty", return_value=False):
            with self.assertRaises(PermissionError):
                preset_transfer.merge_profiles(
                    str(self.media), profile_path=self.new_profiles)
        self.assertFalse(self.new.exists())

    def test_new_cli_dispatch_and_installed_launcher_uses_real_verbs(self):
        with mock.patch.object(preset_transfer, "plan_profiles",
                               return_value={"can_merge": True}) as fn:
            self.assertEqual(preset_transfer.main(
                ["plan-profiles", str(self.media)]), 0)
            self.assertEqual(fn.call_args.args, (str(self.media),))
        with mock.patch.object(preset_transfer, "merge_profiles",
                               return_value=True) as fn:
            self.assertEqual(preset_transfer.main(
                ["merge-profiles", str(self.media)]), 0)
            self.assertEqual(fn.call_args.args, (str(self.media),))
        with mock.patch.object(preset_transfer, "verify_merged",
                               return_value=True) as fn:
            self.assertEqual(preset_transfer.main(
                ["verify-merged", str(self.media)]), 0)
            self.assertEqual(fn.call_args.args, (str(self.media),))
        wrapper = (Path(__file__).resolve().parents[1] /
                   "image/stage-audiohub/01-install/files/bin/audiohub-presets-transfer")
        code = wrapper.read_text()
        for action in ("plan-profiles", "merge-profiles", "verify-merged"):
            self.assertIn(action, code)
        self.assertIn('exec /usr/bin/python3 -m audiohub.preset_transfer "$@"',
                      code)

    def make_old_wav_for_backup(self):
        self.old_music = self.root / "OldReadonlyMusic"
        self.new_music = self.root / "NewMusic"
        self.old_music.mkdir(mode=0o700)
        self.new_music.mkdir(mode=0o700)
        name = "private-audio.wav"
        with wave.open(str(self.old_music / name), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(b"\x00\x01\x00\x02" * 250)
        (self.old_music / name).chmod(0o600)
        return name

    def guided_old_backup(self, copy=True, save=True):
        return preset_transfer.backup_guided(
            str(self.media), str(self.old_music), str(self.old),
            confirm_copy=lambda: copy, confirm_save=lambda: save,
            out=self.logs.append, require_terminal=False)

    def make_empty_sd_music_pair(self):
        self.old_music = self.root / "OldMusicEmpty"
        self.new_music = self.root / "NewMusicEmpty"
        self.old_music.mkdir(mode=0o700)
        self.new_music.mkdir(mode=0o700)

    def test_empty_old_music_presets_only_guided_sd_swap_is_fully_usable(self):
        self.make_empty_sd_music_pair()
        old_settings = self.old_settings.read_bytes()
        old_profiles = self.old_profiles.read_bytes()
        self.assertFalse(self.guided_old_backup(
            copy=lambda: (_ for _ in ()).throw(AssertionError("NO COPY")),
            save=False))
        self.assertFalse((self.media / preset_transfer.FILENAME).exists())
        self.assertTrue(self.guided_old_backup(copy=False, save=True))
        self.assertTrue(self.sd_check_backup())
        self.assertEqual(list(self.old_music.iterdir()), [])
        self.assertEqual(self.old_settings.read_bytes(), old_settings)
        self.assertEqual(self.old_profiles.read_bytes(), old_profiles)
        with self.assertRaises(ValueError):
            music_transfer.transfer("backup", str(self.media),
                                    music_dir=str(self.old_music),
                                    verify=True, require_terminal=False)
        plan = self.sd_plan()
        self.assertEqual(plan["wav_total"], 0)
        self.assertEqual(plan["wav_matched"], 0)
        self.assertEqual(plan["wav_missing"], 0)
        self.assertFalse(plan["wav_copy_needed"])
        self.assertEqual(plan["profile_missing"], 1)
        self.assertTrue(self.guided(copy=False, profiles=True, eq=True))
        self.assertTrue(self.sd_check_new())
        self.assertEqual(list(self.new_music.iterdir()), [])
        self.assertEqual(
            mixer_control.list_volume_profiles(path=self.new_profiles)
            ["profiles"]["private-one"]["master"], 20)
        self.assertEqual(mixer_control.show(path=self.new_settings)["master"], 70)
        self.assertFalse(mixer_control.show(path=self.new_settings)["laptop"]["mute"])
        report = "\n".join(self.logs)
        self.assertIn("Empty old-SD music and archive confirmed", report)
        self.assertIn("zero supported WAVs", report)
        self.assertIn("Guided stored-data migration verified", report)
        self.assertNotIn("private-one", report)
        self.assertNotIn(str(self.root), report)

    def test_empty_music_presets_only_guided_restore_resume_is_idempotent(self):
        self.make_empty_sd_music_pair()
        self.assertTrue(self.guided_old_backup())
        self.assertTrue(self.guided())
        saved = [self.media / preset_transfer.FILENAME,
                 self.new_settings, self.new_profiles]
        original = [(f.stat().st_ino, f.stat().st_mtime_ns, f.read_bytes())
                    for f in saved if f.exists()]
        self.assertTrue(self.guided(copy=False, profiles=False, eq=False))
        self.assertEqual(
            [(f.stat().st_ino, f.stat().st_mtime_ns, f.read_bytes())
             for f in saved if f.exists()], original)
        self.assertTrue(self.sd_check_new())

    def test_empty_source_nonempty_destination_refuses_without_preset_writes(self):
        self.make_empty_sd_music_pair()
        self.assertTrue(self.guided_old_backup())
        track = self.new_music / "existing-private.wav"
        with wave.open(str(track), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(b"\x00\x01\x00\x02" * 120)
        before = track.read_bytes()
        with self.assertRaisesRegex(ValueError, "Empty WAV archive conflicts"):
            self.sd_plan()
        with self.assertRaises(ValueError):
            self.guided()
        self.assertEqual(track.read_bytes(), before)
        self.assertFalse(self.new_settings.exists())
        self.assertFalse(self.new_profiles.exists())
        self.assertTrue((self.media / preset_transfer.FILENAME).exists())

    def test_empty_source_unsafe_wav_refuses_before_preset_archive_created(self):
        self.make_empty_sd_music_pair()
        unsafe = self.old_music / "broken-private.wav"
        unsafe.write_text("not a real WAV")
        with self.assertRaises(ValueError):
            self.guided_old_backup()
        self.assertFalse((self.media / preset_transfer.FILENAME).exists())
        self.assertEqual(unsafe.read_text(), "not a real WAV")

    def test_hidden_wav_in_old_or_archive_or_new_never_looks_empty(self):
        for where in ("old", "archive", "new"):
            with self.subTest(where=where):
                # The combined transfer must not omit an intentionally hidden
                # or private WAV, even though normal music browsing hides it.
                self.make_empty_sd_music_pair() if not hasattr(self, "old_music") else None
                if where == "old":
                    path = self.old_music / ".private-hidden.wav"
                elif where == "archive":
                    path = self.media / ".private-hidden.wav"
                else:
                    path = self.new_music / ".private-hidden.wav"
                path.write_bytes(b"private not exported")
                try:
                    if where == "old":
                        with self.assertRaisesRegex(ValueError, "Hidden private WAV"):
                            self.guided_old_backup()
                        self.assertFalse((self.media / preset_transfer.FILENAME).exists())
                    else:
                        if where == "new" and not (self.media / preset_transfer.FILENAME).exists():
                            self.assertTrue(self.guided_old_backup())
                        if where == "archive":
                            with self.assertRaisesRegex(ValueError, "Hidden private WAV"):
                                self.guided_old_backup()
                        else:
                            with self.assertRaisesRegex(ValueError, "Hidden private WAV"):
                                self.sd_plan()
                    self.assertEqual(path.read_bytes(), b"private not exported")
                finally:
                    path.unlink()

    def test_empty_music_sd_check_refuses_added_wav_after_success(self):
        self.make_empty_sd_music_pair()
        self.assertTrue(self.guided_old_backup())
        self.assertTrue(self.guided())
        new_track = self.new_music / "later.wav"
        with wave.open(str(new_track), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(b"\x00\x01\x00\x02" * 120)
        with self.assertRaisesRegex(ValueError, "Expected empty WAV target"):
            self.sd_check_new()
        self.assertTrue(new_track.exists())

    def plan_old_backup(self):
        return preset_transfer.plan_old_sd_backup(
            str(self.media), str(self.old_music), str(self.old),
            out=self.logs.append, require_terminal=False)

    def test_readonly_backup_plan_before_any_save_or_copy(self):
        name = self.make_old_wav_for_backup()
        old_bytes = (self.old_music / name).read_bytes()
        settings = self.old_settings.read_bytes()
        profiles = self.old_profiles.read_bytes()
        plan = self.plan_old_backup()
        self.assertEqual(plan["wav_total"], 1)
        self.assertEqual(plan["wav_matched"], 0)
        self.assertEqual(plan["wav_missing"], 1)
        self.assertTrue(plan["wav_copy_needed"])
        self.assertFalse(plan["presets_archived"])
        self.assertTrue(plan["presets_need_save"])
        self.assertEqual(plan["saved_profile_count"], 1)
        self.assertGreater(plan["saved_eq_band_count"], 0)
        self.assertFalse(plan["ready_for_readonly_check"])
        self.assertTrue(plan["no_files_changed"])
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertEqual((self.old_music / name).read_bytes(), old_bytes)
        self.assertEqual(self.old_settings.read_bytes(), settings)
        self.assertEqual(self.old_profiles.read_bytes(), profiles)
        rendered = "\n".join(self.logs)
        self.assertIn("READ-ONLY OLD SD BACKUP PLAN", rendered)
        self.assertIn("backup-guided PRIVATE_ARCHIVE OLD_MUSIC OLD_CONFIG", rendered)
        self.assertIn("No private", rendered)
        self.assertNotIn(name, rendered)
        self.assertNotIn("private-one", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_readonly_backup_plan_recognizes_existing_verified_archive(self):
        name = self.make_old_wav_for_backup()
        self.assertTrue(self.guided_old_backup())
        copies = [self.media / name, self.media / preset_transfer.FILENAME]
        before = [(p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
                  for p in copies]
        plan = self.plan_old_backup()
        self.assertEqual(plan["wav_matched"], 1)
        self.assertEqual(plan["wav_missing"], 0)
        self.assertTrue(plan["presets_archived"])
        self.assertFalse(plan["presets_need_save"])
        self.assertTrue(plan["ready_for_readonly_check"])
        self.assertEqual(
            before, [(p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
                     for p in copies])
        self.assertIn("check-backup PRIVATE_ARCHIVE OLD_MUSIC OLD_CONFIG",
                      "\n".join(self.logs))

    def test_readonly_backup_plan_zero_wav_with_real_saved_profiles(self):
        self.make_empty_sd_music_pair()
        plan = self.plan_old_backup()
        self.assertEqual(plan["wav_total"], 0)
        self.assertFalse(plan["wav_copy_needed"])
        self.assertTrue(plan["presets_need_save"])
        self.assertEqual(plan["saved_profile_count"], 1)
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertIn("Both protected WAV folders are EMPTY",
                      "\n".join(self.logs))
        self.assertTrue(self.guided_old_backup())
        second = self.plan_old_backup()
        self.assertTrue(second["ready_for_readonly_check"])
        self.assertTrue(self.sd_check_backup())
        self.assertEqual(list(self.old_music.iterdir()), [])

    def test_readonly_backup_plan_detects_conflicts_without_writes(self):
        name = self.make_old_wav_for_backup()
        archive = self.media / name
        archive.write_bytes(b"unsafe incompatible file")
        archive.chmod(0o600)
        before = archive.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.plan_old_backup()
        self.assertEqual(archive.read_bytes(), before)
        self.assertFalse((self.media / preset_transfer.FILENAME).exists())
        archive.unlink()
        self.assertTrue(self.export())
        original = (self.media / preset_transfer.FILENAME).read_bytes()
        mixer_control.change({"music": {"bass": -6}},
                             path=self.old_settings, confirmed=True)
        with self.assertRaises(ValueError):
            self.plan_old_backup()
        self.assertEqual((self.media / preset_transfer.FILENAME).read_bytes(),
                         original)

    def test_readonly_backup_plan_hidden_wav_and_untrusted_terminal_refuse(self):
        self.make_empty_sd_music_pair()
        secret = self.old_music / ".hidden-private.wav"
        secret.write_bytes(b"never claim this SD is empty")
        with self.assertRaisesRegex(ValueError, "Hidden private WAV"):
            self.plan_old_backup()
        self.assertEqual(list(self.media.iterdir()), [])
        secret.unlink()
        with mock.patch.object(preset_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.plan_old_backup()
        with mock.patch.object(preset_transfer.sys.stdin, "isatty",
                               return_value=False):
            with self.assertRaises(PermissionError):
                preset_transfer.plan_old_sd_backup(
                    str(self.media), str(self.old_music), str(self.old))

    def test_readonly_backup_plan_cli_and_native_launcher_dispatch(self):
        with mock.patch.object(preset_transfer, "plan_old_sd_backup",
                               return_value={"no_files_changed": True}) as fn:
            self.assertEqual(preset_transfer.main([
                "plan-backup", str(self.media), str(self.old),
                str(self.old)]), 0)
            self.assertEqual(fn.call_args.args,
                             (str(self.media), str(self.old), str(self.old)))
        import subprocess
        wrapper = (Path(__file__).resolve().parents[1] /
                   "image/stage-audiohub/01-install/files/bin/audiohub-presets-transfer")
        self.assertEqual(subprocess.run(
            ["/bin/sh", "-n", str(wrapper), str(wrapper)],
            capture_output=True).returncode, 0)
        self.assertIn('check-backup|backup-guided|plan-backup)',
                      wrapper.read_text())
        for args in (["plan-backup"], ["plan-backup", "relative", str(self.old), str(self.old)],
                     ["plan-backup", str(self.media), "relative", str(self.old)],
                     ["plan-backup", str(self.media), str(self.old), "relative"],
                     ["plan-backup", str(self.media), str(self.old)]):
            with self.subTest(args=args):
                self.assertEqual(subprocess.run(
                    ["/bin/sh", str(wrapper), *args],
                    capture_output=True, timeout=5).returncode, 2)

    def test_guided_old_backup_copy_save_and_full_verify(self):
        name = self.make_old_wav_for_backup()
        self.old_music.chmod(0o500)
        original = (self.old_music / name).read_bytes()
        old_settings = self.old_settings.read_bytes()
        old_profiles = self.old_profiles.read_bytes()
        self.assertTrue(self.guided_old_backup())
        self.assertEqual((self.media / name).read_bytes(), original)
        self.assertEqual((self.old_music / name).read_bytes(), original)
        self.assertEqual(self.old_settings.read_bytes(), old_settings)
        self.assertEqual(self.old_profiles.read_bytes(), old_profiles)
        self.assertEqual(stat.S_IMODE(self.old_music.stat().st_mode), 0o500)
        self.assertEqual(stat.S_IMODE((self.media / name).stat().st_mode), 0o600)
        self.assertTrue(self.sd_check_backup())
        logs = "\n".join(self.logs)
        self.assertIn("Step 1/2", logs)
        self.assertIn("Step 2/2", logs)
        self.assertIn("Old SD backup verified", logs)
        self.assertNotIn(name, logs)
        self.assertNotIn("private-one", logs)
        self.assertNotIn(str(self.root), logs)

    def test_guided_old_backup_cancel_copy_makes_no_new_archive_files(self):
        name = self.make_old_wav_for_backup()
        before = (self.old_music / name).read_bytes()
        self.assertFalse(self.guided_old_backup(copy=False))
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertEqual((self.old_music / name).read_bytes(), before)

    def test_guided_old_backup_cancel_save_preserves_copy_then_resume(self):
        name = self.make_old_wav_for_backup()
        self.assertFalse(self.guided_old_backup(save=False))
        dest = self.media / name
        self.assertTrue(dest.exists())
        inode = dest.stat().st_ino
        self.assertFalse((self.media / preset_transfer.FILENAME).exists())
        self.assertTrue(self.guided_old_backup(copy=False, save=True))
        self.assertEqual(dest.stat().st_ino, inode)
        self.assertTrue(self.sd_check_backup())

    def test_guided_old_backup_repeat_does_not_regenerate_catalog_or_wavs(self):
        name = self.make_old_wav_for_backup()
        self.assertTrue(self.guided_old_backup())
        paths = [self.media / name, self.media / preset_transfer.FILENAME]
        identities = [(p.stat().st_ino, p.stat().st_mtime_ns) for p in paths]
        self.assertTrue(self.guided_old_backup(copy=False, save=False))
        self.assertEqual(identities, [(p.stat().st_ino, p.stat().st_mtime_ns)
                                      for p in paths])
        self.assertTrue(self.sd_check_backup())

    def test_guided_old_backup_existing_conflicting_preset_blocks_before_copy(self):
        name = self.make_old_wav_for_backup()
        self.assertTrue(self.export())
        saved = (self.media / preset_transfer.FILENAME).read_bytes()
        mixer_control.change({"music": {"bass": -6}},
                             path=self.old_settings, confirmed=True)
        with self.assertRaises(ValueError):
            self.guided_old_backup()
        self.assertFalse((self.media / name).exists())
        self.assertEqual((self.media / preset_transfer.FILENAME).read_bytes(), saved)

    def test_guided_old_backup_existing_conflicting_wav_blocks_before_preset(self):
        name = self.make_old_wav_for_backup()
        target = self.media / name
        source = (self.old_music / name).read_bytes()
        target.write_bytes(source[:-1] + b"\x09")
        target.chmod(0o600)
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            self.guided_old_backup()
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.media / preset_transfer.FILENAME).exists())

    def test_guided_old_backup_skips_existing_same_preset_archive(self):
        name = self.make_old_wav_for_backup()
        self.assertTrue(self.export())
        catalog = self.media / preset_transfer.FILENAME
        before = (catalog.stat().st_ino, catalog.stat().st_mtime_ns)
        self.assertTrue(self.guided_old_backup(save=False))
        self.assertEqual((catalog.stat().st_ino, catalog.stat().st_mtime_ns), before)
        self.assertTrue((self.media / name).exists())
        self.assertTrue(self.sd_check_backup())

    def test_guided_old_backup_stores_neutral_empty_preset_for_full_check(self):
        name = self.make_old_wav_for_backup()
        self.old_profiles.unlink()  # A test fixture: old SD has no custom profiles.
        mixer_control.change({
            "music": {"bass": 0, "mid": 0, "treble": 0},
            "laptop": {"bass": 0, "mid": 0, "treble": 0}},
            path=self.old_settings, confirmed=True)
        with self.assertRaises(ValueError):
            self.export()  # Standalone export unchanged: reject no customizations.
        self.assertTrue(self.guided_old_backup())
        data, _ = preset_transfer._load(str(self.media))
        self.assertEqual(data["profiles"], {})
        self.assertTrue(all(band == 0 for values in data["eq"].values()
                            for band in values.values()))
        self.assertTrue((self.media / name).exists())
        self.assertTrue(self.sd_check_backup())

    def test_guided_old_backup_source_changed_after_copy_confirmation_refuses_save(self):
        name = self.make_old_wav_for_backup()
        def change_old_before_copy():
            mixer_control.change({"music": {"bass": 9}},
                                 path=self.old_settings, confirmed=True)
            return True
        with self.assertRaises(OSError):
            preset_transfer.backup_guided(
                str(self.media), str(self.old_music), str(self.old),
                confirm_copy=change_old_before_copy, confirm_save=lambda: True,
                require_terminal=False, out=self.logs.append)
        self.assertTrue((self.media / name).exists())
        self.assertFalse((self.media / preset_transfer.FILENAME).exists())

    def test_guided_old_backup_guard_denies_root_and_non_tty(self):
        name = self.make_old_wav_for_backup()
        with mock.patch.object(preset_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.guided_old_backup()
        with mock.patch.object(preset_transfer.sys.stdin, "isatty",
                               return_value=False):
            with self.assertRaises(PermissionError):
                preset_transfer.backup_guided(
                    str(self.media), str(self.old_music), str(self.old))
        self.assertFalse((self.media / name).exists())

    def test_guided_old_backup_cli_and_installed_wrapper_forward_all_three_paths(self):
        with mock.patch.object(preset_transfer, "backup_guided",
                               return_value=True) as call:
            self.assertEqual(preset_transfer.main([
                "backup-guided", str(self.media), str(self.old_music)
                if hasattr(self, "old_music") else str(self.old),
                str(self.old)]), 0)
            self.assertEqual(call.call_args.args[0], str(self.media))
            self.assertEqual(call.call_args.args[2], str(self.old))
        wrapper = (Path(__file__).resolve().parents[1] /
                   "image/stage-audiohub/01-install/files/bin/audiohub-presets-transfer")
        self.assertEqual(subprocess.run(
            ["/bin/sh", "-n", str(wrapper)], capture_output=True).returncode, 0)
        code = wrapper.read_text()
        self.assertIn('check-backup|backup-guided)', code)
        for args in (
            ["backup-guided"], ["backup-guided", "relative", str(self.old), str(self.old)],
            ["backup-guided", str(self.media), "relative", str(self.old)],
            ["backup-guided", str(self.media), str(self.old), "relative"],
            ["backup-guided", str(self.media), str(self.old)],
            ["backup-guided", str(self.media), str(self.old), str(self.old), "extra"]):
            with self.subTest(args=args):
                self.assertEqual(subprocess.run(
                    ["/bin/sh", str(wrapper), *args],
                    capture_output=True, timeout=5).returncode, 2)

    def seed_sd_backup(self):
        self.old_music = self.root / "OldMusic"
        self.new_music = self.root / "NewMusic"
        self.old_music.mkdir(mode=0o700)
        self.new_music.mkdir(mode=0o700)
        self.old_music.chmod(0o700)
        self.new_music.chmod(0o700)
        name = "private-audio.wav"
        with wave.open(str(self.old_music / name), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(b"\x00\x01\x00\x02" * 250)
        (self.old_music / name).chmod(0o600)
        self.assertTrue(music_transfer.transfer(
            "backup", str(self.media), music_dir=str(self.old_music),
            confirm=lambda: True, require_terminal=False, out=self.logs.append))
        self.assertTrue(self.export())
        return name

    def sd_plan(self):
        return preset_transfer.plan_new_sd(
            str(self.media), settings_path=self.new_settings,
            profile_path=self.new_profiles, music_dir=str(self.new_music),
            out=self.logs.append, require_terminal=False)

    def sd_check_new(self):
        return preset_transfer.check_new(
            str(self.media), settings_path=self.new_settings,
            profile_path=self.new_profiles, music_dir=str(self.new_music),
            out=self.logs.append, require_terminal=False)

    def sd_check_backup(self):
        return preset_transfer.check_backup(
            str(self.media), str(self.old_music), str(self.old),
            out=self.logs.append, require_terminal=False)

    def guided(self, copy=True, profiles=True, eq=True):
        return preset_transfer.restore_guided(
            str(self.media), settings_path=self.new_settings,
            profile_path=self.new_profiles, music_dir=str(self.new_music),
            out=self.logs.append, require_terminal=False,
            confirm_copy=lambda: copy, confirm_profiles=lambda: profiles,
            confirm_eq=lambda: eq)

    def test_guided_restores_wav_profiles_eq_with_separate_confirmations(self):
        name = self.seed_sd_backup()
        source = (self.media / name).read_bytes()
        self.assertTrue(self.guided())
        self.assertEqual((self.new_music / name).read_bytes(), source)
        self.assertTrue(self.sd_check_new())
        self.assertEqual(mixer_control.show(path=self.new_settings)["master"], 70)
        self.assertFalse(mixer_control.show(path=self.new_settings)["laptop"]["mute"])
        self.assertEqual(
            mixer_control.list_volume_profiles(path=self.new_profiles)
            ["profiles"]["private-one"]["master"], 20)
        log = "\n".join(self.logs)
        self.assertIn("Step 1/3", log)
        self.assertIn("Step 2/3", log)
        self.assertIn("Step 3/3", log)
        self.assertIn("Guided stored-data migration verified", log)
        self.assertNotIn(name, log)
        self.assertNotIn("private-one", log)
        self.assertNotIn(str(self.root), log)

    def test_guided_preserves_local_profiles_and_active_mixer(self):
        name = self.seed_sd_backup()
        mixer_control.save_volume_profile(
            "local-only", 7, 22, 33, 44,
            path=self.new_profiles, confirmed=True)
        mixer_control.change({"master": 27,
                              "laptop": {"mute": True, "volume": 41}},
                             path=self.new_settings, confirmed=True)
        before = mixer_control.show(path=self.new_settings)
        self.assertTrue(self.guided())
        after = mixer_control.show(path=self.new_settings)
        self.assertEqual(after["master"], before["master"])
        self.assertEqual(after["laptop"]["mute"], before["laptop"]["mute"])
        self.assertEqual(after["laptop"]["volume"], before["laptop"]["volume"])
        saved = mixer_control.list_volume_profiles(path=self.new_profiles)["profiles"]
        self.assertIn("local-only", saved)
        self.assertEqual(saved["local-only"]["master"], 7)
        self.assertIn("private-one", saved)
        self.assertEqual((self.new_music / name).read_bytes(),
                         (self.media / name).read_bytes())
        self.assertTrue(self.sd_check_new())

    def test_guided_cancel_copy_has_zero_destination_writes(self):
        name = self.seed_sd_backup()
        self.assertFalse(self.guided(copy=False))
        self.assertFalse((self.new_music / name).exists())
        self.assertFalse(self.new.exists())
        self.assertTrue((self.media / name).exists())

    def test_guided_cancel_merge_retains_verified_wav_for_restart(self):
        name = self.seed_sd_backup()
        self.assertFalse(self.guided(profiles=False))
        first = self.new_music / name
        self.assertTrue(first.exists())
        inode = first.stat().st_ino
        self.assertFalse(self.new.exists())
        self.assertTrue(self.guided())
        self.assertEqual(first.stat().st_ino, inode)
        self.assertTrue(self.sd_check_new())

    def test_guided_cancel_eq_keeps_wav_and_profiles_without_writing_eq(self):
        name = self.seed_sd_backup()
        self.assertFalse(self.guided(eq=False))
        self.assertTrue((self.new_music / name).exists())
        self.assertTrue(self.new_profiles.exists())
        self.assertFalse(self.new_settings.exists())
        self.assertTrue(self.guided(copy=False, profiles=False, eq=True))
        self.assertTrue(self.sd_check_new())

    def test_guided_conflicting_profiles_block_before_wav_copy(self):
        name = self.seed_sd_backup()
        mixer_control.save_volume_profile(
            "private-one", 99, 15, 15, 15,
            path=self.new_profiles, confirmed=True)
        before = self.new_profiles.read_bytes()
        with self.assertRaises(ValueError):
            self.guided()
        self.assertFalse((self.new_music / name).exists())
        self.assertEqual(self.new_profiles.read_bytes(), before)

    def test_guided_non_neutral_eq_blocks_before_wav_copy(self):
        name = self.seed_sd_backup()
        mixer_control.change({"music": {"bass": 6}},
                             path=self.new_settings, confirmed=True)
        before = self.new_settings.read_bytes()
        with self.assertRaises(ValueError):
            self.guided()
        self.assertFalse((self.new_music / name).exists())
        self.assertEqual(self.new_settings.read_bytes(), before)

    def test_guided_different_wav_collision_blocks_before_other_writes(self):
        name = self.seed_sd_backup()
        target = self.new_music / name
        original = (self.media / name).read_bytes()
        target.write_bytes(original[:-1] + b"\x09")
        target.chmod(0o600)
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            self.guided()
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(self.new.exists())

    def test_guided_idempotent_complete_restore_does_not_change_inodes(self):
        name = self.seed_sd_backup()
        self.assertTrue(self.guided())
        dest = self.new_music / name
        earlier = [x.stat().st_ino for x in
                   (dest, self.new_profiles, self.new_settings)]
        self.assertTrue(self.guided(copy=False, profiles=False, eq=False))
        later = [x.stat().st_ino for x in
                 (dest, self.new_profiles, self.new_settings)]
        self.assertEqual(earlier, later)

    def test_guided_refuses_changed_archive_after_confirmed_wav_copy(self):
        name = self.seed_sd_backup()
        backup = self.media / preset_transfer.FILENAME
        original = backup.read_bytes()
        def altered_during_copy():
            backup.write_bytes(original + b" ")
            backup.chmod(0o600)
            return True
        with self.assertRaises(OSError):
            preset_transfer.restore_guided(
                str(self.media), settings_path=self.new_settings,
                profile_path=self.new_profiles, music_dir=str(self.new_music),
                out=self.logs.append, require_terminal=False,
                confirm_copy=altered_during_copy,
                confirm_profiles=lambda: True, confirm_eq=lambda: True)
        self.assertTrue((self.new_music / name).exists())
        self.assertFalse(self.new.exists())

    def test_guided_rejects_root_or_untrusted_non_tty(self):
        name = self.seed_sd_backup()
        with mock.patch.object(preset_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.guided()
        with mock.patch.object(preset_transfer.sys.stdin, "isatty",
                               return_value=False):
            with self.assertRaises(PermissionError):
                preset_transfer.restore_guided(
                    str(self.media), settings_path=self.new_settings,
                    profile_path=self.new_profiles, music_dir=str(self.new_music))
        self.assertFalse((self.new_music / name).exists())
        self.assertFalse(self.new.exists())

    def test_guided_cli_and_native_launcher_real_dispatch(self):
        with mock.patch.object(preset_transfer, "restore_guided",
                               return_value=True) as call:
            self.assertEqual(preset_transfer.main(
                ["restore-guided", str(self.media)]), 0)
            self.assertEqual(call.call_args.args, (str(self.media),))
        wrapper = (Path(__file__).resolve().parents[1] /
                   "image/stage-audiohub/01-install/files/bin/audiohub-presets-transfer")
        self.assertEqual(subprocess.run(
            ["/bin/sh", "-n", str(wrapper)], capture_output=True).returncode, 0)
        self.assertIn("restore-guided", wrapper.read_text())
        self.assertIn('exec /usr/bin/python3 -m audiohub.preset_transfer "$@"',
                      wrapper.read_text())
        for argv in (["restore-guided"], ["restore-guided", "relative"],
                     ["restore-guided", str(self.media), "--no-confirm"]):
            with self.subTest(argv=argv):
                self.assertEqual(subprocess.run(
                    ["/bin/sh", str(wrapper), *argv],
                    capture_output=True, timeout=5).returncode, 2)

    def test_sd_plan_reveals_missing_wav_profile_and_eq_without_writes(self):
        name = self.seed_sd_backup()
        snapshot = (self.old_settings.read_bytes(), self.old_profiles.read_bytes(),
                    (self.media / name).read_bytes())
        plan = self.sd_plan()
        self.assertEqual(plan["wav_total"], 1)
        self.assertEqual(plan["wav_missing"], 1)
        self.assertEqual(plan["profile_missing"], 1)
        self.assertGreater(plan["eq_bands_different"], 0)
        self.assertFalse(plan["eq_non_neutral_conflict"])
        self.assertFalse(plan["ready_for_final_readonly_check"])
        self.assertTrue(plan["no_files_changed"])
        self.assertFalse(self.new.exists())
        self.assertEqual((self.old_settings.read_bytes(), self.old_profiles.read_bytes(),
                          (self.media / name).read_bytes()), snapshot)
        logs = "\n".join(self.logs)
        self.assertIn("restore PRIVATE_FOLDER --resume", logs)
        self.assertIn("merge-profiles PRIVATE_FOLDER", logs)
        self.assertIn("restore-eq PRIVATE_FOLDER", logs)
        self.assertNotIn(name, logs)
        self.assertNotIn(str(self.root), logs)

    def test_sd_readonly_backup_check_and_full_new_sd_verify(self):
        name = self.seed_sd_backup()
        self.assertTrue(self.sd_check_backup())
        self.assertFalse(self.new.exists())
        self.assertTrue(music_transfer.transfer(
            "restore", str(self.media), music_dir=str(self.new_music),
            confirm=lambda: True, require_terminal=False, out=self.logs.append))
        self.assertEqual(self.sd_plan()["wav_matched"], 1)
        self.assertFalse(self.sd_plan()["ready_for_final_readonly_check"])
        self.assertTrue(self.merge())
        self.assertTrue(self.import_eq())
        plan = self.sd_plan()
        self.assertTrue(plan["ready_for_final_readonly_check"])
        before = ((self.new_music / name).stat().st_ino,
                  self.new_profiles.stat().st_ino,
                  self.new_settings.stat().st_ino)
        self.assertTrue(self.sd_check_new())
        self.assertEqual(((self.new_music / name).stat().st_ino,
                          self.new_profiles.stat().st_ino,
                          self.new_settings.stat().st_ino), before)
        self.assertIn("New SD data check passed", "\n".join(self.logs))

    def test_sd_backup_check_fails_if_old_settings_changed_since_export(self):
        self.seed_sd_backup()
        self.assertTrue(self.sd_check_backup())
        mixer_control.change({"music": {"bass": 4}},
                             path=self.old_settings, confirmed=True)
        with self.assertRaises(ValueError):
            self.sd_check_backup()
        self.assertFalse(self.new.exists())

    def test_sd_backup_check_refuses_missing_or_changed_wav(self):
        name = self.seed_sd_backup()
        (self.media / name).unlink()  # Test fixture only.
        with self.assertRaises(FileNotFoundError):
            self.sd_check_backup()
        self.assertFalse(self.new.exists())

    def test_sd_new_check_refuses_incomplete_data(self):
        self.seed_sd_backup()
        with self.assertRaises(FileNotFoundError):
            self.sd_check_new()
        self.assertTrue(music_transfer.transfer(
            "restore", str(self.media), music_dir=str(self.new_music),
            confirm=lambda: True, require_terminal=False, out=self.logs.append))
        with self.assertRaises(ValueError):
            self.sd_check_new()
        self.assertFalse(self.new.exists())

    def test_sd_plan_rejects_colliding_wav_without_modifying_either(self):
        name = self.seed_sd_backup()
        target = self.new_music / name
        target.write_bytes((self.media / name).read_bytes() + b"changed")
        target.chmod(0o600)
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            self.sd_plan()
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(self.new.exists())

    def test_sd_plan_reports_existing_profile_conflicts_and_non_neutral_eq(self):
        self.seed_sd_backup()
        mixer_control.save_volume_profile(
            "private-one", 66, 66, 66, 66,
            path=self.new_profiles, confirmed=True)
        mixer_control.change({"music": {"bass": 8}},
                             path=self.new_settings, confirmed=True)
        profiles_before = self.new_profiles.read_bytes()
        mixer_before = self.new_settings.read_bytes()
        result = self.sd_plan()
        self.assertEqual(result["profile_conflicts"], 1)
        self.assertTrue(result["eq_non_neutral_conflict"])
        self.assertFalse(result["ready_for_final_readonly_check"])
        self.assertEqual(self.new_profiles.read_bytes(), profiles_before)
        self.assertEqual(self.new_settings.read_bytes(), mixer_before)
        self.assertIn("BLOCKED", "\n".join(self.logs))

    def test_sd_plan_allows_extra_local_profiles_without_misleading_failure(self):
        name = self.seed_sd_backup()
        self.assertTrue(music_transfer.transfer(
            "restore", str(self.media), music_dir=str(self.new_music),
            confirm=lambda: True, require_terminal=False, out=self.logs.append))
        mixer_control.save_volume_profile(
            "extra-local", 10, 10, 10, 10,
            path=self.new_profiles, confirmed=True)
        self.assertTrue(self.merge())
        self.assertTrue(self.import_eq())
        self.assertTrue(self.sd_plan()["ready_for_final_readonly_check"])
        self.assertTrue(self.sd_check_new())
        self.assertTrue((self.new_music / name).exists())

    def test_sd_checks_reject_privileged_or_nonlocal_console(self):
        self.seed_sd_backup()
        with mock.patch.object(preset_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.sd_plan()
            with self.assertRaises(PermissionError):
                self.sd_check_backup()
            with self.assertRaises(PermissionError):
                self.sd_check_new()
        with mock.patch.object(preset_transfer.sys.stdin, "isatty",
                               return_value=False):
            with self.assertRaises(PermissionError):
                preset_transfer.plan_new_sd(
                    str(self.media), settings_path=self.new_settings,
                    profile_path=self.new_profiles, music_dir=str(self.new_music))
        self.assertFalse(self.new.exists())

    def test_sd_cli_wiring_installed_launcher_and_readonly_guards(self):
        with mock.patch.object(preset_transfer, "plan_new_sd",
                               return_value={"wav_total": 1}) as plan:
            self.assertEqual(preset_transfer.main(["plan-new", str(self.media)]), 0)
            self.assertEqual(plan.call_args.args, (str(self.media),))
        with mock.patch.object(preset_transfer, "check_new", return_value=True):
            self.assertEqual(preset_transfer.main(["check-new", str(self.media)]), 0)
        with mock.patch.object(preset_transfer, "check_backup",
                               return_value=True) as check:
            self.assertEqual(preset_transfer.main(
                ["check-backup", str(self.media), str(self.old), str(self.old)]), 0)
            self.assertEqual(check.call_args.args,
                             (str(self.media), str(self.old), str(self.old)))
        script = (Path(__file__).resolve().parents[1] /
                  "image/stage-audiohub/01-install/files/bin/audiohub-presets-transfer")
        self.assertEqual(subprocess.run(
            ["/bin/sh", "-n", str(script)], capture_output=True).returncode, 0)
        text = script.read_text()
        for name in ("plan-new", "check-new", "check-backup"):
            self.assertIn(name, text)
        for invalid in (["check-backup", str(self.media), "relative", str(self.old)],
                        ["check-backup", str(self.media), str(self.old), "relative"],
                        ["check-new", "relative"],
                        ["plan-new", str(self.media), "extra"]):
            self.assertEqual(subprocess.run(
                ["/bin/sh", str(script), *invalid], capture_output=True,
                timeout=5).returncode, 2)

    def test_export_restore_verify_preserves_active_volume_and_never_moves_owner_data(self):
        saved_settings = self.old_settings.read_bytes()
        saved_profiles = self.old_profiles.read_bytes()
        self.assertTrue(self.export())
        archive = self.media / preset_transfer.FILENAME
        data = json.loads(archive.read_text())
        self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)
        self.assertEqual(set(data), {"schema", "eq", "profiles"})
        self.assertEqual(data["eq"]["music"]["bass"], 3)
        self.assertEqual(data["profiles"]["private-one"]["master"], 20)
        for forbidden in ('"wifi"', '"bluetooth"', '"owner_key"', '"password"',
                          '"mute"', '"volume"', '"device"', '"pairing"'):
            self.assertNotIn(forbidden, archive.read_text())
        self.assertEqual(self.old_settings.read_bytes(), saved_settings)
        self.assertEqual(self.old_profiles.read_bytes(), saved_profiles)
        self.assertTrue(self.preview())
        self.assertFalse(self.new.exists())
        self.assertTrue(self.import_profiles())
        self.assertFalse(self.new_settings.exists())
        self.assertEqual(mixer_control.show(path=self.new_settings), defaults())
        self.assertTrue(self.import_eq())
        current = mixer_control.show(path=self.new_settings)
        self.assertEqual(current["master"], 70)
        self.assertEqual(current["music"]["volume"], 65)
        self.assertFalse(current["laptop"]["mute"])
        self.assertEqual(current["music"]["bass"], 3)
        self.assertTrue(self.verify())
        self.assertNotIn("private-one", "\n".join(self.logs))
        self.assertNotIn(str(self.root), "\n".join(self.logs))

    def test_cancelled_export_and_import_create_no_transfer_files(self):
        self.assertFalse(self.export(False))
        self.assertEqual(list(self.media.iterdir()), [])
        self.assertTrue(self.export())
        self.assertFalse(self.import_profiles(False))
        self.assertFalse(self.import_eq(False))
        self.assertFalse(self.new.exists())

    def test_existing_archive_and_custom_destination_are_never_overwritten(self):
        archive = self.media / preset_transfer.FILENAME
        archive.write_text("existing")
        archive.chmod(0o600)
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(archive.read_text(), "existing")
        archive.unlink()  # Test fixture only.
        self.assertTrue(self.export())
        mixer_control.save_volume_profile(
            "new-device", 11, 11, 11, 11, path=self.new_profiles, confirmed=True)
        before = self.new_profiles.read_bytes()
        with self.assertRaises(FileExistsError):
            self.import_profiles()
        self.assertEqual(self.new_profiles.read_bytes(), before)

    def test_restore_eq_never_replaces_non_neutral_destination(self):
        self.assertTrue(self.export())
        mixer_control.change({"music": {"bass": 8}},
                             path=self.new_settings, confirmed=True)
        before = self.new_settings.read_bytes()
        with self.assertRaises(ValueError):
            self.import_eq()
        self.assertEqual(self.new_settings.read_bytes(), before)

    def test_readonly_backup_media_and_symlink_archive(self):
        self.assertTrue(self.export())
        self.media.chmod(0o500)
        self.assertTrue(self.preview())
        self.assertTrue(self.import_profiles())
        self.assertTrue(self.import_eq())
        self.assertTrue(self.verify())
        self.media.chmod(0o700)
        archive = self.media / preset_transfer.FILENAME
        archive.unlink()  # Test fixture only.
        archive.symlink_to(self.old_settings)
        with self.assertRaises(OSError):
            self.preview()

    def test_invalid_archive_members_and_range_fail_closed(self):
        archive = self.media / preset_transfer.FILENAME
        good, _ = preset_transfer._source_snapshot(
            self.old_settings, self.old_profiles)
        cases = [
            '{"schema":"audiohub-portable-presets/1","schema":"other"}',
            '{"schema":"audiohub-portable-presets/1","eq":{},"profiles":{}}',
            json.dumps({**good, "wifi_password": "SECRET"}),
            json.dumps({**good, "eq": {**good["eq"], "music": {
                **good["eq"]["music"], "bass": 500}}}),
            json.dumps({**good, "profiles": {"unsafe": {
                "master": True, "music": 20, "laptop": 20, "tablet": 20}}}),
        ]
        for raw in cases:
            with self.subTest(case=raw[:40]):
                archive.write_text(raw)
                archive.chmod(0o600)
                with self.assertRaises((ValueError, mixer_control.MixerControlUnavailable)):
                    self.preview()
                self.assertFalse(self.new.exists())

    def test_verify_missing_inactive_profiles_and_eq_never_writes(self):
        self.assertTrue(self.export())
        with self.assertRaises(ValueError):
            self.verify()
        self.assertFalse(self.new.exists())
        self.assertTrue(self.import_profiles())
        with self.assertRaises(ValueError):
            self.verify()
        self.assertFalse(self.new_settings.exists())

    def test_matching_eq_is_idempotent_without_new_file_generation(self):
        self.assertTrue(self.export())
        self.assertTrue(self.import_eq())
        before = self.new_settings.read_bytes()
        ino = self.new_settings.stat().st_ino
        self.assertTrue(self.import_eq())
        self.assertEqual(self.new_settings.read_bytes(), before)
        self.assertEqual(self.new_settings.stat().st_ino, ino)

    def test_concurrent_change_rejects_stale_eq_commit(self):
        self.assertTrue(self.export())
        original = mixer_control.change

        def interleave(patch, *, path, confirmed, if_revision):
            original({"master": 11}, path=path, confirmed=True)
            return original(patch, path=path, confirmed=confirmed,
                            if_revision=if_revision)
        with mock.patch.object(preset_transfer.mixer_control, "change",
                               side_effect=interleave):
            with self.assertRaises(mixer_control.StaleMixerPreview):
                self.import_eq()
        self.assertEqual(mixer_control.show(
            path=self.new_settings)["music"]["bass"], 0)

    def test_root_and_missing_tty_are_rejected(self):
        with mock.patch.object(preset_transfer.os, "geteuid", return_value=0):
            with self.assertRaises(PermissionError):
                self.export()
        with mock.patch.object(preset_transfer.sys.stdin, "isatty",
                               return_value=False):
            with self.assertRaises(PermissionError):
                preset_transfer.export_presets(
                    str(self.media), settings_path=self.old_settings,
                    profile_path=self.old_profiles)
        self.assertEqual(list(self.media.iterdir()), [])

    def test_native_wrapper_and_rootfs_installer_integration(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "image/stage-audiohub/01-install/files/bin/audiohub-presets-transfer"
        self.assertEqual(subprocess.run(
            ["/bin/sh", "-n", str(script)], capture_output=True).returncode, 0)
        self.assertIn("audiohub.preset_transfer", script.read_text())
        self.assertIn('exec /usr/bin/python3 -m audiohub.preset_transfer "$@"', script.read_text())
        self.assertIn("export-old", script.read_text())
        self.assertNotIn("sudo ", script.read_text())
        self.assertNotIn("eval ", script.read_text())
        for args in ([], ["export"], ["bad", "/tmp"],
                     ["verify", "relative"], ["export", "/tmp", "--wrong"],
                     ["export-old", "relative", "/tmp"],
                     ["export-old", "/tmp", "relative"]):
            with self.subTest(args=args):
                self.assertEqual(subprocess.run(
                    ["/bin/sh", str(script), *args],
                    capture_output=True, timeout=5).returncode, 2)
        install = (root / "image/stage-audiohub/01-install/00-run.sh").read_text()
        audit = (root / "image/stage-audiohub/02-audit/00-run.sh").read_text()
        self.assertIn("install -m755 files/bin/audiohub-presets-transfer", install)
        self.assertIn("audiohub-presets-transfer --help", install)
        self.assertIn("test -x", audit)
        self.assertIn("audiohub-presets-transfer", audit)

    def test_first_migration_from_readonly_old_sd_uses_only_old_config(self):
        self.old.chmod(0o500)
        self.assertTrue(preset_transfer.export_presets(
            str(self.media), settings_path=self.old_settings,
            profile_path=self.old_profiles, confirm=lambda: True,
            out=self.logs.append, require_terminal=False))
        self.assertTrue((self.media / preset_transfer.FILENAME).exists())
        self.old.chmod(0o700)
        with mock.patch.object(preset_transfer, "export_presets",
                               return_value=True) as exported:
            self.assertEqual(preset_transfer.main(
                ["export-old", str(self.old), str(self.media)]), 0)
            self.assertEqual(exported.call_args.args, (str(self.media),))
            self.assertEqual(exported.call_args.kwargs["settings_path"],
                             self.old / "settings.json")
            self.assertEqual(exported.call_args.kwargs["profile_path"],
                             self.old / "volume-profiles.json")
        self.assertEqual(preset_transfer.main(
            ["export-old", "relative", str(self.media)]), 2)
        self.assertEqual(preset_transfer.main(
            ["export-old", str(self.old), "relative"]), 2)

    def test_cli_help_is_offline_and_commands_are_explicit(self):
        with mock.patch("builtins.print") as output:
            self.assertEqual(preset_transfer.main(["--help"]), 0)
        self.assertIn("If BOTH protected music folders are empty",
                      " ".join(str(x) for x in output.call_args_list))
        self.assertEqual(preset_transfer.main(["--help"]), 0)
        self.assertEqual(preset_transfer.main([]), 2)
        self.assertEqual(preset_transfer.main(["verify", "relative", "bad"]), 2)


if __name__ == "__main__":
    unittest.main()
