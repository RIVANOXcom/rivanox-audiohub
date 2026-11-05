"""Three-path integration contracts without claiming physical Pi4 playback.

Synthetic PipeWire nodes cover two independent Bluetooth sources plus
an explicitly manual, isolated Windows Scream stereo receiver.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import network_laptop, runtime
from audiohub.discovery import bluetooth_sources, choose_usb_output, virtual_sinks
from audiohub.mixer import CHANNELS, defaults, mix_gain_budget, volume_commands
from audiohub.network_buffer import PcmPacketBuffer

BT1 = "AA:BB:CC:DD:EE:FF"
BT2 = "11:22:33:44:55:66"


def node(nid, name, media_class, **props):
    return {
        "type": "PipeWire:Interface:Node", "id": nid,
        "info": {"props": {"node.name": name, "media.class": media_class, **props}},
    }


def graph():
    return [
        node(10, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        node(21, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source",
             **{"api.bluez5.address": BT1}),
        node(22, "bluez_input.11_22_33_44_55_66.0", "Audio/Source",
             **{"api.bluez5.address": BT2}),
        node(31, "audiohub.music", "Audio/Sink"),
        node(32, "audiohub.laptop", "Audio/Sink"),
        node(33, "audiohub.tablet", "Audio/Sink"),
    ]


class Alive:
    def poll(self):
        return None
    def terminate(self):
        pass
    def wait(self, timeout=None):
        return 0


class ThreeInputIntegrationTests(unittest.TestCase):
    def test_three_channel_eq_graph_is_installed_separately(self):
        from audiohub.mixer import pipewire_filter_config
        config = pipewire_filter_config(defaults())
        self.assertEqual(config.count("libpipewire-module-filter-chain"), 3)
        for channel in CHANNELS:
            self.assertIn('node.name = "audiohub.' + channel + '"', config)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_two_bt_capture_streams_plus_manual_laptop_are_isolated(self, spawn):
        spawn.side_effect = [Alive(), Alive()]
        s = runtime.Supervisor.__new__(runtime.Supervisor)
        s.assignments = {BT1: "music", BT2: "tablet"}
        s.loopbacks = {}
        s.retry_state = {}
        s.route_failures_total = 0
        nodes = graph()
        self.assertEqual(choose_usb_output(nodes)["id"], 10)
        sinks = virtual_sinks(nodes)
        self.assertEqual(set(sinks), {"audiohub.music", "audiohub.laptop", "audiohub.tablet"})
        s._route(bluetooth_sources(nodes), sinks, now=0)
        self.assertEqual(spawn.call_count, 2)
        self.assertEqual(
            {c.args[0][-1] for c in spawn.call_args_list},
            {"audiohub.music", "audiohub.tablet"},
        )
        self.assertEqual(network_laptop.player_command()[8], "--target=audiohub.laptop")
        self.assertTrue(all(
            "audiohub.laptop" not in str(c.args[0]) for c in spawn.call_args_list
        ))

    def test_manual_laptop_pcm_is_48k_stereo_and_stays_in_its_eq_channel(self):
        pcm = bytes([0x12, 0x34, 0x56, 0x78]) * 288
        packet = bytes((1, 16, 2, 3, 0)) + pcm
        self.assertEqual(network_laptop.parse_scream_packet(packet), pcm)
        self.assertEqual(network_laptop.player_command()[0], "pw-cat")
        self.assertIn("--target=audiohub.laptop", network_laptop.player_command())
        self.assertEqual(len(pcm), 1152)
        self.assertEqual(len(pcm) // 4, 288)

    def test_all_channel_volume_mute_and_conservative_master_are_separate(self):
        cfg = defaults()
        cfg["master"] = 100
        for name in CHANNELS:
            cfg[name]["volume"] = 100
        commands = volume_commands(cfg, {"music": 31, "laptop": 32, "tablet": 33}, 10)
        self.assertEqual(mix_gain_budget(cfg), 1 / 3)
        self.assertIn(["wpctl", "set-volume", "10", str(1 / 3)], commands)
        for channel, ident in (("music", "31"), ("laptop", "32"), ("tablet", "33")):
            self.assertIn(["wpctl", "set-volume", ident, "1.0"], commands)
        cfg["laptop"]["mute"] = True
        commands = volume_commands(cfg, {"music": 31, "laptop": 32, "tablet": 33}, 10)
        self.assertIn(["wpctl", "set-mute", "32", "1"], commands)
        self.assertNotIn(["wpctl", "set-mute", "31", "1"], commands)
        self.assertEqual(mix_gain_budget(cfg), 0.5)

    def test_eq_boost_budget_counts_all_three_sources_not_just_bluetooth(self):
        cfg = defaults()
        cfg["master"] = 100
        for name in CHANNELS:
            cfg[name].update({"volume": 100, "bass": 12, "mid": 12, "treble": 12})
        self.assertLess(mix_gain_budget(cfg), 1 / 3)

    def test_sender_spoof_ip_filter_never_counts_as_authentication(self):
        good = bytes((1, 16, 2, 3, 0)) + bytes(1152)
        self.assertEqual(
            network_laptop.accepted_pcm(good, ("192.168.55.10", 4100), "192.168.55.10"),
            good[5:],
        )
        self.assertIsNone(
            network_laptop.accepted_pcm(good, ("192.168.55.11", 4100), "192.168.55.10")
        )
        with self.assertRaisesRegex(ValueError, "opt-in"):
            network_laptop.validate_options("192.168.55.10", "192.168.55.20", 4010, False)

    def test_buffer_holds_less_than_20_kb_even_under_packet_burst(self):
        buffer = PcmPacketBuffer(capacity=16, prefill=3)
        for _ in range(3000):
            buffer.append(bytes(1152))
        self.assertEqual(buffer.packet_count, 16)
        self.assertEqual(buffer.dropped_oldest, 2984)
        self.assertLessEqual(buffer.packet_count * 1152, 18432)

    def test_image_never_auto_starts_an_unauthenticated_network_receiver(self):
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text()
        self.assertNotIn("audiohub.network_laptop", installer)
        self.assertNotIn("--unsafe-lan-test", installer)
        for unit in (ROOT / "image/stage-audiohub/01-install/files/systemd").glob("*.service"):
            self.assertNotIn("audiohub.network_laptop", unit.read_text())
            self.assertNotIn("--unsafe-lan-test", unit.read_text())
        self.assertNotIn("audiohub.network_laptop", (
            ROOT / "image/stage-audiohub/01-install/files/systemd/audiohub-runtime.service"
        ).read_text())


if __name__ == "__main__":
    unittest.main()
