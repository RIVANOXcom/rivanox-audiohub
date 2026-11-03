"""Build-time security checks for experimental Bluetooth pairing policy."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PairingPolicyTests(unittest.TestCase):
    def test_service_closes_pairing_on_reboot_with_known_devices(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn("self.initial_pairing_allowed = self.paired_count() == 0", text)
        self.assertIn("self.initial_pairing_allowed and time.monotonic() < self.deadline", text)

    def test_device_count_and_timeout_bounded(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        self.assertIn("BOOT_WINDOW = 600", text)
        self.assertIn("PAIRING_LIMIT = 2", text)
        self.assertIn("NoInputNoOutput", text)

if __name__ == "__main__":
    unittest.main()
