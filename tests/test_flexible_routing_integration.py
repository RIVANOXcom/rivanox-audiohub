"""Actual supervisor routing and manual UDP target integration (synthetic nodes)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import runtime, network_laptop, source_routes

BT1 = "AA:BB:CC:DD:EE:FF"
BT2 = "11:22:33:44:55:66"
OTHER = "22:33:44:55:66:77"


def source(mac):
    return {"address": mac, "name": "bluez_input." + mac.replace(":", "_") + ".0"}


class Process:
    def __init__(self):
        self.alive = True
        self.terminated = False

    def poll(self):
        return None if self.alive else 1

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout=None):
        return 0


class FlexibleRoutingIntegration(unittest.TestCase):
    def supervisor(self, plan):
        s = runtime.Supervisor.__new__(runtime.Supervisor)
        s.route_plan = plan
        s.route_policy_valid = True
        s.assignments = {}
        s.loopbacks = {}
        s.retry_state = {}
        s.route_failures_total = 0
        s.output_switch_failures = 0
        s.settings = runtime.defaults()
        s.last_default = None
        return s

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_bt_feeds_any_two_non_lan_slots(self, spawn):
        plan = {"schema": source_routes.SCHEMA, "mode": "manual",
                "lan_slot": "music", "bluetooth": {BT1: "laptop", BT2: "tablet"}}
        spawn.side_effect = [Process(), Process()]
        s = self.supervisor(source_routes.validate(plan))
        s._route([source(BT1), source(BT2)],
                 {"audiohub.music": 31, "audiohub.laptop": 32,
                  "audiohub.tablet": 33}, now=0)
        self.assertEqual(spawn.call_count, 2)
        self.assertEqual(set(c.args[0][-1] for c in spawn.call_args_list),
                         {"audiohub.laptop", "audiohub.tablet"})
        self.assertNotIn("audiohub.music", str(spawn.call_args_list))
        self.assertEqual(s.assignments[BT1], "laptop")

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_manual_allowlist_does_not_assign_unknown_bt_peer(self, spawn):
        plan = {"schema": source_routes.SCHEMA, "mode": "manual",
                "lan_slot": "tablet", "bluetooth": {BT1: "laptop"}}
        spawn.return_value = Process()
        s = self.supervisor(source_routes.validate(plan))
        s._route([source(OTHER), source(BT1)],
                 {"audiohub.laptop": 42, "audiohub.music": 41,
                  "audiohub.tablet": 43}, now=0)
        self.assertEqual(spawn.call_count, 1)
        self.assertNotIn(OTHER, s.assignments)
        self.assertIn(BT1, s.loopbacks)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_reassignment_stops_old_capture_and_uses_new_sink(self, spawn):
        old, new = Process(), Process()
        spawn.side_effect = [old, new]
        s = self.supervisor(source_routes.validate({
            "schema": source_routes.SCHEMA, "mode": "manual",
            "lan_slot": "music", "bluetooth": {BT1: "tablet"},
        }))
        sinks = {"audiohub.music": 31, "audiohub.laptop": 32,
                 "audiohub.tablet": 33}
        s._route([source(BT1)], sinks, now=1)
        self.assertEqual(spawn.call_args.args[0][-1], "audiohub.tablet")
        s.route_plan = source_routes.validate({
            "schema": source_routes.SCHEMA, "mode": "manual",
            "lan_slot": "tablet", "bluetooth": {BT1: "music"},
        })
        s._route([source(BT1)], sinks, now=2)
        self.assertTrue(old.terminated)
        self.assertEqual(spawn.call_count, 2)
        self.assertEqual(spawn.call_args.args[0][-1], "audiohub.music")

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_two_authorized_bt_routes_recover_only_recreated_pipewire_nodes(self, spawn):
        """One renewed BlueZ or EQ node must not interrupt the other source."""
        old_first, stable_second, new_first, new_second = (
            Process(), Process(), Process(), Process())
        spawn.side_effect = [old_first, stable_second, new_first, new_second]
        plan = source_routes.validate({
            "schema": source_routes.SCHEMA, "mode": "manual",
            "lan_slot": "music", "bluetooth": {
                BT1: "laptop", BT2: "tablet",
            },
        })
        s = self.supervisor(plan)
        first, second = {**source(BT1), "id": 101}, {**source(BT2), "id": 201}
        sinks = {"audiohub.music": 31, "audiohub.laptop": 32,
                 "audiohub.tablet": 33}
        s._route([first, second], sinks, now=0)
        self.assertEqual(spawn.call_count, 2)
        self.assertEqual(s.route_node_generations, {
            BT1: (101, 32), BT2: (201, 33),
        })
        s._route([{**first, "id": 102}, second], sinks, now=1)
        self.assertTrue(old_first.terminated)
        self.assertFalse(stable_second.terminated)
        self.assertFalse(new_first.terminated)
        self.assertEqual(spawn.call_count, 3)
        self.assertEqual(s.route_node_generations, {
            BT1: (102, 32), BT2: (201, 33),
        })
        # A new tablet EQ filter sink ID affects only the second source.
        s._route([{**first, "id": 102}, second],
                 {**sinks, "audiohub.tablet": 34}, now=2)
        self.assertTrue(stable_second.terminated)
        self.assertFalse(new_first.terminated)
        self.assertFalse(new_second.terminated)
        self.assertEqual(spawn.call_count, 4)
        self.assertEqual(s.route_node_generations, {
            BT1: (102, 32), BT2: (201, 34),
        })
        # Neither a reconnect nor node re-creation changes the private
        # manual owner route plan or promotes unknown paired devices.
        self.assertEqual(s.assignments, {BT1: "laptop", BT2: "tablet"})
        self.assertNotIn(OTHER, s.assignments)
        s._route([first, second, source(OTHER)], {}, now=3)
        self.assertTrue(new_first.terminated)
        self.assertTrue(new_second.terminated)
        self.assertFalse(s.loopbacks)
        self.assertFalse(s.route_node_generations)
        self.assertFalse(s.retry_state)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_auto_mode_reserves_current_lan_slot(self, spawn):
        spawn.side_effect = [Process(), Process()]
        plan = source_routes.defaults()
        plan["lan_slot"] = "music"
        s = self.supervisor(plan)
        with mock.patch("audiohub.runtime.atomic_json"):
            s._route([source(BT1), source(BT2)],
                     {"audiohub.music": 31, "audiohub.laptop": 32,
                      "audiohub.tablet": 33}, now=0)
        self.assertEqual(set(s.assignments.values()), {"laptop", "tablet"})
        self.assertNotIn("audiohub.music", str(spawn.call_args_list))

    def test_network_player_targets_any_valid_virtual_sink(self):
        for slot in ("music", "laptop", "tablet"):
            self.assertIn("--target=audiohub." + slot,
                          network_laptop.player_command("audiohub." + slot))
        with self.assertRaises(ValueError):
            network_laptop.player_command("alsa_output.fake-hdmi")

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_network_manual_route_requires_eq_and_real_usb(self, execute):
        def node(nid, name):
            return {"type": "PipeWire:Interface:Node", "id": nid,
                    "info": {"props": {"node.name": name, "media.class": "Audio/Sink"}}}
        graph = [node(10, "alsa_output.usb-Edifier_R600USB"),
                 node(33, "audiohub.music")]
        execute.side_effect = [
            SimpleNamespace(returncode=0, stdout=json.dumps(graph)),
            SimpleNamespace(returncode=0, stdout=""),
        ]
        network_laptop.check_audio_target("audiohub.music")
        self.assertEqual(execute.call_args.args[0], ("wpctl", "set-default", "10"))
        self.assertEqual(execute.call_args.kwargs, {"timeout": 5})
        execute.side_effect = [SimpleNamespace(returncode=0, stdout=json.dumps(graph))]
        with self.assertRaises(RuntimeError):
            network_laptop.check_audio_target("audiohub.tablet")

    @mock.patch("audiohub.network_laptop.lan_target",
                side_effect=["audiohub.music", "audiohub.tablet"])
    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_manual_lan_receiver_exits_on_live_policy_change(
            self, socket, player, check, targets):
        # The first private route lookup occurs before the listener opens;
        # the second detects that its input reservation changed.
        with self.assertRaisesRegex(RuntimeError, "route changed"):
            network_laptop.serve("192.168.1.11", "127.0.0.1", 4010,
                                 unsafe_lan_test=True)
        check.assert_called_once_with("audiohub.music")
        socket.return_value.__enter__.return_value.bind.assert_called_once_with(
            ("127.0.0.1", 4010))
        player.assert_not_called()
        self.assertEqual(targets.call_count, 2)

    @mock.patch("audiohub.runtime.run")
    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_corrupted_private_route_plan_terminates_running_capture(
            self, spawn, atomic, execute):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "audiohub"
            directory.mkdir(mode=0o700)
            (directory / source_routes.FILENAME).write_text("bad json")
            old = Process()
            s = self.supervisor(source_routes.defaults())
            s.loopbacks = {BT1: (source(BT1)["name"], "audiohub.music", old)}
            def run(*args):
                return SimpleNamespace(returncode=0, stdout=(
                    json.dumps([
                        {"type":"PipeWire:Interface:Node","id":10,"info":{"props":{
                            "node.name":"alsa_output.usb-Edifier_R600USB",
                            "media.class":"Audio/Sink"}}},
                        {"type":"PipeWire:Interface:Node","id":31,"info":{"props":{
                            "node.name":"audiohub.music","media.class":"Audio/Sink"}}}
                    ]) if args == ("pw-dump",) else ""
                ))
            execute.side_effect = run
            with mock.patch.object(runtime, "CONFIG", directory):
                s.poll()
            self.assertFalse(s.route_policy_valid)
            self.assertTrue(old.terminated)
            self.assertEqual(s.loopbacks, {})
            spawn.assert_not_called()
            self.assertFalse(atomic.call_args.args[1]["route_policy_valid"])

    def test_unclaimed_status_does_not_expose_source_mac(self):
        from audiohub.webserver import public_status
        state = {"updated_at": 100, "usb_output": True,
                 "route_policy_valid": True,
                 "bluetooth_allowlist": [BT1, BT2]}
        payload = public_status(state, now=110)
        self.assertNotIn(BT1, json.dumps(payload))
        self.assertNotIn("bluetooth_allowlist", payload)
        self.assertNotIn("route_policy_valid", payload)


if __name__ == "__main__":
    unittest.main()
