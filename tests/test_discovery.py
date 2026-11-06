"""Discovery must not route audio to arbitrary unrelated hardware."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.discovery import pipewire_nodes, choose_usb_output, bluetooth_sources


def node(nid, name, media_class, **props):
    return {"id": nid, "type": "PipeWire:Interface:Node",
            "info": {"props": {"node.name": name, "media.class": media_class, **props}}}


class DiscoveryTests(unittest.TestCase):
    def test_prefers_edifier(self):
        nodes = [
            node(1, "alsa_output.usb-Webcam", "Audio/Sink"),
            node(2, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        ]
        self.assertEqual(choose_usb_output(nodes)["id"], 2)

    def test_ambiguous_sink_safely_ignored(self):
        nodes = [node(1, "alsa_output.usb-A", "Audio/Sink"), node(2, "alsa_output.usb-B", "Audio/Sink")]
        self.assertIsNone(choose_usb_output(nodes))

    def test_bluetooth_source_address(self):
        nodes = [node(3, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source")]
        sources = bluetooth_sources(nodes)
        self.assertEqual(sources[0]["address"], "AA:BB:CC:DD:EE:FF")

    def test_oversized_json_text_and_graph_are_refused(self):
        from audiohub.discovery import (MAX_PIPEWIRE_GRAPH_BYTES,
                                        MAX_PIPEWIRE_GRAPH_OBJECTS)
        self.assertEqual(pipewire_nodes(" " * (MAX_PIPEWIRE_GRAPH_BYTES + 1)), [])
        self.assertEqual(pipewire_nodes([{}] * (MAX_PIPEWIRE_GRAPH_OBJECTS + 1)), [])

    def test_invalid_unicode_graph_is_refused_without_crashing(self):
        self.assertEqual(pipewire_nodes("\\ud800"), [])

    def test_invalid_pipewire_dump_is_safe(self):
        self.assertEqual(pipewire_nodes("bad JSON"), [])
        self.assertEqual(pipewire_nodes('{"anything": 1}'), [])


if __name__ == "__main__":
    unittest.main()
