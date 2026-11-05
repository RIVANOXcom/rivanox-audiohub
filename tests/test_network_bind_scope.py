"""Fail-closed IPv4 binding tests for the manual Scream UDP prototype."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.network_laptop import validate_options


class NetworkBindScopeTests(unittest.TestCase):
    def test_specific_private_sender_and_bind_are_accepted_with_manual_flag(self):
        for sender, bind in (
            ("192.168.1.10", "192.168.1.20"),
            ("10.0.0.6", "10.0.0.7"),
            ("172.16.8.5", "172.31.2.3"),
            ("127.0.0.1", "127.0.0.1"),
        ):
            with self.subTest(sender=sender, bind=bind):
                self.assertEqual(
                    validate_options(sender, bind, 4010, True),
                    (sender, bind, 4010)
                )

    def test_no_implicit_opt_in_for_private_addresses(self):
        with self.assertRaisesRegex(ValueError, "opt-in"):
            validate_options("192.168.1.10", "192.168.1.20", 4010, False)

    def test_wildcard_bind_never_allowed_even_with_manual_flag(self):
        with self.assertRaisesRegex(ValueError, "specific"):
            validate_options("192.168.1.10", "0.0.0.0", 4010, True)

    def test_link_local_and_special_use_ips_never_allowed(self):
        for addr in ("169.254.7.1", "100.64.0.1", "198.18.0.1",
                     "192.0.0.1", "224.0.0.1", "239.255.77.77",
                     "255.255.255.255", "8.8.8.8", "0.0.0.0",
                     "240.0.0.1"):
            with self.subTest(addr=addr):
                with self.assertRaises(ValueError):
                    validate_options(addr, "192.168.1.20", 4010, True)
                with self.assertRaises(ValueError):
                    validate_options("192.168.1.10", addr, 4010, True)

    def test_valid_address_with_nonhost_input_rejected(self):
        for addr in ("example.com", "::1", "192.168.1.1:4010", "", None):
            with self.subTest(addr=str(addr)):
                with self.assertRaises(ValueError):
                    validate_options("192.168.1.10", addr, 4010, True)

    def test_invalid_port_denied(self):
        for port in (0, 1023, 65536, True, "4010"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    validate_options("192.168.1.10", "192.168.1.20", port, True)

    def test_no_image_auto_enabled_listener(self):
        stage = ROOT / "image" / "stage-audiohub"
        for file in stage.rglob("*"):
            if file.is_file() and (file.suffix in (".sh", ".service", ".conf")
                                   or file.name.endswith("-nr")):
                text = file.read_text(encoding="utf-8")
                self.assertNotIn("audiohub.network_laptop", text)
                self.assertNotIn("--unsafe-lan-test", text)


if __name__ == "__main__":
    unittest.main()
