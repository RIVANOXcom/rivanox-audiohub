# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only, privacy-bounded PipeWire EQ-to-USB link observations.

PipeWire Node presence does not prove that an EQ output actually reaches the
selected USB speaker. Link records can provide stronger *topology* evidence,
but still cannot prove audible sound, volume, clipping or correct Bluetooth
capture. No raw node metadata, addresses, MACs or port IDs escape the summary.
"""
from __future__ import annotations

from .discovery import (_conflicting_node_ids, _parse_pipewire_graph,
                        choose_usb_output, pipewire_nodes, props)

CHANNELS = ("music", "laptop", "tablet")
MAX_GRAPH_OBJECTS = 8192


def _id(value):
    return value if type(value) is int and 0 <= value <= 2**31 - 1 else None


def _parse(raw):
    # Never parse links more permissively than their companion Node IDs.
    graph = _parse_pipewire_graph(raw)
    return graph if graph is not None and len(graph) <= MAX_GRAPH_OBJECTS else None


def summarize_links(raw):
    """Observe only explicit PipeWire Link output-node -> input-node edges.

    Missing links are *not* proof that there is no sound: PipeWire can use
    additional adapter/monitor nodes. We only report positive, directly
    evidenced EQ-output-to-selected-USB edges, never infer an audio path
    from matching names or counts alone.
    """
    graph = _parse(raw)
    blank = {
        "inspection_available": False,
        "eq_output_to_usb_direct_link": {name: False for name in CHANNELS},
        "links_inspected": 0,
        "malformed_links": 0,
        "release_ready": False,
    }
    if graph is None:
        return blank
    nodes = pipewire_nodes(graph)
    if _conflicting_node_ids(nodes):
        return blank
    usb = choose_usb_output(nodes)
    usb_id = _id(usb.get("id")) if usb is not None else None
    names = {}
    invalid_names = set()
    for node in nodes:
        nid = _id(node.get("id"))
        name = props(node).get("node.name")
        if nid is None or type(name) is not str:
            continue
        if name in names:
            invalid_names.add(name)
        else:
            names[name] = nid
    candidates = {
        slot: names.get("audiohub." + slot + ".output")
        if "audiohub." + slot + ".output" not in invalid_names else None
        for slot in CHANNELS
    }
    connected = dict.fromkeys(CHANNELS, False)
    count = 0
    bad = 0
    # Untrusted pipewire snapshot: only documented Link info node IDs count.
    # Properties such as "link.output.node" may contain untrusted free text.
    seen_links = set()
    for obj in graph:
        if type(obj) is not dict or obj.get("type") != "PipeWire:Interface:Link":
            continue
        info = obj.get("info")
        output_id = _id(info.get("output-node-id")) if type(info) is dict else None
        input_id = _id(info.get("input-node-id")) if type(info) is dict else None
        if output_id is None or input_id is None or output_id == input_id:
            bad += 1
            continue
        edge = (output_id, input_id)
        if edge in seen_links:
            # Stereo L/R links legitimately share source and destination
            # *node* IDs while their port IDs differ. We aggregate a
            # single node-level edge; it is not malformed or a second path.
            continue
        seen_links.add(edge)
        count += 1
        if usb_id is None or input_id != usb_id:
            continue
        for slot in CHANNELS:
            if candidates[slot] == output_id:
                connected[slot] = True
    return {
        "inspection_available": True,
        "eq_output_to_usb_direct_link": connected,
        "links_inspected": min(count, MAX_GRAPH_OBJECTS),
        "malformed_links": min(bad, MAX_GRAPH_OBJECTS),
        "release_ready": False,
    }
