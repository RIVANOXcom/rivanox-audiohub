"""Offline source routing policy integration and security tests."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import source_routes as routes


class SourcePolicyTests(unittest.TestCase):
    def setUp(self):
        obj = tempfile.TemporaryDirectory()
        self.addCleanup(obj.cleanup)
        self.root = Path(obj.name)
        self.dir = self.root / "audiohub"

    def test_default_transport_slots(self):
        self.assertEqual(routes.load(self.dir), {
            "schema": routes.SCHEMA, "mode": "auto",
            "lan_slot": "laptop", "bluetooth": {},
        })
        self.assertEqual(routes.lan_target(self.dir), "audiohub.laptop")

    def test_lan_switch_can_target_any_of_three_slots(self):
        for slot in ("music", "tablet", "laptop"):
            with self.subTest(slot=slot):
                routes.set_lan(slot, self.dir)
                self.assertEqual(routes.lan_target(self.dir), "audiohub." + slot)

    def test_manual_bt_assignment_preserves_one_lan_slot(self):
        routes.set_lan("music", self.dir)
        routes.bind_bluetooth("aa:bb:cc:dd:ee:ff", "laptop", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        policy = routes.load(self.dir)
        self.assertEqual(policy["mode"], "manual")
        self.assertEqual(policy["bluetooth"]["AA:BB:CC:DD:EE:FF"], "laptop")
        self.assertEqual(set(policy["bluetooth"].values()),
                         {"laptop", "tablet"})

    def test_conflicting_slots_rejected_without_reset(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        old = routes.load(self.dir)
        with self.assertRaises(ValueError):
            routes.bind_bluetooth("11:22:33:44:55:66", "music", self.dir)
        with self.assertRaises(ValueError):
            routes.set_lan("music", self.dir)
        self.assertEqual(routes.load(self.dir), old)

    def test_third_bluetooth_source_is_rejected(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        with self.assertRaises(ValueError):
            routes.bind_bluetooth("22:33:44:55:66:77", "music", self.dir)

    def test_manual_zero_bt_disables_auto_discovery(self):
        routes.set_mode("manual", self.dir)
        self.assertEqual(routes.load(self.dir)["bluetooth"], {})
        self.assertEqual(routes.load(self.dir)["mode"], "manual")
        routes.set_mode("auto", self.dir)
        self.assertEqual(routes.load(self.dir)["mode"], "auto")

    def test_unbind_does_not_reenable_auto(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.unbind_bluetooth("AA:BB:CC:DD:EE:FF", self.dir)
        self.assertEqual(routes.load(self.dir)["mode"], "manual")
        self.assertEqual(routes.load(self.dir)["bluetooth"], {})

    def test_invalid_policy_types_and_unknown_keys(self):
        bad = [
            {}, [], {"schema": routes.SCHEMA, "mode": "auto",
                     "lan_slot": "music", "bluetooth": {"AA:BB:CC:DD:EE:FF": "tablet"}},
            {"schema": routes.SCHEMA, "mode": "manual",
             "lan_slot": "laptop", "bluetooth": {"AA:BB:CC:DD:EE:FF": "laptop"}},
            {"schema": routes.SCHEMA, "mode": "manual",
             "lan_slot": "laptop", "bluetooth": {"AA:BB:CC:DD:EE:FF": "music",
                                                "11:22:33:44:55:66": "music"}},
        ]
        for plan in bad:
            with self.subTest(plan=repr(plan)), self.assertRaises(ValueError):
                routes.validate(plan)

    def test_private_on_disk_permissions(self):
        routes.set_lan("music", self.dir)
        file = self.dir / routes.FILENAME
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        self.assertFalse(any(x.name.endswith(".tmp") for x in self.dir.iterdir()))

    def test_corrupt_policy_fails_closed_and_is_not_overwritten(self):
        routes.set_mode("manual", self.dir)
        file = self.dir / routes.FILENAME
        file.write_text("garbage")
        with self.assertRaises(ValueError):
            routes.load(self.dir)
        with self.assertRaises(ValueError):
            routes.set_lan("music", self.dir)
        self.assertEqual(file.read_text(), "garbage")

    def test_file_symlink_rejected(self):
        self.dir.mkdir(mode=0o700)
        private = self.root / "private"
        private.write_text("secret")
        (self.dir / routes.FILENAME).symlink_to(private)
        with self.assertRaises(OSError):
            routes.load(self.dir)
        self.assertEqual(private.read_text(), "secret")

    def test_directory_symlink_rejected(self):
        real = self.root / "real"
        real.mkdir(mode=0o700)
        self.dir.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            routes.load(self.dir)

    def test_overlong_or_world_readable_policy_rejected(self):
        routes.set_lan("music", self.dir)
        file = self.dir / routes.FILENAME
        file.chmod(0o644)
        with self.assertRaises(PermissionError):
            routes.load(self.dir)
        file.chmod(0o600)
        file.write_bytes(b"x" * (routes.MAX_FILE_BYTES + 1))
        with self.assertRaises((ValueError, PermissionError)):
            routes.load(self.dir)
