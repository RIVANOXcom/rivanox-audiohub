# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed PipeWire discovery for USB playback and A2DP inputs.

No discovery result constitutes device ownership or a physical sound test.
"""
from __future__ import annotations

import json
import math
import re

_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z")
_BLUEZ_NAME = re.compile(r"bluez_input\.([0-9A-Fa-f_]{17})(?:\.[a-zA-Z0-9_.:-]{1,32})?\Z")
_CHANNEL_NAMES = frozenset(("audiohub.music", "audiohub.laptop", "audiohub.tablet"))
MAX_PIPEWIRE_GRAPH_BYTES = 4 * 1024 * 1024
MAX_PIPEWIRE_GRAPH_OBJECTS = 8192


def _unique_pipewire_members(pairs):
    """Duplicate Node IDs, Link endpoints, or metadata keys are ambiguous."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate PipeWire JSON member")
        result[key] = value
    return result


def _reject_pipewire_constant(_value):
    raise ValueError("Non-standard PipeWire JSON constant")


def _finite_pipewire_float(number):
    """Even standard JSON exponents can overflow to non-finite floats."""
    value = float(number)
    if not math.isfinite(value):
        raise ValueError("PipeWire JSON exponent overflow")
    return value


def _parse_pipewire_graph(raw):
    """Bound and validate exactly one shared Node/Link graph snapshot."""
    if type(raw) is str:
        try:
            if len(raw.encode("utf-8")) > MAX_PIPEWIRE_GRAPH_BYTES:
                return None
            raw = json.loads(
                raw,
                object_pairs_hook=_unique_pipewire_members,
                parse_constant=_reject_pipewire_constant,
                parse_float=_finite_pipewire_float,
            )
        except (UnicodeError, TypeError, ValueError, RecursionError):
            return None
    return raw if type(raw) is list and len(raw) <= MAX_PIPEWIRE_GRAPH_OBJECTS else None


def pipewire_nodes(raw):
    # Node selection and EQ Link observation must reject the same bad input.
    data = _parse_pipewire_graph(raw)
    if data is None:
        return []
    return [
        obj for obj in data
        if isinstance(obj, dict) and obj.get("type") == "PipeWire:Interface:Node"
    ]


def props(node):
    if not isinstance(node, dict):
        return {}
    info = node.get("info")
    if not isinstance(info, dict):
        return {}
    fields = info.get("props")
    return fields if isinstance(fields, dict) else {}


def _id(node):
    ident = node.get("id") if isinstance(node, dict) else None
    return ident if type(ident) is int and 0 <= ident <= 2**31 - 1 else None


def _conflicting_node_ids(nodes):
    """A PipeWire node ID must identify exactly one actual Node object.

    Duplicate records, even with different names or identical properties,
    are not a reliable routing graph. Refuse the entire affected snapshot.
    """
    seen = set()
    for item in nodes:
        ident = _id(item)
        if ident is None:
            continue
        if ident in seen:
            return True
        seen.add(ident)
    return False


def choose_usb_output(nodes):
    """Select exactly one Edifier or the sole unambiguous USB audio output."""
    if _conflicting_node_ids(nodes):
        return None
    sinks = []
    for item in nodes:
        value = props(item)
        if value.get("media.class") != "Audio/Sink" or _id(item) is None:
            continue
        name = value.get("node.name")
        if type(name) is not str or not name.startswith("alsa_output.usb-"):
            continue
        sinks.append(item)
    matching = [
        item for item in sinks
        if "edifier" in " ".join(
            str(props(item).get(k, ""))[:128]
            for k in ("node.name", "node.description", "device.product.name")
        ).lower()
    ]
    if len(matching) == 1:
        return matching[0]
    if len(matching) > 1:
        return None
    # Generic USB speakers can identify as "USB Audio Device"; only select
    # them when there is no competing USB sink. HDMI is never a fallback.
    return sinks[0] if len(sinks) == 1 else None


def bluetooth_sources(nodes):
    """Recognize only actual A2DP-style BlueZ source nodes with valid MACs.

    Unknown names or inconsistent addresses are ignored rather than treated
    as new pairing candidates. The MAC is kept only inside the local process.
    """
    if _conflicting_node_ids(nodes):
        return []
    result = []
    seen = set()
    conflicted = set()
    for item in nodes:
        value = props(item)
        name = value.get("node.name")
        if (value.get("media.class") != "Audio/Source"
                or type(name) is not str or len(name) > 128
                or _id(item) is None):
            continue
        match = _BLUEZ_NAME.fullmatch(name)
        if match is None:
            continue
        name_mac = match.group(1).replace("_", ":").upper()
        property_mac = value.get("api.bluez5.address") or value.get("device.address")
        if property_mac is not None:
            if (type(property_mac) is not str or _MAC.fullmatch(property_mac) is None
                    or property_mac.upper() != name_mac):
                continue
        if name_mac in seen:
            conflicted.add(name_mac)
            continue
        seen.add(name_mac)
        result.append({"name": name, "address": name_mac, "id": item["id"]})
    # An address with two eligible BlueZ source nodes is ambiguous.
    # Neither entry is safe to route; never trust whichever arrived first.
    return [source for source in result if source["address"] not in conflicted]


def virtual_sinks(nodes):
    if _conflicting_node_ids(nodes):
        return {}
    found = {}
    ambiguous = set()
    for item in nodes:
        value = props(item)
        name = value.get("node.name")
        ident = _id(item)
        if (value.get("media.class") == "Audio/Sink" and type(name) is str
                and name in _CHANNEL_NAMES and ident is not None):
            if name in found:
                ambiguous.add(name)
            else:
                found[name] = ident
    # One duplicate logical name makes the routing graph unreliable.
    # Dropping all sinks forces the active supervisor to stop managed routes.
    return {} if ambiguous else found
