"""Anonymized local source-observation UI; never equate process with audio."""
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import runtime, source_status, source_routes
from audiohub.mixer import CHANNELS, defaults


class FakeProcess:
    def __init__(self, alive=True):
        self.alive = alive

    def poll(self):
        return None if self.alive else 1


class LocalSourceStatusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / "private"
        self.file = self.directory / "runtime-status.json"

    def report_file(self, data):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        runtime.atomic_json(self.file, data)

    @staticmethod
    def sample(*, lan_slot="laptop", usb_ready=True):
        mac = "AA:BB:CC:DD:EE:FF"
        sources = [{"address": mac, "name": "bluez_input.test"}]
        assignment = {mac: "music"}
        loops = {mac: ("bluez_input.test", "audiohub.music", FakeProcess())}
        sinks = {"audiohub.music": 5, "audiohub.laptop": 6}
        return runtime.observed_source_slots(
            sources, assignment, loops, sinks, lan_slot=lan_slot,
            policy_valid=True, usb_ready=usb_ready)

    def test_observer_separates_configured_detected_and_running_from_audible(self):
        actual = self.sample()
        self.assertEqual(set(actual), set(CHANNELS))
        self.assertTrue(actual["music"]["bluetooth_assigned"])
        self.assertTrue(actual["music"]["bluetooth_node_observed"])
        self.assertTrue(actual["music"]["managed_loopback_running"])
        self.assertTrue(actual["laptop"]["lan_reserved"])
        self.assertFalse(actual["laptop"]["bluetooth_assigned"])
        self.assertFalse(actual["tablet"]["virtual_sink_observed"])
        self.assertNotIn("AA:BB:CC", str(actual))

    def test_source_status_fresh_shows_evidence_and_unknown_connection(self):
        self.report_file({
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "mac": "AA:BB:CC:DD:EE:FF", "ssid": "SECRET-WIFI",
            "device_id": "SECRET-NODE",
        })
        before = self.file.read_bytes()
        with mock.patch.object(runtime, "atomic_json") as write:
            report = source_status.read_report(path=self.file, now=105)
            write.assert_not_called()
        self.assertTrue(report["fresh"])
        self.assertTrue(report["observations_available"])
        self.assertEqual(report["status_age_seconds"], 5)
        music = report["inputs"]["music"]
        self.assertEqual(music["configured_role"], "bluetooth_assigned")
        self.assertTrue(music["configured"])
        self.assertTrue(music["bluetooth_source_node_seen"])
        self.assertTrue(music["managed_loopback_process_running"])
        self.assertEqual(music["bluetooth_connected"], "unverified")
        self.assertEqual(music["audio_stream_available"], "unverified")
        self.assertEqual(music["audible_playback"], "unverified")
        self.assertEqual(report["inputs"]["laptop"]["configured_role"], "lan_reserved")
        self.assertIsNone(report["inputs"]["laptop"]["bluetooth_source_node_seen"])
        self.assertIsNone(report["inputs"]["laptop"]["managed_loopback_process_running"])
        self.assertEqual(report["inputs"]["tablet"]["configured_role"], "unassigned")
        self.assertFalse(report["inputs"]["tablet"]["configured"])
        self.assertFalse(report["hardware_verified"])
        self.assertFalse(report["release_ready"])
        self.assertNotIn("AA:BB:CC", json.dumps(report))
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertEqual(self.file.read_bytes(), before)

    def test_source_status_stale_missing_future_and_wrong_type_fail_closed(self):
        for age in (None, 31, -1, 100):
            with self.subTest(age=age):
                raw = {
                    "updated_at": 100 if age is None else 100 - age,
                    "route_policy_valid": True,
                    "source_slot_observations_version": 1,
                    "source_slot_observations": self.sample(),
                }
                if age is None:
                    raw.pop("updated_at")
                report = source_status.interpret(raw, now=100)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["observations_available"])
                for slot in CHANNELS:
                    self.assertEqual(report["inputs"][slot]["configured_role"], "unknown")
                    self.assertIsNone(report["inputs"][slot]["configured"])
                    self.assertIsNone(report["inputs"][slot]["bluetooth_source_node_seen"])
        self.assertFalse(self.directory.exists())
        self.assertFalse(source_status.read_report(path=self.file, now=100)[
            "observations_available"])
        self.assertFalse(self.directory.exists())

    def test_source_status_rejects_malformed_unsafe_or_forged_positive_fields(self):
        base = {
            "updated_at": 100,
            "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
        }
        for replacement in (
            {"route_policy_valid": "true"},
            {"source_slot_observations_version": True},
            {"source_slot_observations_version": 2},
            {"source_slot_observations": {}},
            {"source_slot_observations": {"music": {"secret": "bad"}}},
        ):
            with self.subTest(replacement=replacement):
                report = source_status.interpret({**base, **replacement}, now=103)
                self.assertFalse(report["observations_available"])
                self.assertIsNone(report["inputs"]["music"]["configured"])
        invalid = json.loads(json.dumps(base))
        invalid["source_slot_observations"]["music"]["bluetooth_node_observed"] = 1
        self.assertFalse(source_status.interpret(invalid, now=103)[
            "observations_available"])
        invalid2 = json.loads(json.dumps(base))
        invalid2["source_slot_observations"]["music"]["lan_reserved"] = True
        self.assertFalse(source_status.interpret(invalid2, now=103)[
            "observations_available"])

    def test_invalid_route_policy_must_not_assert_assignment_or_audio(self):
        state = {
            "updated_at": 100, "route_policy_valid": False,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
        }
        report = source_status.interpret(state, now=100)
        self.assertTrue(report["fresh"])
        self.assertFalse(report["observations_available"])
        self.assertFalse(report["route_policy_valid"])
        self.assertEqual(report["inputs"]["music"]["configured_role"], "unknown")

    def test_read_report_rejects_unprivate_symlinked_and_bad_json_without_creating(self):
        self.directory.mkdir(mode=0o700)
        secret = self.root / "hidden.json"
        secret.write_text('{"password":"LOCAL-PASSWORD"}')
        self.file.symlink_to(secret)
        out = source_status.read_report(path=self.file, now=100)
        self.assertFalse(out["observations_available"])
        self.assertNotIn("PASSWORD", json.dumps(out))
        self.file.unlink()
        self.file.write_text('{"updated_at":100,"updated_at":100}')
        self.file.chmod(0o600)
        self.assertFalse(source_status.read_report(path=self.file, now=100)[
            "observations_available"])
        self.file.write_text('{"updated_at":100}')
        self.file.chmod(0o644)
        self.assertFalse(source_status.read_report(path=self.file, now=100)[
            "observations_available"])

    def test_anonymized_poll_observations_never_report_unmatched_or_invalid_nodes(self):
        mapping = {"AA:BB:CC:DD:EE:FF": "music"}
        bad_sources = [
            {"address": "11:22:33:44:55:66", "name": "bluez_input.a"},
            {"address": "AA:BB:CC:DD:EE:FF", "name": "../untrusted"},
        ]
        report = runtime.observed_source_slots(
            bad_sources, mapping, {}, {"audiohub.music": 1},
            lan_slot="laptop", policy_valid=True, usb_ready=False)
        self.assertTrue(report["music"]["bluetooth_assigned"])
        self.assertFalse(report["music"]["bluetooth_node_observed"])
        self.assertFalse(report["music"]["managed_loopback_running"])
        self.assertFalse(report["music"]["usb_route_ready"])
        self.assertFalse(report["tablet"]["bluetooth_assigned"])

    def test_invalid_route_policy_suppresses_stale_assignments_and_processes(self):
        mac = "AA:BB:CC:DD:EE:FF"
        report = runtime.observed_source_slots(
            [{"address": mac, "name": "bluez_input.demo"}],
            {mac: "music"},
            {mac: ("bluez_input.demo", "audiohub.music", FakeProcess())},
            {"audiohub.music": 1}, lan_slot="laptop",
            policy_valid=False, usb_ready=False)
        self.assertFalse(report["music"]["bluetooth_assigned"])
        self.assertFalse(report["music"]["bluetooth_node_observed"])
        self.assertFalse(report["music"]["managed_loopback_running"])

    def test_dead_loopback_never_counts_as_running_audio(self):
        mac = "AA:BB:CC:DD:EE:FF"
        report = runtime.observed_source_slots(
            [{"address": mac, "name": "bluez_input.demo"}],
            {mac: "music"},
            {mac: ("bluez_input.demo", "audiohub.music", FakeProcess(False))},
            {"audiohub.music": 1}, lan_slot="laptop",
            policy_valid=True, usb_ready=True)
        self.assertTrue(report["music"]["bluetooth_node_observed"])
        self.assertFalse(report["music"]["managed_loopback_running"])

    def test_source_routes_status_command_is_read_only_and_forbids_write_flags(self):
        expected = source_status.interpret({}, now=100)
        with (mock.patch.object(source_status, "read_report",
                                return_value=expected) as show,
              mock.patch.object(source_routes, "update") as writer):
            with redirect_stdout(StringIO()) as out:
                source_routes.main(["status"])
            self.assertEqual(json.loads(out.getvalue()), expected)
            show.assert_called_once()
            writer.assert_not_called()
        token = "r1-" + "a" * 64
        for args in (["--preview", "status"],
                     ["--confirm-local-route-change", "status"],
                     ["--if-preview-revision", token, "status"]):
            with self.subTest(args=args):
                with (mock.patch.object(source_status, "read_report") as show,
                      mock.patch.object(source_routes, "update") as writer):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            source_routes.main(args)
                    self.assertEqual(failed.exception.code, 2)
                    show.assert_not_called()
                    writer.assert_not_called()

    def test_runtime_poll_writes_observed_slots_but_not_device_identifiers(self):
        from audiohub import runtime as live
        from unittest.mock import Mock
        from audiohub.source_routes import defaults as route_defaults
        mac = "AA:BB:CC:DD:EE:FF"
        supervisor = live.Supervisor.__new__(live.Supervisor)
        supervisor.settings = defaults()
        supervisor.assignments = {mac: "music"}
        supervisor.loopbacks = {mac: ("bluez_input.demo", "audiohub.music", FakeProcess())}
        supervisor.retry_state = {}
        supervisor.route_failures_total = 0
        supervisor.output_switch_failures = 0
        supervisor.last_default = None
        supervisor.route_plan = route_defaults()
        supervisor.route_policy_valid = True
        sources = [{"address": mac, "name": "bluez_input.demo"}]
        sinks = {"audiohub.music": 11, "audiohub.laptop": 12,
                 "audiohub.tablet": 13}
        links = {"links_inspected": 0,
                 "eq_output_to_usb_direct_link": {
                     slot: False for slot in CHANNELS}}
        responses = Mock(returncode=0, stdout="[]")
        with (mock.patch.object(live, "run", return_value=responses),
              mock.patch.object(live, "pipewire_nodes", return_value=[]),
              mock.patch.object(live, "summarize_links", return_value=links),
              mock.patch.object(live, "choose_usb_output", return_value={"id": 10}),
              mock.patch.object(live, "bluetooth_sources", return_value=sources),
              mock.patch.object(live, "virtual_sinks", return_value=sinks),
              mock.patch.object(live, "load_routes", return_value=route_defaults()),
              mock.patch.object(live, "read_json", return_value=defaults()),
              mock.patch.object(live, "volume_commands", return_value=[]),
              mock.patch.object(supervisor, "_route"),
              mock.patch.object(live, "atomic_json") as save):
            supervisor.poll()
        save.assert_called_once()
        data = save.call_args.args[1]
        self.assertEqual(data["source_slot_observations_version"], 1)
        self.assertTrue(data["source_slot_observations"]["music"][
            "bluetooth_node_observed"])
        self.assertTrue(data["source_slot_observations"]["music"][
            "managed_loopback_running"])
        self.assertTrue(data["source_slot_observations"]["laptop"][
            "lan_reserved"])
        self.assertNotIn(mac, json.dumps(data))
        self.assertNotIn("bluez_input.demo", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
