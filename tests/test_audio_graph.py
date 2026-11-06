"""Privacy-safe PipeWire graph connectivity tests; no Pi hardware required."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.audio_graph import summarize_links
from audiohub.hardware_preflight import inspect_topology


def node(ident, name, kind="Audio/Sink"):
    return {
        "id": ident, "type": "PipeWire:Interface:Node",
        "info": {"props": {"node.name": name, "media.class": kind,
                           "device.serial": "PRIVATE-SERIAL"}},
    }


def link(output, target):
    return {
        "type": "PipeWire:Interface:Link",
        "info": {"output-node-id": output, "input-node-id": target,
                 "props": {"link.output.port": "PRIVATE-PORT"}},
    }


def graph():
    return [
        node(10, "alsa_output.usb-EDIFIER_R600USB"),
        node(21, "audiohub.music"),
        node(22, "audiohub.laptop"),
        node(23, "audiohub.tablet"),
        node(31, "audiohub.music.output", "Audio/Source"),
        node(32, "audiohub.laptop.output", "Audio/Source"),
        node(33, "audiohub.tablet.output", "Audio/Source"),
    ]


class LinkEvidenceTests(unittest.TestCase):
    def test_actual_three_direct_links_are_observed(self):
        report = summarize_links(graph() + [link(31, 10), link(32, 10), link(33, 10)])
        self.assertTrue(report["inspection_available"])
        self.assertEqual(report["links_inspected"], 3)
        self.assertEqual(report["eq_output_to_usb_direct_link"],
                         {"music": True, "laptop": True, "tablet": True})
        self.assertFalse(report["release_ready"])

    def test_presence_only_does_not_fake_a_link(self):
        result = inspect_topology(graph())
        self.assertTrue(result["checks"]["edifier_usb_sink_unique"])
        self.assertTrue(all(result["checks"]["virtual_sink_unique"].values()))
        self.assertFalse(any(result["link_observation"]["eq_output_to_usb_direct_link"].values()))
        self.assertFalse(result["release_ready"])

    def test_unrelated_or_reversed_edges_cannot_pass(self):
        found = summarize_links(graph() + [link(10, 31), link(33, 21), link(31, 32)])
        self.assertFalse(any(found["eq_output_to_usb_direct_link"].values()))

    def test_disconnected_channel_never_inferred_from_two_others(self):
        found = summarize_links(graph() + [link(31, 10), link(33, 10)])
        self.assertEqual(found["eq_output_to_usb_direct_link"],
                         {"music": True, "laptop": False, "tablet": True})

    def test_ambiguous_usb_outputs_fail_closed(self):
        found = summarize_links(graph() + [
            node(11, "alsa_output.usb-EDIFIER_SECOND"), link(31, 10)
        ])
        self.assertFalse(found["eq_output_to_usb_direct_link"]["music"])

    def test_duplicate_unrelated_node_id_blocks_positive_link_evidence(self):
        g = graph() + [
            node(31, "untrusted.unrelated", "Audio/Source"),
            link(31, 10),
        ]
        summary = summarize_links(g)
        self.assertFalse(summary["inspection_available"])
        self.assertFalse(summary["eq_output_to_usb_direct_link"]["music"])
        self.assertFalse(summary["release_ready"])

    def test_duplicate_eq_node_name_is_ambiguous(self):
        found = summarize_links(graph() + [
            node(44, "audiohub.music.output", "Audio/Source"), link(31, 10)
        ])
        self.assertFalse(found["eq_output_to_usb_direct_link"]["music"])

    def test_bad_link_ids_and_duplicate_edges_do_not_count(self):
        found = summarize_links(graph() + [
            link(31, 10), link(31, 10), link(True, 10),
            link(-1, 10), link(31, 31),
            {"type": "PipeWire:Interface:Link", "info": "invalid"},
        ])
        self.assertTrue(found["eq_output_to_usb_direct_link"]["music"])
        self.assertEqual(found["links_inspected"], 1)
        self.assertEqual(found["malformed_links"], 4)

    def test_two_stereo_port_links_share_one_valid_node_edge(self):
        # A normal stereo connection can have two distinct PipeWire Port
        # links between the same source and sink Node IDs.
        report = summarize_links(graph() + [link(31, 10), link(31, 10)])
        self.assertTrue(report["eq_output_to_usb_direct_link"]["music"])
        self.assertEqual(report["links_inspected"], 1)
        self.assertEqual(report["malformed_links"], 0)

    def test_raw_secrets_are_not_reported(self):
        raw = json.dumps(graph() + [link(31, 10), {
            "type": "PipeWire:Interface:Link",
            "info": {"output-node-id": 99, "input-node-id": 10,
                     "props": {"password": "PRIVATE-WIFI", "bluetooth.address": "AA:BB"}},
        }])
        summary = json.dumps(summarize_links(raw))
        for secret in ("PRIVATE-SERIAL", "PRIVATE-WIFI", "AA:BB", "EDIFIER_R600USB"):
            self.assertNotIn(secret, summary)

    def test_malformed_and_oversized_snapshots_never_pass(self):
        for raw in (None, {}, "oops", False, ["bad"], [None],
                    [{"type": "PipeWire:Interface:Link", "info": {"output-node-id": "31"}}],
                    [None] * 8193):
            with self.subTest(raw=repr(raw)[:35]):
                result = summarize_links(raw)
                self.assertFalse(any(result["eq_output_to_usb_direct_link"].values()))
                self.assertFalse(result["release_ready"])

    def test_preflight_only_reports_topology_not_audio_acceptance(self):
        report = inspect_topology(graph() + [link(31, 10)])
        self.assertTrue(report["link_observation"]["eq_output_to_usb_direct_link"]["music"])
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["hardware_gates"]["speaker_audible"], "unverified")


if __name__ == "__main__":
    unittest.main()
