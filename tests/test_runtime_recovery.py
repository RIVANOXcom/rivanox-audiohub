"""AudioHub runtime recovery tests without requiring Bluetooth or USB hardware."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.runtime import STATE, Supervisor


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


if __name__ == "__main__":
    unittest.main()
