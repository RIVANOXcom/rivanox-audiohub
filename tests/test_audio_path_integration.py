"""AudioHub: audio path integration regression tests (no device assumed)."""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import runtime
from audiohub.discovery import (
    pipewire_nodes, props, choose_usb_output, bluetooth_sources, virtual_sinks,
)

PHONE = "AA:BB:CC:DD:EE:FF"
PHONE2 = "00:11:22:33:44:55"
PHONE3 = "DD:EE:11:22:33:44"


def node(ident, name, media_class, **other):
    return {"type": "PipeWire:Interface:Node", "id": ident,
            "info": {"props": {"node.name": name, "media.class": media_class, **other}}}


def bt_node(ident=5, address=PHONE):
    return node(ident, "bluez_input." + address.replace(":", "_") + ".0",
                "Audio/Source", **{"api.bluez5.address": address})


def speaker(ident=11):
    return node(ident, "alsa_output.usb-Edifier_R600USB", "Audio/Sink")


def mixer_nodes():
    return [
        speaker(),
        bt_node(),
        node(21, "audiohub.music", "Audio/Sink"),
        node(22, "audiohub.tablet", "Audio/Sink"),
        node(23, "audiohub.laptop", "Audio/Sink"),
    ]


class Process:
    def __init__(self, alive=True):
        self.alive = alive
        self.terminated = False

    def poll(self):
        return None if self.alive else 1

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout=2):
        return 0

    def kill(self):
        self.alive = False


class AudioPathTests(unittest.TestCase):
    def supervisor(self, *, assignments=None):
        obj = runtime.Supervisor.__new__(runtime.Supervisor)
        obj.assignments = {PHONE: "music"} if assignments is None else assignments
        obj.loopbacks = {}
        obj.retry_state = {}
        obj.route_failures_total = 0
        obj.output_switch_failures = 0
        obj.settings = runtime.defaults()
        obj.last_default = None
        return obj

    def src(self, address=PHONE):
        return {"name": "bluez_input." + address.replace(":", "_") + ".0",
                "address": address}

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_explicit_capture_routes_to_eq_not_direct_usb_or_hdmi(self, launch):
        launch.return_value = Process()
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=100)
        argv = launch.call_args.args[0]
        self.assertEqual(argv, [
            "pw-loopback", "--name", "audiohub-music", "--channels", "2",
            "--capture", "bluez_input.AA_BB_CC_DD_EE_FF.0",
            "--playback", "audiohub.music",
        ])
        self.assertNotIn("alsa_output", " ".join(argv))
        self.assertNotIn("shell", str(launch.call_args.kwargs))

    def test_rejects_unsupported_or_injected_capture_targets(self):
        for name, channel in (
            ("bluez_input.A;touch /tmp/x", "music"),
            ("bluez_input.first", "laptop"),
            ("alsa_output.usb-Edifier", "music"),
            ("bluez_input." + "A"*200, "music"),
            (None, "music"),
        ):
            with self.subTest(name=str(name)[:25], channel=channel):
                with self.assertRaises(ValueError):
                    runtime.pipewire_loopback_args(name, channel)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_two_independent_bluetooth_sources_have_different_eq_sinks(self, launch):
        launch.side_effect = [Process(), Process()]
        s = self.supervisor(assignments={})
        s._route([self.src(PHONE), self.src(PHONE2)],
                 {"audiohub.music": 21, "audiohub.tablet": 22}, now=0)
        self.assertEqual(launch.call_count, 2)
        targets = [c.args[0][-1] for c in launch.call_args_list]
        self.assertEqual(set(targets), {"audiohub.music", "audiohub.tablet"})
        self.assertEqual(set(s.assignments.values()), {"music", "tablet"})

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_only_two_sources_admitted_even_when_three_present(self, launch):
        launch.side_effect = [Process(), Process(), Process()]
        s = self.supervisor(assignments={})
        s._route([self.src(PHONE), self.src(PHONE2), self.src(PHONE3)],
                 {"audiohub.music": 21, "audiohub.tablet": 22}, now=0)
        self.assertEqual(launch.call_count, 2)
        self.assertEqual(len(s.loopbacks), 2)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_no_route_without_verified_usb_sinks(self, launch):
        s = self.supervisor()
        s._route([self.src()], {}, now=0)
        launch.assert_not_called()

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_existing_healthy_route_is_not_restarted(self, launch):
        proc = Process()
        launch.return_value = proc
        s = self.supervisor()
        for second in (0, 5, 15, 30, 100):
            s._route([self.src()], {"audiohub.music": 21}, now=second)
        self.assertEqual(launch.call_count, 1)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_dead_process_retries_only_after_bounded_backoff(self, launch):
        first, second, third = Process(), Process(), Process()
        launch.side_effect = [first, second, third]
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=0)
        first.alive = False
        s._route([self.src()], {"audiohub.music": 21}, now=1)
        self.assertEqual(s.route_failures_total, 1)
        self.assertEqual(launch.call_count, 1)
        s._route([self.src()], {"audiohub.music": 21}, now=5)
        self.assertEqual(launch.call_count, 1)
        s._route([self.src()], {"audiohub.music": 21}, now=6)
        self.assertEqual(launch.call_count, 2)
        second.alive = False
        s._route([self.src()], {"audiohub.music": 21}, now=7)
        s._route([self.src()], {"audiohub.music": 21}, now=16)
        self.assertEqual(launch.call_count, 2)
        s._route([self.src()], {"audiohub.music": 21}, now=17)
        self.assertEqual(launch.call_count, 3)

    @mock.patch("audiohub.runtime.subprocess.Popen", side_effect=OSError("stream failed"))
    def test_repeated_spawn_failures_never_create_fork_bomb(self, launch):
        s = self.supervisor()
        for second in (0, 1, 5, 6, 7, 15, 16, 30, 31, 70, 71):
            s._route([self.src()], {"audiohub.music": 21}, now=second)
        self.assertLessEqual(launch.call_count, 5)
        self.assertEqual(s.route_failures_total, launch.call_count)
        self.assertLessEqual(max([x[1] for x in s.retry_state.values()]), 131)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_usb_unplug_terminates_routes_and_clears_failures(self, launch):
        proc = Process()
        launch.return_value = proc
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=0)
        s._route([self.src()], {}, now=1)
        self.assertTrue(proc.terminated)
        self.assertEqual(s.loopbacks, {})
        self.assertEqual(s.retry_state, {})

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_source_node_change_reconnects_without_old_target(self, launch):
        first, second = Process(), Process()
        launch.side_effect = [first, second]
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=0)
        changed = {"address": PHONE, "name": "bluez_input.AA_BB_CC_DD_EE_FF.1"}
        s._route([changed], {"audiohub.music": 21}, now=1)
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(first.terminated)

    def test_invalid_stored_assignments_do_not_grant_extra_channels(self):
        s = self.supervisor(assignments={
            PHONE: "music", PHONE2: "music", "non-mac": "tablet",
        })
        with mock.patch("audiohub.runtime.atomic_json") as write:
            s._assign([self.src(PHONE)])
        self.assertEqual(s.assignments, {PHONE2: "music", PHONE: "tablet"})
        write.assert_called_once()

    def test_capped_exponential_failure_delays(self):
        self.assertEqual([runtime.backoff_seconds(i) for i in range(1, 8)],
                         [5, 10, 20, 40, 60, 60, 60])

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_poll_routes_only_after_usb_default_succeeds(self, commands, launch, atomic):
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=0, stdout=json.dumps(mixer_nodes()) if args == ("pw-dump",) else ""
        )
        launch.return_value = Process()
        s = self.supervisor()
        s.poll()
        self.assertEqual(launch.call_count, 1)
        self.assertIn(("wpctl", "set-default", "11"),
                      [x.args for x in commands.call_args_list])
        output = atomic.call_args.args[1]
        self.assertTrue(output["usb_route_ready"])
        self.assertEqual(output["active_routes"], 1)
        self.assertEqual(output["route_start_failures"], 0)

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_failed_default_prevents_speaker_routes_and_volume(self, commands, launch, atomic):
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=1 if args[:2] == ("wpctl", "set-default") else 0,
            stdout=json.dumps(mixer_nodes()) if args == ("pw-dump",) else ""
        )
        s = self.supervisor()
        s.poll()
        launch.assert_not_called()
        output = atomic.call_args.args[1]
        self.assertTrue(output["usb_output"])
        self.assertFalse(output["usb_route_ready"])
        self.assertEqual(output["active_routes"], 0)
        self.assertEqual(output["output_switch_failures"], 1)
        self.assertNotIn(("wpctl", "set-volume", "11", "0.7"),
                         [x.args for x in commands.call_args_list])

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_no_usb_never_routes_to_hdmi_default(self, commands, launch, atomic):
        nodes = [
            node(15, "alsa_output.platform-hdmi", "Audio/Sink"), bt_node(),
            node(21, "audiohub.music", "Audio/Sink"),
        ]
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=0, stdout=json.dumps(nodes) if args == ("pw-dump",) else ""
        )
        s = self.supervisor()
        s.poll()
        launch.assert_not_called()
        self.assertFalse(atomic.call_args.args[1]["usb_route_ready"])
        self.assertNotIn("set-default", str(commands.call_args_list))

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_hot_unplug_stops_existing_route(self, commands, launch, atomic):
        current = [mixer_nodes(), [bt_node(), node(21, "audiohub.music", "Audio/Sink")]]
        def invoke(*args):
            if args == ("pw-dump",):
                return SimpleNamespace(returncode=0, stdout=json.dumps(current.pop(0)))
            return SimpleNamespace(returncode=0, stdout="")
        commands.side_effect = invoke
        proc = Process()
        launch.return_value = proc
        s = self.supervisor()
        s.poll()
        s.poll()
        self.assertTrue(proc.terminated)
        self.assertFalse(atomic.call_args.args[1]["usb_route_ready"])
        self.assertEqual(s.loopbacks, {})

    def test_malformed_pipewire_props_never_crash_discovery(self):
        values = [
            node(5, "bad", "Audio/Source"),
            {"type": "PipeWire:Interface:Node", "info": {"props": ["wrong"]}},
            {"type": "PipeWire:Interface:Node", "info": []},
            {"type": "PipeWire:Interface:Node", "info": {"props": None}},
        ]
        self.assertEqual(bluetooth_sources(values), [])
        self.assertEqual(virtual_sinks(values), {})
        self.assertIsNone(choose_usb_output(values))

    def test_bluetooth_addresses_are_valid_and_deduplicated(self):
        found = bluetooth_sources([bt_node(5), bt_node(6), bt_node(7, PHONE2)])
        self.assertEqual(len(found), 2)
        self.assertEqual({x["address"] for x in found}, {PHONE, PHONE2})

    def test_mismatched_bt_name_address_is_rejected(self):
        mismatch = bt_node()
        mismatch["info"]["props"]["api.bluez5.address"] = PHONE2
        self.assertEqual(bluetooth_sources([mismatch]), [])

    def test_bad_id_node_is_not_routed(self):
        values = [bt_node("5"), node(True, "audiohub.music", "Audio/Sink")]
        self.assertEqual(bluetooth_sources(values), [])
        self.assertEqual(virtual_sinks(values), {})

    def test_only_real_eq_channels_are_discovered(self):
        nodes = [
            node(1, "audiohub.music", "Audio/Sink"),
            node(2, "audiohub.hijack", "Audio/Sink"),
            node(3, "audiohub.music.output", "Audio/Sink"),
        ]
        self.assertEqual(virtual_sinks(nodes), {"audiohub.music": 1})

    def test_ambiguous_usb_hardware_is_not_selected(self):
        self.assertIsNone(choose_usb_output([
            node(1, "alsa_output.usb-card1", "Audio/Sink"),
            node(2, "alsa_output.usb-card2", "Audio/Sink"),
        ]))
        self.assertIsNone(choose_usb_output([
            node(1, "alsa_output.usb-Edifier1", "Audio/Sink"),
            node(2, "alsa_output.usb-Edifier2", "Audio/Sink"),
        ]))

    def test_single_generic_usb_sink_is_allowed_without_hdmi_fallback(self):
        self.assertEqual(choose_usb_output([
            node(3, "alsa_output.platform-hdmi", "Audio/Sink"),
            node(5, "alsa_output.usb-Generic_USB_Audio", "Audio/Sink"),
        ])["id"], 5)

    def test_wireplumber_uses_input_role_to_prevent_bypassing_eq(self):
        config = (ROOT / "image/stage-audiohub/01-install/files/wireplumber"
                  / "90-audiohub.conf").read_text()
        self.assertIn("bluez5.roles = [ a2dp_sink ]", config)
        self.assertIn('node.name = "~bluez_input.*"', config)
        self.assertIn("bluez5.media-source-role = input", config)
        self.assertIn("monitor.bluez.rules = [", config)


if __name__ == "__main__":
    unittest.main()
