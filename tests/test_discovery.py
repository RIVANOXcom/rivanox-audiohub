"""Discovery must not route audio to arbitrary unrelated hardware."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.discovery import pipewire_nodes, choose_usb_output, bluetooth_sources, virtual_sinks


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


    def test_duplicate_virtual_sink_name_blocks_all_routing(self):
        sinks = [
            node(10, "audiohub.music", "Audio/Sink"),
            node(11, "audiohub.laptop", "Audio/Sink"),
            node(12, "audiohub.music", "Audio/Sink"),
        ]
        self.assertEqual(virtual_sinks(sinks), {})

    def test_identical_duplicate_virtual_record_is_unsafe(self):
        one = node(10, "audiohub.music", "Audio/Sink")
        self.assertEqual(virtual_sinks([one, dict(one)]), {})

    def test_reused_node_id_for_two_channels_blocks_virtual_routes(self):
        sinks = [
            node(10, "audiohub.music", "Audio/Sink"),
            node(10, "audiohub.tablet", "Audio/Sink"),
        ]
        self.assertEqual(virtual_sinks(sinks), {})

    def test_reused_edifier_usb_node_id_blocks_output_selection(self):
        graph = [
            node(10, "alsa_output.usb-EDIFIER", "Audio/Sink"),
            node(10, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source"),
        ]
        self.assertIsNone(choose_usb_output(graph))

    def test_valid_virtual_channels_with_distinct_ids_continue(self):
        sinks = [
            node(10, "audiohub.music", "Audio/Sink"),
            node(11, "audiohub.tablet", "Audio/Sink"),
            node(12, "audiohub.laptop", "Audio/Sink"),
        ]
        self.assertEqual(virtual_sinks(sinks), {
            "audiohub.music": 10, "audiohub.tablet": 11, "audiohub.laptop": 12,
        })

    def test_duplicate_bt_mac_with_two_source_profiles_is_dropped(self):
        sources = [
            node(10, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source"),
            node(11, "bluez_input.AA_BB_CC_DD_EE_FF.1", "Audio/Source"),
        ]
        self.assertEqual(bluetooth_sources(sources), [])

    def test_ambiguous_bt_identity_does_not_disable_unrelated_source(self):
        sources = [
            node(10, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source"),
            node(11, "bluez_input.AA_BB_CC_DD_EE_FF.1", "Audio/Source"),
            node(12, "bluez_input.11_22_33_44_55_66.0", "Audio/Source"),
        ]
        result = bluetooth_sources(sources)
        self.assertEqual([entry["address"] for entry in result], ["11:22:33:44:55:66"])

    def test_conflicting_global_node_id_disables_all_bt_capture(self):
        nodes = [
            node(10, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source"),
            node(10, "audiohub.music", "Audio/Sink"),
        ]
        self.assertEqual(bluetooth_sources(nodes), [])

    def test_non_string_virtual_sink_metadata_is_ignored(self):
        graph = [node(10, ["audiohub.music"], "Audio/Sink"),
                 node(11, {"name": "audiohub.tablet"}, "Audio/Sink"),
                 node(12, "audiohub.music", "Audio/Sink")]
        self.assertEqual(virtual_sinks(graph), {"audiohub.music": 12})

    def test_existing_unambiguous_generic_usb_fallback_still_works(self):
        graph = [node(8, "alsa_output.usb-USB_Audio", "Audio/Sink")]
        self.assertEqual(choose_usb_output(graph)["id"], 8)

    def test_duplicate_node_identity_or_metadata_json_is_rejected(self):
        # Last-wins JSON must not bypass global Node-ID conflict detection.
        records = (
            '[{"type":"PipeWire:Interface:Node","id":1,"id":9,'
            '"info":{"props":{"node.name":"audiohub.music",'
            '"media.class":"Audio/Sink"}}}]',
            '[{"type":"PipeWire:Interface:Node","id":9,'
            '"info":{"props":{"node.name":"audiohub.music",'
            '"node.name":"alsa_output.usb-Edifier_R600USB",'
            '"media.class":"Audio/Sink"}}}]',
        )
        for raw in records:
            with self.subTest(raw=raw[:54]):
                self.assertEqual(pipewire_nodes(raw), [])

    def test_pipewire_graph_nonfinite_literals_and_exponents_are_rejected(self):
        for numeric in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            with self.subTest(numeric=numeric):
                raw = ('[{"type":"PipeWire:Interface:Node","id":1,'
                       '"info":{"props":{"extra":' + numeric + '}}}]')
                self.assertEqual(pipewire_nodes(raw), [])

    def test_nested_size_bounded_pipewire_metadata_fails_without_crash(self):
        for nesting in ("[" * 1500 + "0" + "]" * 1500,
                        '{"x":' * 650 + "0" + "}" * 650):
            with self.subTest(nesting=nesting[:10]):
                raw = '[{"type":"PipeWire:Interface:Node","id":1,' + (
                    '"info":{"props":{"nested":' + nesting + '}}}]'
                )
                self.assertEqual(pipewire_nodes(raw), [])

    def test_valid_pipewire_dump_still_selects_usb_and_bluetooth_nodes(self):
        graph = [
            node(3, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
            node(4, "bluez_input.AA_BB_CC_DD_EE_FF.0", "Audio/Source"),
        ]
        decoded = pipewire_nodes(json.dumps(graph))
        self.assertEqual(choose_usb_output(decoded)["id"], 3)
        self.assertEqual(len(bluetooth_sources(decoded)), 1)

    def test_invalid_pipewire_dump_is_safe(self):
        self.assertEqual(pipewire_nodes("bad JSON"), [])
        self.assertEqual(pipewire_nodes('{"anything": 1}'), [])


if __name__ == "__main__":
    unittest.main()
