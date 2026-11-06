"""No-hardware tests for privacy-safe AudioHub acceptance preflight."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import hardware_preflight as preflight


def make_node(number, name, media_class, **extra):
    return {
        "id": number,
        "type": "PipeWire:Interface:Node",
        "info": {"props": {
            "node.name": name,
            "media.class": media_class,
            **extra,
        }},
    }


def topology():
    return [
        make_node(12, "alsa_output.usb-EDIFIER_R600USB", "Audio/Sink",
                  **{"node.description": "Edifier USB Speaker"}),
        make_node(20, "audiohub.music", "Audio/Sink"),
        make_node(21, "audiohub.laptop", "Audio/Sink"),
        make_node(22, "audiohub.tablet", "Audio/Sink"),
        make_node(30, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source",
                  **{"api.bluez5.address": "AA:BB:CC:DD:EE:FF",
                     "device.serial": "CUSTOMER-PRIVATE"}),
    ]


class HardwarePreflightTests(unittest.TestCase):
    def test_complete_topology_is_never_hardware_accepted(self):
        report = preflight.inspect_topology(topology())
        self.assertEqual(report["topology_preflight"], "ready_for_manual_test")
        self.assertTrue(report["checks"]["edifier_usb_sink_unique"])
        self.assertEqual(report["checks"]["bluetooth_source_count"], 1)
        self.assertEqual(report["checks"]["virtual_sink_unique"],
                         {"music": True, "laptop": True, "tablet": True})
        self.assertFalse(report["release_ready"])
        self.assertTrue(all(x == "unverified" for x in report["hardware_gates"].values()))

    def test_missing_laptop_channel_blocks_preflight(self):
        data = [node for node in topology() if node.get("id") != 21]
        report = preflight.inspect_topology(data)
        self.assertEqual(report["topology_preflight"], "incomplete")
        self.assertFalse(report["checks"]["virtual_sink_unique"]["laptop"])

    def test_duplicate_edifier_or_virtual_node_fails_closed(self):
        data = topology()
        data.append(make_node(99, "alsa_output.usb-another_edifier", "Audio/Sink"))
        self.assertFalse(preflight.inspect_topology(data)["checks"]["edifier_usb_sink_unique"])
        data = topology()
        data.append(make_node(99, "audiohub.tablet", "Audio/Sink"))
        self.assertFalse(preflight.inspect_topology(data)["checks"]["virtual_sink_unique"]["tablet"])

    def test_unrelated_usb_output_is_not_accepted_as_edifier(self):
        data = topology()
        data[0] = make_node(12, "alsa_output.usb-OTHER_USB", "Audio/Sink")
        self.assertFalse(preflight.inspect_topology(data)["checks"]["edifier_usb_sink_unique"])

    def test_duplicate_pipewire_id_blocks_manual_hardware_readiness(self):
        current = topology()
        current.append(make_node(
            30, "bluez_input.11_22_33_44_55_66.0", "Audio/Source"
        ))
        report = preflight.inspect_topology(current)
        self.assertEqual(report["topology_preflight"], "incomplete")
        self.assertFalse(report["hardware_gates"]["speaker_audible"] != "unverified")
        self.assertFalse(report["release_ready"])

    def test_wrong_media_class_or_invalid_identifier_ignored(self):
        data = topology()
        data[1] = make_node(True, "audiohub.music", "Audio/Sink")
        data[2] = make_node(-3, "audiohub.laptop", "Audio/Sink")
        data[3] = make_node(22, "audiohub.tablet", "Audio/Source")
        result = preflight.inspect_topology(data)
        self.assertFalse(result["checks"]["virtual_sink_unique"]["music"])
        self.assertFalse(result["checks"]["virtual_sink_unique"]["laptop"])
        self.assertFalse(result["checks"]["virtual_sink_unique"]["tablet"])

    def test_malformed_pipewire_properties_are_ignored(self):
        data = topology() + [
            {"type": "PipeWire:Interface:Node", "id": 56, "info": ["bad"]},
            {"type": "PipeWire:Interface:Node", "id": 57, "info": {"props": "bad"}},
            {"type": "PipeWire:Interface:Node", "id": 58, "info": {"props": {}}},
            {"type": "PipeWire:Interface:Node", "id": 59, "info": {"props": {
                "node.name": None, "media.class": "Audio/Sink"}}},
        ]
        report = preflight.inspect_topology(json.dumps(data))
        self.assertEqual(report["topology_preflight"], "ready_for_manual_test")

    def test_ambiguous_json_node_fields_do_not_falsely_complete_preflight(self):
        valid = json.dumps(topology())
        # Contradictory numeric Node ID in a single JSON object:
        # no last-wins normalization may produce topology-ready evidence.
        malformed = valid.replace('"id": 12', '"id": 999, "id": 12', 1)
        self.assertNotEqual(valid, malformed)
        result = preflight.inspect_topology(malformed)
        self.assertEqual(result["topology_preflight"], "incomplete")
        self.assertFalse(result["release_ready"])
        self.assertFalse(result["link_observation"]["inspection_available"])

    def test_invalid_dump_and_failed_query_cannot_pass(self):
        for raw in (None, "", "malformed json", "{}", "[]"):
            with self.subTest(raw=raw):
                self.assertEqual(preflight.inspect_topology(raw)["topology_preflight"],
                                 "incomplete")
        self.assertFalse(preflight.inspect_topology(topology(), query_ok=False)
                         ["checks"]["pipewire_inspection_succeeded"])

    def test_no_raw_identifiers_or_audio_payload_in_report(self):
        report = preflight.inspect_topology(topology())
        raw = json.dumps(report)
        for secret in ("AA:BB:CC:DD:EE:FF", "CUSTOMER-PRIVATE",
                       "alsa_output.usb-EDIFIER", "bluez_input.", "device.serial"):
            self.assertNotIn(secret, raw)

    @mock.patch("audiohub.hardware_preflight.bounded_command_output")
    def test_query_uses_timeout_no_shell_and_no_file_writes(self, run):
        run.return_value = subprocess.CompletedProcess(["pw-dump"], 0,
                                                        json.dumps(topology()), "")
        report = preflight.probe()
        self.assertTrue(report["checks"]["pipewire_inspection_succeeded"])
        run.assert_called_once_with(
            ("pw-dump",), timeout=5
        )

    @mock.patch("audiohub.hardware_preflight.bounded_command_output",
                return_value=None)
    def test_timeout_returns_incomplete_report(self, run):
        self.assertEqual(preflight.probe()["topology_preflight"], "incomplete")

    @mock.patch("audiohub.hardware_preflight.bounded_command_output",
                return_value=None)
    def test_missing_pipewire_utility_is_safe(self, run):
        report = preflight.probe()
        self.assertFalse(report["checks"]["pipewire_inspection_succeeded"])

    @mock.patch("audiohub.hardware_preflight.probe")
    def test_cli_return_code_only_confirms_topology(self, probe):
        probe.return_value = preflight.inspect_topology(topology())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(preflight.main(), 0)
        self.assertFalse(json.loads(output.getvalue())["release_ready"])
        probe.return_value = preflight.inspect_topology([])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(preflight.main(), 2)


if __name__ == "__main__":
    unittest.main()
