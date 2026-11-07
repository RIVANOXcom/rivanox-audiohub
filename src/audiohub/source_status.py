# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only local, anonymized source evidence from one AudioHub poll.

PipeWire device-node observations and surviving managed routing processes are
NOT equivalent to Bluetooth connection, delivered PCM, or audible speakers.
Never promote these observations into release/hardware acceptance.
"""
from __future__ import annotations

import json
import time

from .mixer import CHANNELS
from .runtime import STATE, read_json

FRESH_SECONDS = 30
FIELDS = frozenset({
    "lan_reserved", "bluetooth_assigned", "bluetooth_node_observed",
    "managed_loopback_running", "virtual_sink_observed", "usb_route_ready",
})


def _valid_observations(raw):
    if type(raw) is not dict or set(raw) != set(CHANNELS):
        return False
    for values in raw.values():
        if (type(values) is not dict or set(values) != FIELDS
                or any(type(x) is not bool for x in values.values())):
            return False
        if values["lan_reserved"] and values["bluetooth_assigned"]:
            return False
        if ((values["bluetooth_node_observed"]
             or values["managed_loopback_running"])
                and not values["bluetooth_assigned"]):
            return False
    return True


def interpret(status, *, now=None):
    """Use only allowlisted fixed-slot booleans; stale evidence is UNKNOWN."""
    now = int(time.time() if now is None else now)
    if type(status) is not dict:
        status = {}
    updated = status.get("updated_at")
    fresh = (type(updated) is int and type(now) is int
             and 0 <= now - updated <= FRESH_SECONDS)
    policy_ok = status.get("route_policy_valid")
    raw = status.get("source_slot_observations")
    available = (fresh
                 and status.get("source_slot_observations_version") == 1
                 and type(status.get("source_slot_observations_version")) is int
                 and policy_ok is True and _valid_observations(raw))
    inputs = {}
    for slot in CHANNELS:
        details = raw[slot] if available else None
        if details is None:
            role = "unknown"
            configured = None
            discovered = None
            process_running = None
            virtual_sink = None
            usb = None
        else:
            role = ("lan_reserved" if details["lan_reserved"] else
                    "bluetooth_assigned" if details["bluetooth_assigned"] else
                    "unassigned")
            configured = details["lan_reserved"] or details["bluetooth_assigned"]
            discovered = (details["bluetooth_node_observed"]
                          if details["bluetooth_assigned"] else None)
            process_running = (details["managed_loopback_running"]
                               if details["bluetooth_assigned"] else None)
            virtual_sink = details["virtual_sink_observed"]
            usb = details["usb_route_ready"]
        inputs[slot] = {
            "configured_role": role,
            "configured": configured,
            "bluetooth_source_node_seen": discovered,
            "managed_loopback_process_running": process_running,
            "virtual_sink_observed": virtual_sink,
            "usb_route_ready": usb,
            "bluetooth_connected": "unverified",
            "audio_stream_available": "unverified",
            "audible_playback": "unverified",
        }
    return {
        "mode": "local-source-observations-read-only",
        "fresh": bool(fresh),
        "observations_available": bool(available),
        "status_age_seconds": now - updated if fresh else None,
        "route_policy_valid": policy_ok if fresh and type(policy_ok) is bool else None,
        "inputs": inputs,
        "interpretation": (
            "Source node seen is only a PipeWire observation; a managed "
            "loopback process running is not proof of Bluetooth connection, "
            "delivered PCM, an audible speaker, or hardware acceptance."
        ),
        "source_settings_written": False,
        "hardware_verified": False,
        "release_ready": False,
    }


def read_report(*, path=None, now=None):
    """Read one local owner-private runtime status JSON without writing."""
    return interpret(read_json(STATE if path is None else path, {}), now=now)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Read-only local source evidence; NOT connected/audio proof")
    parser.parse_args(argv)
    print(json.dumps(read_report(), sort_keys=True))


if __name__ == "__main__":
    main()
