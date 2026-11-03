"""Read-only web API and deployment safety tests."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.webserver import ALLOWED, PUBLIC_FIELDS, public_status


class WebStatusTests(unittest.TestCase):
    def test_live_health_is_anonymized_and_bounded(self):
        raw = {
            "updated_at": 100, "usb_output": True, "active_routes": 999,
            "bluetooth_source_count": 999,
            "virtual_channels": ["music", "music", "tablet", "../secret"],
            "address": "AA:BB:CC:DD:EE:FF", "ssid": "PrivateWifi",
            "password": "never-disclose",
        }
        status = public_status(raw, now=109)
        self.assertEqual(set(status), PUBLIC_FIELDS)
        self.assertEqual(status["active_routes"], 3)
        self.assertEqual(status["bluetooth_sources"], 2)
        self.assertEqual(status["virtual_channel_count"], 2)
        self.assertTrue(status["usb_connected"])
        self.assertNotIn("AA:BB", str(status))
        self.assertNotIn("PrivateWifi", str(status))

    def test_stale_or_wrong_status_is_not_trusted(self):
        for value in ({}, "bad", {"updated_at": 1, "usb_output": True}):
            with self.subTest(value=value):
                self.assertFalse(public_status(value, now=100)["fresh"])
                self.assertFalse(public_status(value, now=100)["usb_connected"])

    def test_time_must_not_be_in_future(self):
        self.assertFalse(public_status({"updated_at": 200}, now=100)["fresh"])

    def test_assets_are_explicitly_allowlisted(self):
        self.assertIn("/", ALLOWED)
        for code in ("en", "de", "es", "fr", "it"):
            self.assertIn("/locales/" + code + ".json", ALLOWED)
        for hidden in ("/etc/passwd", "/.env", "/../secrets", "/locales/../../etc/passwd"):
            self.assertNotIn(hidden, ALLOWED)

    def test_web_service_does_not_expose_mutating_api(self):
        script = (ROOT / "src/audiohub/webserver.py").read_text()
        self.assertIn("def do_POST(self):", script)
        self.assertIn("Read-only preview", script)
        self.assertNotIn("shell=True", script)

    def test_image_contains_web_and_service(self):
        builder = (ROOT / "build-image.sh").read_text()
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text()
        self.assertIn('cp -a "$ROOT/web/."', builder)
        self.assertIn("files/web/.", installer)
        self.assertIn("audiohub-status-web.service", installer)


if __name__ == "__main__":
    unittest.main()
