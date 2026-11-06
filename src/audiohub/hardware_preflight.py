# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only, privacy-preserving PipeWire topology preflight for AudioHub.

This utility cannot establish audible playback or approve a release. It never
changes device state, stores output, records peer IDs, or enables LAN audio.
"""
from __future__ import annotations

import json

from .process_capture import bounded_command_output
from .discovery import _conflicting_node_ids, pipewire_nodes
from .audio_graph import summarize_links

CHANNELS = ("music", "laptop", "tablet")


def _properties(node):
    """Treat external PipeWire metadata as untrusted unstructured input."""
    info = node.get("info")
    if not isinstance(info, dict):
        return {}
    props = info.get("props")
    return props if isinstance(props, dict) else {}


def _valid_node_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def inspect_topology(raw, *, query_ok=True):
    """Summarize topology with counts and booleans, without device identifiers.

    A connected source or an advertised USB sink is not proof of sound. The
    output purposely contains no name, MAC, serial, source IP, or raw log line.
    """
    nodes = pipewire_nodes(raw) if query_ok else []
    logical_counts = dict.fromkeys(CHANNELS, 0)
    edifier = 0
    bluetooth = 0
    for node in nodes:
        if not _valid_node_id(node.get("id")):
            continue
        props = _properties(node)
        media_class = props.get("media.class")
        name = props.get("node.name")
        if not isinstance(name, str):
            continue
        if media_class == "Audio/Sink":
            for channel in CHANNELS:
                if name == "audiohub." + channel:
                    logical_counts[channel] += 1
            if name.startswith("alsa_output.usb-"):
                details = " ".join(
                    str(props.get(field, ""))
                    for field in ("node.name", "node.description", "device.product.name")
                ).lower()
                if "edifier" in details:
                    edifier += 1
        if media_class == "Audio/Source" and name.startswith("bluez_input."):
            bluetooth += 1

    logical = {name: logical_counts[name] == 1 for name in CHANNELS}
    usb = edifier == 1
    # Even a fully present topology is only a *prerequisite* to hands-on tests.
    topology_ready = bool(query_ok and usb and all(logical.values())\n                          and not _conflicting_node_ids(nodes))
    return {
        "schema_version": 1,
        "assessment": "topology_only_not_hardware_acceptance",
        "topology_preflight": "ready_for_manual_test" if topology_ready else "incomplete",
        "checks": {
            "pipewire_inspection_succeeded": bool(query_ok),
            "edifier_usb_sink_unique": usb,
            "virtual_sink_unique": logical,
            "bluetooth_source_count": bluetooth,
        },
        "link_observation": summarize_links(raw if query_ok else None),
        "hardware_gates": {
            "speaker_audible": "unverified",
            "three_simultaneous_sources": "unverified",
            "per_channel_isolation": "unverified",
            "mix_clipping": "unverified",
            "wifi_owner_security": "unverified",
            "endurance_24h": "unverified",
        },
        "release_ready": False,
    }


def probe():
    """Use an argv-only, bounded, nonprivileged PipeWire read command."""
    result = bounded_command_output(("pw-dump",), timeout=5)
    if result is None:
        return inspect_topology(None, query_ok=False)
    return inspect_topology(
        result.stdout if result.returncode == 0 else None,
        query_ok=result.returncode == 0,
    )


def main():
    report = probe()
    print(json.dumps(report, sort_keys=True, indent=2))
    # Exit 0 means ONLY that expected topology exists, NOT device acceptance.
    return 0 if report["topology_preflight"] == "ready_for_manual_test" else 2


if __name__ == "__main__":
    raise SystemExit(main())
