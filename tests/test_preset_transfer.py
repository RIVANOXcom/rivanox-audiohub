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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import mixer_control, preset_transfer
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
        self.assertEqual(preset_transfer.main(["--help"]), 0)
        self.assertEqual(preset_transfer.main([]), 2)
        self.assertEqual(preset_transfer.main(["verify", "relative", "bad"]), 2)


if __name__ == "__main__":
    unittest.main()
