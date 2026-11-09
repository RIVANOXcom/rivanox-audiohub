"""Offline Pi/Windows key-copy comparison; no credential creation or network."""
import hashlib
import hmac
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import key_onboarding as keys
from audiohub import secure_lan
from audiohub import windows_bridge_setup as setup
from audiohub import windows_bridge_gui as gui


class OfflineKeyComparisonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "bench-key"
        self.secret = bytes(range(32))
        self.path.write_bytes(self.secret)
        if os.name == "posix":
            self.path.chmod(0o600)
        self.code = hmac.new(self.secret, keys.CHECK_DOMAIN,
                             hashlib.sha256).hexdigest()[:32]

    def test_same_full_entropy_key_produces_matching_private_code(self):
        self.assertEqual(keys.local_key_code(self.path), self.code)
        self.assertEqual(keys.code_from_key_bytes(self.secret), self.code)
        self.assertTrue(keys.verify_local_key_code(self.path, self.code))
        self.assertTrue(keys.verify_key_bytes(self.secret, self.code))

    def test_mismatch_including_changed_key_fails_without_network(self):
        for bad in ("0" * 32, "F" * 32, self.code[:-1], "", " " + self.code,
                    None, 123):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                keys.verify_local_key_code(self.path, bad)
        with self.assertRaises(ValueError):
            keys.verify_key_bytes(b"wrong", self.code)
        with mock.patch.object(secure_lan.socket, "create_connection") as dial:
            with self.assertRaises(ValueError):
                setup.validate_local_setup(
                    "192.168.10.30", "f" * 64, str(self.path), 10,
                    expected_key_code="f" * 32)
            dial.assert_not_called()

    def test_reject_relative_linked_and_unreadable_or_invalid_files(self):
        with self.assertRaises(ValueError):
            keys.local_key_code("bench-key")
        link = self.path.parent / "linked"
        try:
            link.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest("No symlinks on this platform")
        with self.assertRaises(ValueError):
            keys.local_key_code(link)
        self.path.write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            keys.local_key_code(self.path)
        self.path.write_bytes(self.secret)
        if os.name == "posix":
            self.path.chmod(0o644)
            with self.assertRaises(ValueError):
                keys.local_key_code(self.path)

    def test_cli_local_code_revealed_only_by_explicit_offline_action(self):
        with mock.patch.object(secure_lan.socket, "create_connection") as dial, \
             mock.patch("builtins.print") as output:
            result = setup.main(["--show-key-code", str(self.path)])
            self.assertEqual(result, 0)
            dial.assert_not_called()
        rendered = "\n".join(str(call.args[0]) for call in output.call_args_list)
        self.assertIn(self.code, rendered)
        self.assertIn("NOT authentication", rendered)
        self.assertNotIn(str(self.path), rendered)
        self.assertNotIn(self.secret.hex(), rendered)

    def test_runtime_checks_actual_loaded_key_before_first_socket(self):
        with mock.patch.object(secure_lan.socket, "create_connection") as dial:
            with self.assertRaises(ValueError):
                secure_lan.run_bridge(
                    server_ip="192.168.10.30", port=secure_lan.DEFAULT_PORT,
                    udp_port=secure_lan.DEFAULT_UDP_PORT,
                    key_file=str(self.path), pin_sha256="f" * 64,
                    session_minutes=1, isolated_lab=True,
                    expected_key_code="f" * 32)
            dial.assert_not_called()

    def test_cli_manual_session_rechecks_expected_code_without_logging_it(self):
        answers = iter(["192.168.10.30", "f" * 64, str(self.path), "10", "ISOLATED"])
        execute = mock.Mock(return_value=4)
        output = []
        self.assertEqual(setup.interactive_bridge(
            input_fn=lambda _: next(answers), output=output.append,
            execute=execute, expected_key_code=self.code), 0)
        self.assertEqual(execute.call_args.kwargs["expected_key_code"], self.code)
        text = "\n".join(output)
        self.assertNotIn(self.code, text)
        self.assertNotIn(str(self.path), text)
        answers = iter(["192.168.10.30", "f" * 64, str(self.path), "10"])
        with self.assertRaises(ValueError):
            setup.interactive_bridge(input_fn=lambda _: next(answers),
                                     output=output.append, execute=execute,
                                     check_only=True, expected_key_code="f" * 32)
        self.assertEqual(execute.call_count, 1)

    def test_gui_key_code_is_optional_but_mismatch_blocks_offline(self):
        args = ("192.168.10.30", "f" * 64, str(self.path), "10")
        self.assertEqual(gui.validate_fields(*args, expected_key_code=self.code),
                         (args[0], args[1], args[2], 10))
        with mock.patch.object(secure_lan.socket, "create_connection") as dial:
            with self.assertRaises(ValueError):
                gui.validate_fields(*args, expected_key_code="f" * 32)
            dial.assert_not_called()


if __name__ == "__main__":
    unittest.main()
