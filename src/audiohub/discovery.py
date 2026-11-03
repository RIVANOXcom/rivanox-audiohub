# SPDX-License-Identifier: AGPL-3.0-only
"""Safe recognition of a USB speaker and Bluetooth PipeWire sources."""
from __future__ import annotations

import json
import re


def pipewire_nodes(raw):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [obj for obj in data if isinstance(obj, dict) and obj.get("type") == "PipeWire:Interface:Node"]


def props(node):
    return (node.get("info") or {}).get("props") or {}


def choose_usb_output(nodes):
    """Prefer matching Edifier USB; decline ambiguous unrelated outputs."""
    sinks = []
    for item in nodes:
        value = props(item)
        if value.get("media.class") != "Audio/Sink":
            continue
        name = str(value.get("node.name", ""))
        if not name.startswith("alsa_output.usb-"):
            continue
        sinks.append(item)
    matching = [
        item for item in sinks
        if "edifier" in " ".join(str(props(item).get(k, "")) for k in
            ("node.name", "node.description", "device.product.name")).lower()
    ]
    if len(matching) == 1:
        return matching[0]
    return sinks[0] if len(sinks) == 1 else None


def bluetooth_sources(nodes):
    sources = []
    for item in nodes:
        value = props(item)
        name = str(value.get("node.name", ""))
        if value.get("media.class") != "Audio/Source" or not name.startswith("bluez_input."):
            continue
        address = value.get("api.bluez5.address") or value.get("device.address")
        if not address:
            match = re.search(r"bluez_input\.([0-9A-Fa-f_]{17})", name)
            address = match.group(1).replace("_", ":") if match else name
        sources.append({"name": name, "address": str(address).upper(), "id": item.get("id")})
    return sources


def virtual_sinks(nodes):
    found = {}
    for item in nodes:
        value = props(item)
        name = str(value.get("node.name", ""))
        if value.get("media.class") == "Audio/Sink" and name.startswith("audiohub."):
            found[name] = item.get("id")
    return found
