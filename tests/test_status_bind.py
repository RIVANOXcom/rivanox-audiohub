"""First-boot status listener security tests without opening sockets."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.status_bind import select_bind_address
from audiohub import webserver


class StatusBindTests(unittest.TestCase):
    def test_default_listening_interface_is_localhost(self):
        self.assertEqual(select_bind_address({}), "127.0.0.1")

    def test_explicit_loopback_does_not_require_unsafe_flag(self):
        self.assertEqual(select_bind_address({"AUDIOHUB_STATUS_BIND_IP": "127.0.0.2"}),
                         "127.0.0.2")

    def test_rfc1918_lan_requires_exact_case_sensitive_opt_in(self):
        for address in ("10.1.2.3", "172.16.1.23", "172.31.255.12",
                        "192.168.4.1"):
            with self.subTest(address=address):
                with self.assertRaisesRegex(ValueError, "explicit"):
                    select_bind_address({"AUDIOHUB_STATUS_BIND_IP": address})
                self.assertEqual(select_bind_address({
                    "AUDIOHUB_STATUS_BIND_IP": address,
                    "AUDIOHUB_UNSAFE_STATUS_LAN": "YES",
                }), address)
        with self.assertRaises(ValueError):
            select_bind_address({
                "AUDIOHUB_STATUS_BIND_IP": "10.1.2.3",
                "AUDIOHUB_UNSAFE_STATUS_LAN": "yes",
            })

    def test_never_binds_wildcard_or_public_address_even_when_opted_in(self):
        for address in ("0.0.0.0", "8.8.8.8", "255.255.255.255",
                        "239.255.77.77", "169.254.1.2", "::", "::1",
                        "198.51.100.4", "172.32.1.2", "host.local",
                        "192.168.1.1:8765", ""):
            with self.subTest(address=address), self.assertRaises(ValueError):
                select_bind_address({
                    "AUDIOHUB_STATUS_BIND_IP": address,
                    "AUDIOHUB_UNSAFE_STATUS_LAN": "YES",
                })

    def test_non_string_bind_rejected(self):
        for address in (None, 99, ["127.0.0.1"], True):
            with self.subTest(address=address), self.assertRaises(ValueError):
                select_bind_address({"AUDIOHUB_STATUS_BIND_IP": address})

    @mock.patch("audiohub.webserver.select_bind_address", return_value="127.0.0.1")
    @mock.patch("audiohub.webserver.BoundedStatusHTTPServer")
    def test_web_startup_uses_guarded_loopback_address(self, server, bind):
        webserver.main()
        server.assert_called_once_with(("127.0.0.1", 8765), webserver.Handler)
        server.return_value.serve_forever.assert_called_once_with(poll_interval=0.5)
        bind.assert_called_once()

    @mock.patch("audiohub.webserver.select_bind_address", side_effect=ValueError("no LAN"))
    @mock.patch("audiohub.webserver.BoundedStatusHTTPServer")
    def test_denied_bind_never_opens_socket(self, server, bind):
        with self.assertRaises(ValueError):
            webserver.main()
        server.assert_not_called()

    def test_malformed_runtime_virtual_channels_cannot_crash_status(self):
        raw = {
            "updated_at": 100,
            "usb_output": True,
            "virtual_channels": ["music", {"malformed": "data"},
                                 ["tablet"], 22, None, "tablet", "music"],
        }
        report = webserver.public_status(raw, now=101)
        self.assertEqual(report["virtual_channel_count"], 2)
        self.assertEqual(set(report), webserver.PUBLIC_FIELDS)
        self.assertNotIn("malformed", json.dumps(report))

    def test_image_does_not_enable_unsafe_lan_status_access(self):
        service = (ROOT / "image/stage-audiohub/01-install/files/systemd"
                   / "audiohub-status-web.service").read_text(encoding="utf-8")
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("AUDIOHUB_UNSAFE_STATUS_LAN", service)
        self.assertNotIn("AUDIOHUB_UNSAFE_STATUS_LAN", installer)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertNotIn("ExecStart=/bin/sh", service)


if __name__ == "__main__":
    unittest.main()
