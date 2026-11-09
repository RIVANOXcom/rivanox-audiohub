"""Staged rotation preflight tests – real filesystem, zero network or writes."""
import hashlib
import hmac
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import key_onboarding as codes
from audiohub import key_rotation as rotation
from audiohub import secure_lan
from audiohub import windows_bridge_setup as cli
from audiohub import windows_bridge_gui as gui


class StagedRotationOfflineTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.directory = Path(td.name)
        self.current = self.directory / "current.bin"
        self.staged = self.directory / "staged.bin"
        self.old_secret = bytes(range(32))
        self.new_secret = bytes(range(32, 64))
        self.current.write_bytes(self.old_secret)
        self.staged.write_bytes(self.new_secret)
        if os.name == "posix":
            self.current.chmod(0o600)
            self.staged.chmod(0o600)
        self.old_code = codes.code_from_key_bytes(self.old_secret)
        self.new_code = codes.code_from_key_bytes(self.new_secret)

    def assess(self, **kw):
        args = {
            "current_path": self.current,
            "staged_path": self.staged,
            "current_pi_code": self.old_code,
            "staged_pi_code": self.new_code,
        }
        args.update(kw)
        return rotation.inspect_staged_rotation(**args)

    def test_two_distinct_verified_copies_pass_without_changes_or_identifiers(self):
        old_bytes = self.current.read_bytes()
        new_bytes = self.staged.read_bytes()
        with mock.patch.object(secure_lan.socket, "create_connection") as dial, \
             mock.patch.object(secure_lan.socket, "socket") as socket_new:
            result = self.assess()
            dial.assert_not_called()
            socket_new.assert_not_called()
        self.assertEqual(result["classification"], "OFFLINE_STAGING_CHECK_ONLY")
        self.assertTrue(result["old_copy_matches_claimed_pi_code"])
        self.assertTrue(result["staged_copy_matches_claimed_pi_code"])
        for item in ("changes_applied", "network_tested", "device_owner_verified",
                     "rotation_approved", "release_ready"):
            self.assertFalse(result[item])
        text = str(result)
        self.assertNotIn(str(self.current), text)
        self.assertNotIn(str(self.staged), text)
        self.assertNotIn(self.old_code, text)
        self.assertNotIn(self.new_code, text)
        self.assertNotIn(self.old_secret.hex(), text)
        self.assertNotIn(self.new_secret.hex(), text)
        self.assertEqual(self.current.read_bytes(), old_bytes)
        self.assertEqual(self.staged.read_bytes(), new_bytes)

    def test_wrong_old_or_staged_pi_code_rejected(self):
        with self.assertRaises(ValueError):
            self.assess(current_pi_code="f" * 32)
        with self.assertRaises(ValueError):
            self.assess(staged_pi_code="f" * 32)
        with self.assertRaises(ValueError):
            self.assess(current_pi_code="F" * 32)
        with self.assertRaises(ValueError):
            self.assess(staged_pi_code="")
        with self.assertRaises(ValueError):
            self.assess(current_pi_code=None)

    def test_reused_new_key_and_codes_are_not_rotation(self):
        with self.assertRaises(ValueError):
            self.assess(staged_pi_code=self.old_code)
        self.staged.write_bytes(self.old_secret)
        with self.assertRaises(ValueError):
            self.assess(staged_pi_code=self.new_code)
        with self.assertRaises(ValueError):
            self.assess(staged_pi_code=self.old_code)

    def test_identical_path_and_hardlink_refused(self):
        with self.assertRaises(ValueError):
            self.assess(staged_path=self.current)
        hard = self.directory / "duplicate"
        try:
            os.link(self.current, hard)
        except (OSError, NotImplementedError):
            self.skipTest("Hardlinks unavailable")
        with self.assertRaises(ValueError):
            self.assess(staged_path=hard)

    def test_symlink_and_bad_modes_and_wrong_size_refused(self):
        link = self.directory / "linked-new"
        try:
            link.symlink_to(self.staged)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable")
        with self.assertRaises(ValueError):
            self.assess(staged_path=link)
        self.staged.write_bytes(b"x" * 31)
        with self.assertRaises(ValueError):
            self.assess()
        if os.name == "posix":
            self.staged.write_bytes(self.new_secret)
            self.staged.chmod(0o644)
            with self.assertRaises(ValueError):
                self.assess()

    def test_interactive_prompts_hide_pi_codes_and_do_not_print_paths(self):
        paths = iter((str(self.current), str(self.staged)))
        private_codes = iter((self.old_code, self.new_code))
        output = []
        with mock.patch.object(secure_lan.socket, "create_connection") as dial:
            answer = rotation.interactive_preflight(
                input_fn=lambda _: next(paths),
                secret_input_fn=lambda _: next(private_codes),
                output=output.append,
            )
            self.assertEqual(answer, 0)
            dial.assert_not_called()
        rendered = "\n".join(output)
        self.assertIn("PREVIEW", rendered)
        self.assertIn("PASS", rendered)
        for forbidden in (self.old_code, self.new_code,
                          str(self.current), str(self.staged),
                          self.old_secret.hex(), self.new_secret.hex()):
            self.assertNotIn(forbidden, rendered)

    def test_windows_cli_mode_invokes_only_offline_rotation(self):
        with mock.patch.object(cli.key_rotation, "interactive_preflight",
                               return_value=0) as preflight, \
             mock.patch.object(secure_lan.socket, "create_connection") as dial:
            self.assertEqual(cli.main(["--rotation-preflight"]), 0)
            preflight.assert_called_once_with()
            dial.assert_not_called()

    def test_gui_helper_refuses_busy_and_bad_pair(self):
        fake = gui.BridgeWindow.__new__(gui.BridgeWindow)
        fake.closing = False
        fake.worker = None
        fake.entries = {"key": mock.Mock(get=mock.Mock(return_value=str(self.current)))}
        self.assertEqual(fake._assess_rotation(
            str(self.staged), self.old_code, self.new_code,
        )["classification"], rotation.CLASSIFICATION)
        with self.assertRaises(ValueError):
            fake._assess_rotation(str(self.staged), self.old_code, "0" * 32)
        fake.closing = True
        with self.assertRaises(ValueError):
            fake._assess_rotation(str(self.staged), self.old_code, self.new_code)
        fake.closing = False
        fake.worker = mock.Mock(is_alive=mock.Mock(return_value=True))
        with self.assertRaises(ValueError):
            fake._assess_rotation(str(self.staged), self.old_code, self.new_code)


if __name__ == "__main__":
    unittest.main()
