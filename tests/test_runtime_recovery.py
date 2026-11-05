"""AudioHub runtime recovery tests without requiring Bluetooth or USB hardware."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.runtime import STATE, Supervisor, MAX_RUNTIME_JSON_BYTES, atomic_json, read_json


class FakeProcess:
    def __init__(self):
        self.alive = True
        self.terminated = False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout=2):
        return 0

    def kill(self):
        self.alive = False


class RecoveryTests(unittest.TestCase):
    def supervisor(self):
        obj = Supervisor.__new__(Supervisor)
        obj.assignments = {"AA:BB:CC:DD:EE:FF": "music"}
        obj.loopbacks = {}
        obj.last_default = None
        return obj

    def source(self, name):
        return [{"address": "AA:BB:CC:DD:EE:FF", "name": name}]

    def test_status_stored_in_volatile_runtime_directory(self):
        expected = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self.assertTrue(str(STATE).startswith(expected + "/audiohub/"))

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_new_audio_source_replaces_old_route(self, popen):
        one, two = FakeProcess(), FakeProcess()
        popen.side_effect = [one, two]
        s = self.supervisor()
        s._route(self.source("bluez_input.first"), {"audiohub.music": 7})
        self.assertEqual(popen.call_count, 1)
        s._route(self.source("bluez_input.first"), {"audiohub.music": 7})
        self.assertEqual(popen.call_count, 1, "unchanged routes must not restart")
        s._route(self.source("bluez_input.second"), {"audiohub.music": 7})
        self.assertTrue(one.terminated)
        self.assertEqual(popen.call_count, 2)
        self.assertFalse(two.terminated)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_disconnected_sink_stops_managed_routes(self, popen):
        proc = FakeProcess()
        popen.return_value = proc
        s = self.supervisor()
        s._route(self.source("bluez_input.first"), {"audiohub.music": 7})
        s._route(self.source("bluez_input.first"), {})
        self.assertTrue(proc.terminated)
        self.assertEqual(s.loopbacks, {})


class PrivateRuntimeStateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.private = self.base / "private"
        self.private.mkdir(mode=0o700)
        self.path = self.private / "runtime-status.json"

    def test_private_status_roundtrip_and_permissions(self):
        payload = {"usb_output": True, "routes": {"music": 1}}
        atomic_json(self.path, payload)
        self.assertEqual(read_json(self.path, {}), payload)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)

    def test_two_updates_are_atomic_and_leave_no_tmp(self):
        atomic_json(self.path, {"first": True})
        atomic_json(self.path, {"second": True})
        self.assertEqual(read_json(self.path, {}), {"second": True})
        self.assertEqual(sorted(p.name for p in self.private.iterdir()),
                         ["runtime-status.json"])

    def test_existing_symlink_destination_refused_without_touching_target(self):
        protected = self.base / "protected"
        protected.write_text("DO NOT MODIFY")
        self.path.symlink_to(protected)
        with self.assertRaises((OSError, PermissionError)):
            atomic_json(self.path, {"tried": True})
        self.assertEqual(protected.read_text(), "DO NOT MODIFY")
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(read_json(self.path, {"ok": False}), {"ok": False})

    def test_legacy_predictable_tmp_symlink_is_not_used(self):
        protected = self.base / "protected"
        protected.write_text("PRIVATE OWNER DATA")
        old_tmp = self.path.with_suffix(".tmp")
        old_tmp.symlink_to(protected)
        atomic_json(self.path, {"a": 1})
        self.assertEqual(protected.read_text(), "PRIVATE OWNER DATA")
        self.assertTrue(old_tmp.is_symlink())
        self.assertEqual(read_json(self.path, {}), {"a": 1})

    def test_symlinked_parent_directory_is_denied(self):
        external = self.base / "linked"
        external.symlink_to(self.private, target_is_directory=True)
        malicious_path = external / "state.json"
        with self.assertRaises(OSError):
            atomic_json(malicious_path, {"secret": "no"})
        self.assertFalse((self.private / "state.json").exists())
        self.assertEqual(read_json(malicious_path, {"safe": True}),
                         {"safe": True})

    def test_world_readable_storage_directory_rejected(self):
        os.chmod(self.private, 0o755)
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"secret": "never"})
        self.assertFalse(self.path.exists())
        self.assertEqual(read_json(self.path, {}), {})

    def test_overlarge_state_read_returns_default(self):
        self.path.write_bytes(b"x" * (MAX_RUNTIME_JSON_BYTES + 1))
        os.chmod(self.path, 0o600)
        self.assertEqual(read_json(self.path, {"safe": True}), {"safe": True})

    def test_overlarge_state_write_is_refused_untouched(self):
        atomic_json(self.path, {"first": 1})
        old = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "storage limit"):
            atomic_json(self.path, {"data": "x" * MAX_RUNTIME_JSON_BYTES})
        self.assertEqual(self.path.read_bytes(), old)

    def test_corrupt_json_returns_fallback_without_leak(self):
        self.path.write_text("{{SECRET{")
        os.chmod(self.path, 0o600)
        self.assertEqual(read_json(self.path, {"fresh": False}), {"fresh": False})

    def test_malformed_type_returns_fallback(self):
        self.path.write_text("[1,2,3]")
        os.chmod(self.path, 0o600)
        self.assertEqual(read_json(self.path, {}), {})

    def test_symlinked_file_read_returns_fallback(self):
        hidden = self.base / "hidden"
        hidden.write_text('{"secret":"do not read"}')
        self.path.symlink_to(hidden)
        self.assertEqual(read_json(self.path, {"blocked": True}),
                         {"blocked": True})

    def test_fifo_file_is_refused_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("Linux-only")
        os.mkfifo(self.path)
        self.assertEqual(read_json(self.path, {"blocked": True}),
                         {"blocked": True})
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"data": 1})

    def test_hardlinked_destination_is_refused(self):
        original = self.base / "original"
        original.write_text('{"old":1}')
        os.chmod(original, 0o600)
        os.link(original, self.path)
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"old": 2})
        self.assertEqual(json.loads(original.read_text()), {"old": 1})
        self.assertEqual(read_json(self.path, {"no": True}), {"no": True})

    def test_destination_with_unsafe_file_permissions_is_refused(self):
        self.path.write_text('{"old":1}')
        os.chmod(self.path, 0o644)
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"old": 2})
        self.assertEqual(read_json(self.path, {"safe": True}), {"safe": True})

    def test_nonjson_nan_is_refused_before_file_creation(self):
        with self.assertRaises(ValueError):
            atomic_json(self.path, {"number": float("nan")})
        self.assertFalse(self.path.exists())

    def test_create_missing_private_intermediate_directory(self):
        dest = self.private / "inner" / "runtime-status.json"
        atomic_json(dest, {"ok": True})
        self.assertEqual(read_json(dest, {}), {"ok": True})
        self.assertEqual(stat.S_IMODE(dest.parent.stat().st_mode), 0o700)

    def test_reject_relative_and_traversal_state_paths(self):
        for invalid in (Path("state.json"), self.private / ".." / "secret.json"):
            with self.subTest(path=str(invalid)):
                with self.assertRaises(ValueError):
                    atomic_json(invalid, {"value": 1})
                self.assertEqual(read_json(invalid, {"blocked": True}),
                                 {"blocked": True})


if __name__ == "__main__":
    unittest.main()
