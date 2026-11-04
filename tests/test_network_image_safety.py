"""Ensure that the insecure LAN-only prototype cannot start with the image."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audiohub.network_laptop import validate_options


class NetworkPrototypeSafetyTests(unittest.TestCase):
    def test_no_image_stage_installs_network_receiver_service(self):
        stage = ROOT / "image" / "stage-audiohub"
        self.assertTrue(stage.is_dir())
        paths = [
            file for file in stage.rglob("*")
            if file.is_file() and (file.name.endswith((".sh", ".service", ".conf"))
                                   or file.name.endswith("-nr"))
        ]
        self.assertGreater(len(paths), 0)
        for path in paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("audiohub.network_laptop", text)
                self.assertNotIn("network_laptop.py", text)
                self.assertNotIn("--unsafe-lan-test", text)

    def test_network_receiver_requires_manual_test_flag(self):
        with self.assertRaisesRegex(ValueError, "Explicit"):
            validate_options("192.168.1.10", "192.168.1.20", 4010, False)

    def test_network_receiver_rejects_public_bind_address(self):
        with self.assertRaises(ValueError):
            validate_options("192.168.1.10", "8.8.8.8", 4010, True)

    def test_network_receiver_rejects_multicast_sender(self):
        with self.assertRaises(ValueError):
            validate_options("239.255.77.77", "192.168.1.20", 4010, True)


if __name__ == "__main__":
    unittest.main()
