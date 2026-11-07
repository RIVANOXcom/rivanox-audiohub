"""Offline AudioHub mixer controls: private atomic file only, never actual audio."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import mixer_control
from audiohub.mixer import defaults


class LocalMixerControlsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.settings = self.root / "audiohub" / "settings.json"

    def test_read_only_show_is_default_and_creates_nothing(self):
        current = mixer_control.show(path=self.settings)
        self.assertEqual(current, defaults())
        self.assertFalse(self.settings.parent.exists())

    def test_explicit_change_writes_private_atomic_file_and_keeps_other_channels(self):
        self.assertEqual(mixer_control.change({"master": 35}, path=self.settings,
                                              confirmed=True)["master"], 35)
        self.assertEqual(mixer_control.change(
            {"music": {"volume": 12}}, path=self.settings, confirmed=True
        )["music"]["volume"], 12)
        latest = mixer_control.change({"tablet": {"mute": True}},
                                      path=self.settings, confirmed=True)
        self.assertEqual(latest["master"], 35)
        self.assertEqual(latest["music"]["volume"], 12)
        self.assertTrue(latest["tablet"]["mute"])
        self.assertFalse(latest["laptop"]["mute"])
        self.assertEqual(mixer_control.show(path=self.settings), latest)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.settings.parent.stat().st_mode), 0o700)
        self.assertEqual(self.settings.stat().st_nlink, 1)
        self.assertEqual(stat.S_IMODE(
            (self.settings.parent / mixer_control.LOCK_NAME).stat().st_mode
        ), 0o600)
        self.assertEqual(set(self.settings.parent.iterdir()),
                         {self.settings, self.settings.parent / mixer_control.LOCK_NAME})

    def test_no_confirmation_or_root_cannot_create_files(self):
        with self.assertRaisesRegex(mixer_control.MixerControlUnavailable, "confirmation"):
            mixer_control.change({"master": 80}, path=self.settings)
        with mock.patch("audiohub.mixer_control.os.geteuid", return_value=0):
            with self.assertRaisesRegex(mixer_control.MixerControlUnavailable,
                                        "unprivileged"):
                mixer_control.change({"master": 80}, path=self.settings, confirmed=True)
            with self.assertRaisesRegex(mixer_control.MixerControlUnavailable,
                                        "unprivileged"):
                mixer_control.show(path=self.settings)
        self.assertFalse(self.settings.parent.exists())

    def test_invalid_value_cannot_replace_valid_setting(self):
        mixer_control.change({"master": 57}, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        for patch in ({"master": -1}, {"master": 101}, {"master": True},
                      {"music": {"volume": 200}}, {"tablet": {"mute": "yes"}},
                      {"wifi_password": "PRIVATE-SECRET"},
                      {"music": {"bass": float("nan")}}):
            with self.subTest(patch=repr(patch)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change(patch, path=self.settings, confirmed=True)
                self.assertEqual(self.settings.read_bytes(), before)
        self.assertNotIn(b"PRIVATE-SECRET", before)

    def test_corrupt_or_unreviewed_state_never_replaced_by_defaults(self):
        self.settings.parent.mkdir(mode=0o700)
        for payload in (
            b"{", b'{"master": 25, "master": 80}',
            b'{"master": 31, "unexpected": "SECRET"}',
            b'{"master": 80, "music": {"mute": "heard"}}',
        ):
            with self.subTest(payload=payload[:40]):
                self.settings.write_bytes(payload)
                self.settings.chmod(0o600)
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
                self.assertEqual(self.settings.read_bytes(), payload)

    def test_untrusted_symlinks_and_permissions_do_not_destroy_target(self):
        other = self.root / "protected.json"
        other.write_text("PRIVATE-OWNER")
        self.settings.parent.mkdir(mode=0o700)
        self.settings.symlink_to(other)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"master": 25}, path=self.settings, confirmed=True)
        self.assertEqual(other.read_text(), "PRIVATE-OWNER")
        self.settings.unlink()
        self.settings.write_text(json.dumps(defaults()))
        self.settings.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"master": 25}, path=self.settings, confirmed=True)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o644)

    def test_raced_lock_symlink_is_rejected_before_writing(self):
        self.settings.parent.mkdir(mode=0o700)
        other = self.root / "outside"
        other.write_text("PRIVATE-PROTECTED")
        (self.settings.parent / mixer_control.LOCK_NAME).symlink_to(other)
        with self.assertRaises(OSError):
            mixer_control.change({"master": 60}, path=self.settings, confirmed=True)
        self.assertEqual(other.read_text(), "PRIVATE-PROTECTED")
        self.assertFalse(self.settings.exists())

    def test_two_concurrent_local_writers_keep_both_user_changes(self):
        def update(request):
            return mixer_control.change(request, path=self.settings, confirmed=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [
                pool.submit(update, {"music": {"volume": 33}}),
                pool.submit(update, {"tablet": {"mute": True}}),
            ]
            for future in tasks:
                future.result(timeout=8)
        result = mixer_control.show(path=self.settings)
        self.assertEqual(result["music"]["volume"], 33)
        self.assertTrue(result["tablet"]["mute"])
        self.assertEqual(result["master"], defaults()["master"])

    def test_cli_defaults_are_read_only_and_mutation_needs_flag(self):
        with mock.patch("audiohub.mixer_control.show", return_value=defaults()) as show:
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["show"])
            self.assertIn('"master": 70', output.getvalue())
            show.assert_called_once_with()
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["set-master", "40"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with({"master": 40}, confirmed=False)
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-volume", "laptop", "45"
                ])
            change.assert_called_once_with({"laptop": {"volume": 45}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "mute", "tablet", "on"
                ])
            change.assert_called_once_with({"tablet": {"mute": True}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change") as change:
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-volume", "unknown", "50"
                ])
            change.assert_not_called()

    def test_computed_supervisor_commands_reflect_saved_levels_and_mutes(self):
        from audiohub.mixer import volume_commands
        mixer_control.change({"master": 20, "music": {"volume": 14},
                              "tablet": {"mute": True}},
                             path=self.settings, confirmed=True)
        current = mixer_control.show(path=self.settings)
        commands = volume_commands(current, {"music": 31, "tablet": 33}, 11)
        self.assertEqual(commands[0][:3], ["wpctl", "set-volume", "11"])
        self.assertIn(["wpctl", "set-volume", "31", "0.14"], commands)
        self.assertIn(["wpctl", "set-mute", "33", "1"], commands)
        self.assertTrue(all(isinstance(a, list) for a in commands))


if __name__ == "__main__":
    unittest.main()
