"""Offline tests for guided Windows bridge setup without socket access."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import windows_bridge_setup as setup


class WindowsBridgeSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "private.bin"
        self.key.write_bytes(os.urandom(32))
        if os.name == "posix":
            self.key.chmod(0o600)
        self.pin = "a" * 64

    def _answers(self, *, confirmation="ISOLATED", minutes="", ip="192.168.10.30",
                 pin=None, key=None):
        answers = [ip, self.pin if pin is None else pin,
                   str(self.key) if key is None else key, minutes, confirmation]
        it = iter(answers)
        return lambda prompt: next(it)

    def test_operator_confirms_before_one_limited_bridge_session(self):
        executed = mock.Mock(return_value=17)
        output = []
        status = setup.interactive_bridge(
            input_fn=self._answers(), output=output.append, execute=executed)
        self.assertEqual(status, 0)
        executed.assert_called_once_with(
            server_ip="192.168.10.30", port=4044, udp_port=4010,
            key_file=str(self.key), pin_sha256=self.pin,
            session_minutes=10, isolated_lab=True)
        joined = "\n".join(output)
        self.assertNotIn(str(self.key), joined)
        self.assertNotIn(self.pin, joined)
        self.assertNotIn(self.key.read_bytes().hex(), joined)
        self.assertIn("17", joined)

    def test_preflight_without_ports_or_confirmation(self):
        executed = mock.Mock()
        output = []
        status = setup.interactive_bridge(
            input_fn=self._answers(), output=output.append,
            execute=executed, check_only=True)
        self.assertEqual(status, 0)
        executed.assert_not_called()
        self.assertTrue(any("no TCP/UDP listener" in line for line in output))

    def test_cancel_refuses_network(self):
        for answer in ("", "yes", "isolated", "ISOLATED "):
            with self.subTest(answer=answer):
                executed = mock.Mock()
                result = setup.interactive_bridge(
                    input_fn=self._answers(confirmation=answer),
                    output=lambda _: None, execute=executed)
                # Whitespace around explicit marker is accepted; exact case remains.
                if answer.strip() == "ISOLATED":
                    self.assertEqual(result, 0)
                    executed.assert_called_once()
                else:
                    self.assertEqual(result, 1)
                    executed.assert_not_called()

    def test_invalid_pin_duration_and_missing_key_never_connect(self):
        for opts in (
            {"pin": "b" * 63},
            {"minutes": "0"},
            {"minutes": "31"},
            {"minutes": "1.5"},
            {"minutes": "-1"},
            {"key": "/does/not/exist"},
            {"ip": "0.0.0.0"},
            {"ip": "8.8.8.8"},
        ):
            with self.subTest(opts=opts):
                executed = mock.Mock()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    setup.interactive_bridge(
                        input_fn=self._answers(**opts),
                        output=lambda _: None, execute=executed)
                executed.assert_not_called()

    def test_python_tls_capability_gate_is_pre_network(self):
        with mock.patch.object(setup.ssl, "HAS_TLSv1_3", False):
            with self.assertRaises(RuntimeError):
                setup.check_python_tls()
        self.assertEqual(setup._read_minutes(""), 10)
        self.assertEqual(setup._read_minutes(" 30 "), 30)
        for value in ("false", "1.5", "31", "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                setup._read_minutes(value)

    def test_secret_symlink_or_insecure_permission_refused(self):
        link = Path(self.tmp.name) / "linked"
        try:
            link.symlink_to(self.key)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            setup.validate_local_setup("192.168.10.30", self.pin, str(link), 10)
        if os.name == "posix":
            self.key.chmod(0o644)
            with self.assertRaises(ValueError):
                setup.validate_local_setup("192.168.10.30", self.pin, str(self.key), 10)

    def test_unsupported_python_reports_no_false_end_to_end_claim(self):
        with mock.patch.object(setup.sys, "version_info", (3, 10)):
            with self.assertRaisesRegex(RuntimeError, "3.11"):
                setup.check_python_tls()


if __name__ == "__main__":
    unittest.main()
