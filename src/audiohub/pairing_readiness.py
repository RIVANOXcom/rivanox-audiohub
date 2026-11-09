# SPDX-License-Identifier: AGPL-3.0-only
"""Private, read-only Pi console guide to Bluetooth first-use readiness.

Only bounded aggregate BlueZ properties are inspected over the LOCAL system
D-Bus. Device addresses, names, paths, UUIDs and aliases are never emitted.
No Discoverable/Pairable/Trusted changes, pairing calls, sockets, file writes,
owner authentication or new-device enrollment. This is an ALPHA observation.
"""
from __future__ import annotations

import argparse
import json
import re
import time

CLASSIFICATION = "UNVERIFIED_LOCAL_BLUETOOTH_OBSERVATION"
BOOT_WINDOW = 600
PAIRING_LIMIT = 2
MAX_OBJECTS = 256
ADAPTER_PATH = re.compile(r"/org/bluez/hci[0-9]{1,3}\Z")

# These are informational states. None constitutes an authenticated owner.
MESSAGES = {
    "unavailable": (
        "BlueZ controller status cannot be read.",
        "Check Bluetooth service and physical controller locally; do not reset pairing permissions."
    ),
    "ambiguous_adapter": (
        "No unique Pi Bluetooth controller was identified.",
        "Use a physically trusted Pi console to inspect adapters. No pairing was changed."
    ),
    "controller_off": (
        "Bluetooth controller is currently powered off.",
        "Check local power and Bluetooth service before attempting device discovery."
    ),
    "unexpected_open": (
        "Bluetooth discovery or pairing is open despite existing paired records or expired boot window.",
        "Do not add an unknown device. Inspect the BlueZ agent and close any unintended pairing window locally."
    ),
    "initial_window_observed": (
        "The unclaimed experimental first-pair window appears visible.",
        "Only in an isolated, owner-supervised lab: open Bluetooth on your intended phone and look for AudioHub. "
        "NoInputNoOutput is not proof of ownership; nearby devices may also attempt pairing."
    ),
    "window_closed": (
        "The experimental pairing window is closed or not observable.",
        "Existing firmware has no approved post-claim pairing UI. Do not bypass this by rebooting or opening public access."
    ),
    "paired_untrusted": (
        "A Bluetooth pairing record is present without complete trust state.",
        "Do not assume an audio source will reconnect; have the owner review the device locally."
    ),
    "known_devices": (
        "One or more paired and trusted Bluetooth records exist.",
        "Use the existing device's Bluetooth menu to reconnect, then verify audible audio on the physical speaker. "
        "This does not prove ownership or concurrent two-source playback."
    ),
    "device_limit": (
        "The experimental paired-device limit has been reached.",
        "Existing devices may reconnect. Additional device enrollment requires a separately approved private workflow."
    ),
    "inconsistent": (
        "Bluetooth records are inconsistent or exceed the supported limits.",
        "Do not change pairing remotely. Inspect the local BlueZ setup with a trusted operator."
    ),
}


def _flag(value):
    # Strict booleans only. A guessed integer or string must not claim readiness.
    return value if type(value) is bool else None


def _empty(state):
    return {
        "classification": CLASSIFICATION,
        "state": state,
        "controller_present": False,
        "powered": False,
        "pairable": False,
        "discoverable": False,
        "paired_devices": 0,
        "trusted_paired_devices": 0,
        "connected_paired_devices": 0,
        "first_boot_seconds_left": 0,
        "owner_authenticated": False,
        "pairing_performed": False,
        "hardware_audio_verified": False,
        "production_ready": False,
    }


def inspect_managed_objects(objects, uptime_seconds):
    """Derive strictly anonymous readiness from already-read BlueZ properties."""
    if (type(objects) is not dict or len(objects) > MAX_OBJECTS
            or type(uptime_seconds) not in (int, float)
            or not 0 <= uptime_seconds < 10**10):
        return _empty("unavailable")
    adapters = [
        (path, properties["org.bluez.Adapter1"])
        for path, properties in objects.items()
        if (type(path) is str and ADAPTER_PATH.fullmatch(path) is not None
            and type(properties) is dict
            and type(properties.get("org.bluez.Adapter1")) is dict)
    ]
    if len(adapters) != 1:
        return _empty("ambiguous_adapter")
    adapter_path, adapter = adapters[0]
    powered = _flag(adapter.get("Powered"))
    pairable = _flag(adapter.get("Pairable"))
    discoverable = _flag(adapter.get("Discoverable"))
    if any(value is None for value in (powered, pairable, discoverable)):
        return _empty("unavailable")

    paired = trusted = connected = 0
    for properties in objects.values():
        if type(properties) is not dict:
            return _empty("unavailable")
        device = properties.get("org.bluez.Device1")
        if device is None:
            continue
        if type(device) is not dict:
            return _empty("unavailable")
        # Devices on other controllers never count toward this adapter.
        if device.get("Adapter") != adapter_path:
            continue
        is_paired = _flag(device.get("Paired"))
        is_trusted = _flag(device.get("Trusted"))
        is_connected = _flag(device.get("Connected"))
        if any(value is None for value in (is_paired, is_trusted, is_connected)):
            return _empty("unavailable")
        paired += int(is_paired)
        trusted += int(is_paired and is_trusted)
        connected += int(is_paired and is_connected)

    remain = max(0, BOOT_WINDOW - int(uptime_seconds)) if paired == 0 else 0
    # These are observations of BlueZ, not a claim that the agent will permit
    # pairing; a service crash or other local configuration may differ.
    if not powered:
        state = "controller_off"
    elif paired > PAIRING_LIMIT:
        state = "inconsistent"
    elif (pairable or discoverable) and (paired > 0 or remain == 0):
        state = "unexpected_open"
    elif paired == PAIRING_LIMIT:
        state = "device_limit"
    elif paired > 0 and trusted < paired:
        state = "paired_untrusted"
    elif paired > 0:
        state = "known_devices"
    elif pairable and discoverable and remain > 0:
        state = "initial_window_observed"
    else:
        state = "window_closed"
    return {
        **_empty(state),
        "controller_present": True,
        "powered": powered,
        "pairable": pairable,
        "discoverable": discoverable,
        "paired_devices": min(paired, PAIRING_LIMIT + 1),
        "trusted_paired_devices": min(trusted, PAIRING_LIMIT + 1),
        "connected_paired_devices": min(connected, PAIRING_LIMIT + 1),
        "first_boot_seconds_left": remain,
    }


def _as_bool(value, dbus):
    # Normalize real DBus Boolean, never arbitrary strings or numeric flags.
    if isinstance(value, dbus.Boolean) or type(value) is bool:
        return bool(value)
    return None


def read_local_bluez(*, bus=None, uptime=None):
    """Only one local BlueZ GetManagedObjects call; NEVER call Set/Pair/Trust."""
    try:
        import dbus
        if bus is None:
            bus = dbus.SystemBus()
        manager = dbus.Interface(
            bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        objects = manager.GetManagedObjects(timeout=4)
        if len(objects) > MAX_OBJECTS:
            return _empty("unavailable")
        normalized = {}
        for path, props in objects.items():
            attrs = {}
            if "org.bluez.Adapter1" in props:
                adapter = props["org.bluez.Adapter1"]
                attrs["org.bluez.Adapter1"] = {
                    name: _as_bool(adapter.get(name), dbus)
                    for name in ("Powered", "Pairable", "Discoverable")
                }
            if "org.bluez.Device1" in props:
                device = props["org.bluez.Device1"]
                attrs["org.bluez.Device1"] = {
                    "Adapter": str(device.get("Adapter", "")),
                    **{name: _as_bool(device.get(name), dbus)
                       for name in ("Paired", "Trusted", "Connected")},
                }
            normalized[str(path)] = attrs
        return inspect_managed_objects(
            normalized, time.monotonic() if uptime is None else uptime
        )
    except (ImportError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
        return _empty("unavailable")
    except Exception:
        # D-Bus transport errors must not print device identifiers or paths.
        return _empty("unavailable")


def render_guide(snapshot):
    state = snapshot.get("state", "unavailable")
    label, action = MESSAGES.get(state, MESSAGES["unavailable"])
    left = snapshot.get("first_boot_seconds_left", 0)
    if state == "initial_window_observed":
        label += " Approximate boot-window time left: " + str(left) + " seconds."
    return (
        "RIVANOX AudioHub – local Bluetooth pairing check (ALPHA)\n"
        + label + "\n"
        + "Known paired: " + str(snapshot.get("paired_devices", 0))
        + " / experimental limit " + str(PAIRING_LIMIT) + ".\n"
        + "Next: " + action + "\n"
        + "This does not authenticate an owner or prove USB audio, Wi-Fi, "
          "Bluetooth compatibility or release readiness.\n"
        + "No device addresses, names or credentials are reported; "
          "no settings were changed."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="Emit only anonymous bounded local observation JSON")
    args = parser.parse_args(argv)
    snapshot = read_local_bluez()
    print(json.dumps(snapshot, sort_keys=True) if args.json else render_guide(snapshot))
    return 0 if snapshot["state"] not in ("unavailable", "ambiguous_adapter", "inconsistent", "unexpected_open") else 2


if __name__ == "__main__":
    raise SystemExit(main())
