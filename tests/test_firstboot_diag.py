"""Offline pi-alpha SD report tests. No actual Pi, Bluetooth or network required."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import firstboot_diag as diag


class Clock:
    def __init__(self):
        self.elapsed = 0

    def now(self):
        return 2_000_000 + self.elapsed

    def mono(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.runtime = self.root / "runtime-status.json"
        self.output = self.root / "boot"
        self.output.mkdir()
        self.uid = os.geteuid()

    def runtime_write(self, record):
        self.runtime.write_text(json.dumps(record))
        self.runtime.chmod(0o600)

    def test_missing_runtime_is_not_reported_healthy(self):
        report = diag.sample(self.runtime, self.uid, now=1000)
        self.assertEqual(report["runtime_status"], "unavailable_or_stale")
        self.assertFalse(report["usb_audio_detected"])
        self.assertEqual(report["bluetooth_audio_sources"], 0)

    def test_recent_runtime_copies_only_bounded_nonidentifying_metrics(self):
        self.runtime_write({
            "updated_at": 100,
            "usb_output": True,
            "virtual_channels": ["music", "music", "tablet", {"bad": 1}],
            "bluetooth_source_count": 99,
            "active_routes": -2,
            "device_address": "AA:BB:CC:DD:EE:FF",
            "wifi_password": "supersecret",
            "ssid": "private-ssid",
        })
        result = diag.sample(self.runtime, self.uid, now=101, controller_present=True)
        self.assertEqual(result["runtime_status"], "recent")
        self.assertTrue(result["usb_audio_detected"])
        self.assertTrue(result["bluetooth_controller_present"])
        self.assertEqual(result["virtual_audio_channels"], 2)
        self.assertEqual(result["bluetooth_audio_sources"], 2)
        self.assertEqual(result["active_audio_routes"], 0)
        serialized = json.dumps(result)
        for forbidden in ("AA:BB", "supersecret", "private-ssid", "wifi_password"):
            self.assertNotIn(forbidden, serialized)

    def test_stale_or_future_runtime_is_not_trusted(self):
        self.runtime_write({"updated_at": 11, "usb_output": True})
        self.assertEqual(diag.sample(self.runtime, self.uid, now=102)["runtime_status"],
                         "unavailable_or_stale")
        self.runtime_write({"updated_at": 102, "usb_output": True})
        self.assertEqual(diag.sample(self.runtime, self.uid, now=101)["runtime_status"],
                         "unavailable_or_stale")

    def test_wrong_types_cannot_escape_or_fake_success(self):
        for updated in (True, "100", [], {}, None):
            self.runtime_write({"updated_at": updated, "usb_output": True})
            with self.subTest(updated=repr(updated)):
                self.assertFalse(diag.sample(self.runtime, self.uid, now=100)["usb_audio_detected"])
        self.runtime_write({
            "updated_at": 100, "usb_output": 1,
            "active_routes": True, "bluetooth_source_count": "7",
            "virtual_channels": [{"x": 1}, None, 1],
        })
        snapshot = diag.sample(self.runtime, self.uid, now=101)
        self.assertFalse(snapshot["usb_audio_detected"])
        self.assertEqual(snapshot["bluetooth_audio_sources"], 0)
        self.assertEqual(snapshot["active_audio_routes"], 0)
        self.assertEqual(snapshot["virtual_audio_channels"], 0)

    def test_broken_json_and_oversized_file_fail_closed(self):
        self.runtime.write_bytes(b"{unparsable")
        self.assertEqual(diag.sample(self.runtime, self.uid)["runtime_status"],
                         "unavailable_or_stale")
        self.runtime.write_bytes(b"a" * (diag.MAX_RUNTIME_BYTES + 1))
        self.assertEqual(diag.sample(self.runtime, self.uid)["runtime_status"],
                         "unavailable_or_stale")

    def test_runtime_symlink_is_not_followed(self):
        private = self.root / "private"
        private.write_text(json.dumps({"updated_at": 100, "usb_output": True}))
        self.runtime.symlink_to(private)
        self.assertFalse(diag.sample(self.runtime, self.uid, now=101)["usb_audio_detected"])

    def test_runtime_wrong_owner_fails_closed(self):
        self.runtime_write({"updated_at": 100, "usb_output": True})
        self.assertFalse(diag.sample(self.runtime, self.uid + 1, now=101)["usb_audio_detected"])

    def test_report_requires_real_mounted_boot_partition(self):
        payload = {"schema": diag.SCHEMA, "snapshots": []}
        self.assertFalse(diag.write_report(self.output, payload))
        self.assertFalse((self.output / diag.OUTPUT_NAME).exists())

    def test_report_is_atomic_and_never_includes_secret_fields(self):
        self.runtime_write({"updated_at": 2_000_000, "usb_output": True,
                            "bluetooth_source_count": 1, "MAC": "AA:CC",
                            "SSID": "private-network"})
        sample = diag.sample(self.runtime, self.uid, now=2_000_001)
        record = {"schema": diag.SCHEMA, "snapshots": [sample]}
        self.assertTrue(diag.write_report(self.output, record, require_mount=False))
        target = self.output / diag.OUTPUT_NAME
        self.assertEqual(json.loads(target.read_text()), record)
        self.assertNotIn("private-network", target.read_text())
        self.assertNotIn("AA:CC", target.read_text())
        self.assertTrue(diag.write_report(self.output, record, require_mount=False))
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_symlink_target_is_never_followed_during_report_replacement(self):
        outside = self.root / "outside"
        outside.write_text("keep existing private file")
        (self.output / diag.OUTPUT_NAME).symlink_to(outside)
        self.assertTrue(diag.write_report(
            self.output, {"schema": diag.SCHEMA}, require_mount=False
        ))
        self.assertEqual(outside.read_text(), "keep existing private file")
        self.assertFalse((self.output / diag.OUTPUT_NAME).is_symlink())

    def test_oversized_report_is_rejected(self):
        self.assertFalse(diag.write_report(
            self.output, {"secret": "x" * 9000}, require_mount=False
        ))
        self.assertFalse((self.output / diag.OUTPUT_NAME).exists())

    def test_report_continues_collecting_after_initial_missing_runtime(self):
        clock = Clock()
        controller = self.root / "controller"
        controller.touch()
        with mock.patch.object(diag, "write_report", wraps=diag.write_report):
            self.assertTrue(diag.run_probe(
                sleep=clock.sleep, now=clock.now, mono=clock.mono,
                output_dir=self.output, runtime_path=self.runtime,
                user_id=self.uid, controller_path=controller,
                require_mount=False,
            ))
        report = json.loads((self.output / diag.OUTPUT_NAME).read_text())
        self.assertEqual(len(report["snapshots"]), len(diag.CHECKPOINT_DELAYS))
        self.assertEqual(report["snapshots"][0]["seconds_since_probe_start"], 0)
        self.assertEqual(report["snapshots"][-1]["seconds_since_probe_start"], 600)
        self.assertFalse(report["hardware_accepted"])
        self.assertFalse(report["owner_authenticated"])
        self.assertFalse(report["phone_wifi_provisioned"])
        self.assertTrue(report["snapshots"][0]["bluetooth_controller_present"])

    def test_report_observes_later_runtime_health_without_network(self):
        clock = Clock()
        def sleep(seconds):
            clock.sleep(seconds)
            if clock.elapsed >= 30:
                self.runtime_write({
                    "updated_at": int(clock.now()), "usb_output": True,
                    "bluetooth_source_count": 1, "active_routes": 1,
                    "virtual_channels": ["music"],
                })
        self.assertTrue(diag.run_probe(
            sleep=sleep, now=clock.now, mono=clock.mono,
            output_dir=self.output, runtime_path=self.runtime,
            user_id=self.uid, controller_path=self.root / "absent",
            require_mount=False,
        ))
        report = json.loads((self.output / diag.OUTPUT_NAME).read_text())
        self.assertEqual(report["snapshots"][0]["runtime_status"],
                         "unavailable_or_stale")
        self.assertTrue(report["snapshots"][1]["usb_audio_detected"])
        self.assertEqual(report["snapshots"][1]["active_audio_routes"], 1)
        self.assertFalse(report["hardware_accepted"])

    def test_usb_presence_is_distinct_from_successful_audio_routing(self):
        self.runtime_write({
            "updated_at": 100, "usb_output": True,
            "usb_route_ready": False, "route_start_failures": 12,
            "output_switch_failures": 3,
            "wifi_password": "private-test-only",
        })
        result = diag.sample(self.runtime, self.uid, now=101)
        self.assertTrue(result["usb_audio_detected"])
        self.assertFalse(result["usb_audio_route_ready"])
        self.assertEqual(result["route_start_failures"], 12)
        self.assertEqual(result["output_switch_failures"], 3)
        self.assertNotIn("private-test-only", json.dumps(result))

    def test_audio_failure_counters_are_bounded_and_type_checked(self):
        self.runtime_write({
            "updated_at": 100, "usb_output": 1,
            "usb_route_ready": "yes",
            "route_start_failures": 99999,
            "output_switch_failures": True,
        })
        result = diag.sample(self.runtime, self.uid, now=101)
        self.assertFalse(result["usb_audio_detected"])
        self.assertFalse(result["usb_audio_route_ready"])
        self.assertEqual(result["route_start_failures"], 999)
        self.assertEqual(result["output_switch_failures"], 0)

    def test_conservative_master_estimate_is_redacted_and_bounded(self):
        self.runtime_write({
            "updated_at": 101,
            "usb_output": True,
            "usb_route_ready": True,
            "effective_master_percent": 33,
            "ssid": "SECRET-WIFI",
        })
        report = diag.sample(self.runtime, self.uid, now=102)
        self.assertEqual(report["effective_master_percent"], 33)
        self.assertNotIn("SECRET-WIFI", json.dumps(report))
        self.runtime_write({
            "updated_at": 101, "effective_master_percent": 9000,
        })
        self.assertEqual(
            diag.sample(self.runtime, self.uid, now=102)["effective_master_percent"], 100
        )
        self.runtime_write({
            "updated_at": 101, "effective_master_percent": True,
        })
        self.assertEqual(
            diag.sample(self.runtime, self.uid, now=102)["effective_master_percent"], 0
        )

    def test_diagnostics_install_uses_only_readonly_runtime_and_boot_file(self):
        script = (ROOT / "src/audiohub/firstboot_diag.py").read_text()
        service = (ROOT / "image/stage-audiohub/01-install/files/systemd"
                   / "audiohub-firstboot-diag.service").read_text()
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text()
        for forbidden in ("socket.socket", "dbus.SystemBus", "nmcli",
                          "subprocess.run", "passwd", "Authorization:"):
            # pwd.getpwnam("audiohub") is expected and does not read secrets.
            if forbidden == "passwd":
                continue
            self.assertNotIn(forbidden, script)
        self.assertIn("PrivateNetwork=yes", service)
        self.assertIn("ReadWritePaths=/boot/firmware", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("systemctl enable audiohub-firstboot-diag.service", installer)
        self.assertNotIn("ExecStart=/bin/sh", service)


if __name__ == "__main__":
    unittest.main()
