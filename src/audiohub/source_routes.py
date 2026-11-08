# SPDX-License-Identifier: AGPL-3.0-only
"""Private offline source-to-slot policy, never remote ownership authority.

A route plan describes *which eligible* BlueZ source or manually started
Scream transport may use each stable mixer slot. It never pairs a Bluetooth
device, trusts a MAC as an identity, opens a UDP socket or grants ownership.
The existing untrusted Scream receiver remains opt-in in an isolated lab.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time

from .mixer import CHANNELS
from .process_capture import bounded_command_output

SCHEMA = "audiohub-source-routes/1"
FILENAME = "source-routes.json"
MAX_FILE_BYTES = 4096
MAC = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")
MODES = ("auto", "manual")


class StaleRoutePreview(ValueError):
    """A local route writer changed the policy after the operator's preview."""


def _check_revision(token):
    if (type(token) is not str or len(token) != 67
            or not token.startswith("r1-")
            or any(c not in "0123456789abcdef" for c in token[3:])):
        raise ValueError("Invalid local route preview revision")
    return token


def defaults():
    return {"schema": SCHEMA, "mode": "auto", "lan_slot": "laptop", "bluetooth": {}}


def canonical_mac(value):
    if type(value) is not str:
        raise ValueError("Bluetooth address must be a string")
    name = value.upper()
    if MAC.fullmatch(name) is None or name in (
            "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        raise ValueError("Invalid Bluetooth address")
    return name


def validate(plan):
    """Fail closed on unknown formats, aliases, conflicts and impossible routes."""
    if type(plan) is not dict or set(plan) != {"schema", "mode", "lan_slot", "bluetooth"}:
        raise ValueError("Invalid source route schema")
    if plan["schema"] != SCHEMA or plan["mode"] not in MODES:
        raise ValueError("Unsupported source route policy")
    if type(plan["lan_slot"]) is not str or plan["lan_slot"] not in CHANNELS:
        raise ValueError("LAN slot must be one of three stable mixer slots")
    bound = plan["bluetooth"]
    if type(bound) is not dict or len(bound) > 2:
        raise ValueError("At most two explicit Bluetooth sources")
    clean = {}
    used = {plan["lan_slot"]}
    for address, slot in bound.items():
        mac = canonical_mac(address)
        if mac != address or type(slot) is not str or slot not in CHANNELS:
            raise ValueError("Non-canonical source mapping")
        if slot in used:
            raise ValueError("Multiple sources would occupy one audio input")
        used.add(slot)
        clean[mac] = slot
    if plan["mode"] == "auto" and clean:
        raise ValueError("Auto discovery must not include manual allowlist")
    return {"schema": SCHEMA, "mode": plan["mode"],
            "lan_slot": plan["lan_slot"], "bluetooth": clean}


def _private_dir(path, *, create=False):
    """Walk every directory component without following an ancestor symlink."""
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if ".." in path.parts:
        raise ValueError("Route directory traversal is prohibited")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    dirfd = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            try:
                nextfd = os.open(component, flags, dir_fd=dirfd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=dirfd)
                except FileExistsError:
                    pass  # Concurrent creation still must pass O_NOFOLLOW.
                nextfd = os.open(component, flags, dir_fd=dirfd)
            os.close(dirfd)
            dirfd = nextfd
        st = os.fstat(dirfd)
        if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o077:
            raise PermissionError("Route directory must be user-owned and private")
        result = dirfd
        dirfd = None
        return result
    finally:
        if dirfd is not None:
            os.close(dirfd)


def _unique_route_members(pairs):
    """No last-wins duplicate keys in private audio routing policy."""
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("Duplicate private audio route member")
        seen[key] = value
    return seen


def _reject_route_constant(_value):
    raise ValueError("Non-standard private audio route number")


def _read(fd):
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=fd)
    except FileNotFoundError:
        return defaults()
    try:
        st = os.fstat(handle)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) & 0o077
                or st.st_size > MAX_FILE_BYTES):
            raise PermissionError("Unsafe source route policy file")
        raw = os.read(handle, MAX_FILE_BYTES + 1)
        if len(raw) != st.st_size:
            raise ValueError("Source route file changed during bounded read")
        try:
            decoded = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_route_members,
                parse_constant=_reject_route_constant,
            )
        except (UnicodeError, ValueError, RecursionError):
            # Do not echo peer addresses, route keys or raw private JSON.
            raise ValueError("Malformed private source route JSON") from None
        return validate(decoded)
    finally:
        os.close(handle)


def _route_identity(dirfd):
    """Return a stable private on-disk policy generation, or None if absent."""
    try:
        st = os.stat(FILENAME, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
            or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) & 0o077
            or st.st_size > MAX_FILE_BYTES):
        raise PermissionError("Unsafe private source route policy")
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _revision(plan, identity):
    encoded = json.dumps({"identity": identity, "policy": plan},
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "r1-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_policy(dirfd):
    """Reject a concurrent atomic/ABA policy replacement while reading."""
    before = _route_identity(dirfd)
    current = _read(dirfd)
    if before != _route_identity(dirfd):
        raise ValueError("Private audio route changed during preview")
    return current, _revision(current, before)


def _proposed(plan, action, value, slot=None):
    """One routing mutation model shared by actual local writes and preview."""
    new = validate(plan)
    if action == "set-lan":
        if type(value) is not str or value not in CHANNELS:
            raise ValueError("Unknown input slot")
        new["lan_slot"] = value
    elif action == "swap-lan":
        # A single all-or-nothing policy generation avoids the intermediate
        # unbind/restore steps required by a manually occupied target slot.
        if (type(value) is not str or value not in CHANNELS
                or value == new["lan_slot"] or new["mode"] != "manual"):
            raise ValueError("LAN swap requires another manual Bluetooth slot")
        owners = [address for address, dest in new["bluetooth"].items()
                  if dest == value]
        if len(owners) != 1:
            raise ValueError("Target slot needs one manually assigned Bluetooth source")
        old_lan_slot = new["lan_slot"]
        new["lan_slot"] = value
        new["bluetooth"][owners[0]] = old_lan_slot
    elif action == "swap-bt":
        # Move two explicitly assigned Bluetooth inputs in one valid policy
        # generation instead of temporary unbinding either source.
        if (new["mode"] != "manual"
                or type(value) is not str or value not in CHANNELS
                or type(slot) is not str or slot not in CHANNELS
                or slot == value or new["lan_slot"] in (value, slot)):
            raise ValueError("Swap needs two distinct manually assigned BT slots")
        from_device = [mac for mac, dest in new["bluetooth"].items()
                       if dest == value]
        to_device = [mac for mac, dest in new["bluetooth"].items()
                     if dest == slot]
        if len(from_device) != 1 or len(to_device) != 1:
            raise ValueError("Both Bluetooth input slots must be manually assigned")
        new["bluetooth"][from_device[0]] = slot
        new["bluetooth"][to_device[0]] = value
    elif action == "bind-bt":
        mac = canonical_mac(value)
        if type(slot) is not str or slot not in CHANNELS:
            raise ValueError("Unknown input slot")
        if new["mode"] == "auto":
            new["mode"] = "manual"
            new["bluetooth"] = {}
        new["bluetooth"][mac] = slot
    elif action == "unbind-bt":
        mac = canonical_mac(value)
        if new["mode"] != "manual" or mac not in new["bluetooth"]:
            raise ValueError("Bluetooth address is not manually bound")
        del new["bluetooth"][mac]
    elif action == "mode":
        if type(value) is not str or value not in MODES:
            raise ValueError("Invalid source policy mode")
        new["mode"] = value
        new["bluetooth"] = {}
    else:
        raise ValueError("Unknown local route operation")
    return validate(new)


def _slots(plan):
    assigned = {name: {"lan_reserved": name == plan["lan_slot"],
                       "manual_bluetooth_addresses": [],
                       "free_for_manual_assignment": True}
                for name in CHANNELS}
    for mac, name in sorted(plan["bluetooth"].items()):
        assigned[name]["manual_bluetooth_addresses"].append(mac)
    for state in assigned.values():
        state["free_for_manual_assignment"] = (
            not state["lan_reserved"] and not state["manual_bluetooth_addresses"])
    return assigned


def route_slots(directory=None):
    """Read-only slot reservation view; no connected-device assertions."""
    directory = Path(directory) if directory is not None else (
        Path.home() / ".config" / "audiohub")
    try:
        fd = _private_dir(directory)
    except FileNotFoundError:
        policy, revision = defaults(), _revision(defaults(), None)
    else:
        try:
            policy, revision = _stable_policy(fd)
        finally:
            os.close(fd)
    return {
        "mode": "source-slots-read-only",
        "route_policy": policy["mode"], "lan_slot": policy["lan_slot"],
        "slots": _slots(policy),
        "free_slots": [name for name in CHANNELS
                       if _slots(policy)[name]["free_for_manual_assignment"]],
        "revision": revision,
        "connected_devices_verified": False,
        "audible_playback_verified": False,
        "policy_written": False,
    }


def preview_route(action, value, slot=None, *, directory=None):
    """Plan a route change before it touches the source policy or devices."""
    directory = Path(directory) if directory is not None else (
        Path.home() / ".config" / "audiohub")
    try:
        fd = _private_dir(directory)
    except FileNotFoundError:
        current, revision = defaults(), _revision(defaults(), None)
    else:
        try:
            current, revision = _stable_policy(fd)
        finally:
            os.close(fd)
    proposed = _proposed(current, action, value, slot)
    before = set(current["bluetooth"].items())
    after = set(proposed["bluetooth"].items())
    return {
        "mode": "source-route-preview-only",
        "action": action, "revision": revision,
        "current": current, "proposed": proposed,
        "would_change": proposed != current,
        "lan_slot_change": ({"from": current["lan_slot"],
                             "to": proposed["lan_slot"]}
                            if proposed["lan_slot"] != current["lan_slot"] else None),
        "source_mode_change": ({"from": current["mode"], "to": proposed["mode"]}
                               if proposed["mode"] != current["mode"] else None),
        "bluetooth_bindings_removed": [
            {"address": mac, "slot": name} for mac, name in sorted(before - after)],
        "bluetooth_bindings_added": [
            {"address": mac, "slot": name} for mac, name in sorted(after - before)],
        "current_slots": _slots(current),
        "proposed_slots": _slots(proposed),
        "auto_discovery_would_be_disabled": (
            current["mode"] == "auto" and proposed["mode"] == "manual"),
        "separate_confirmation_recommended": True,
        "connected_devices_verified": False,
        "audible_playback_verified": False,
        "policy_written": False,
    }


def load(directory=None):
    directory = Path(directory) if directory is not None else (
        Path.home() / ".config" / "audiohub")
    try:
        fd = _private_dir(directory)
    except FileNotFoundError:
        return defaults()
    try:
        return _read(fd)
    finally:
        os.close(fd)


def lan_target(directory=None):
    """Validate the private policy each time; never trust a remote target."""
    return "audiohub." + load(directory)["lan_slot"]


def update(mutate, directory=None, *, if_revision=None):
    """Atomic source-policy change; optionally guard a reviewed route preview."""
    if if_revision is not None:
        _check_revision(if_revision)
    directory = Path(directory) if directory is not None else (
        Path.home() / ".config" / "audiohub")
    fd = _private_dir(directory, create=True)
    lock = None
    temp = None
    try:
        lock = os.open(".source-routes.lock",
                       os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                       0o600, dir_fd=fd)
        st = os.fstat(lock)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) & 0o077):
            raise PermissionError("Unsafe source policy lock")
        fcntl.flock(lock, fcntl.LOCK_EX)
        if if_revision is None:
            current = _read(fd)
        else:
            current, actual_revision = _stable_policy(fd)
            if actual_revision != if_revision:
                raise StaleRoutePreview("Local source route preview is stale")
        desired = validate(mutate(current))
        data = (json.dumps(desired, sort_keys=True, separators=(",", ":")) +
                "\n").encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Route plan exceeds storage bound")
        temp = "." + FILENAME + "." + secrets.token_hex(8) + ".tmp"
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
        try:
            offset = 0
            while offset < len(data):
                written = os.write(out, data[offset:])
                if written <= 0:
                    raise OSError("Incomplete source policy write")
                offset += written
            os.fsync(out)
        finally:
            os.close(out)
        os.replace(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd)
        temp = None
        os.fsync(fd)
        return desired
    finally:
        if temp:
            try:
                os.unlink(temp, dir_fd=fd)
            except OSError:
                pass
        if lock is not None:
            os.close(lock)
        os.close(fd)


def set_lan(slot, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "set-lan", slot),
                  directory, if_revision=if_revision)


def swap_lan_with_bluetooth(slot, directory=None, *, if_revision=None):
    """Only an explicitly revision-confirmed local operator may swap sources."""
    if if_revision is None:
        raise ValueError("LAN/Bluetooth swap requires a reviewed preview revision")
    return update(lambda plan: _proposed(plan, "swap-lan", slot),
                  directory, if_revision=_check_revision(if_revision))


def swap_bluetooth_inputs(first, second, directory=None, *, if_revision=None):
    """One confirmed private generation exchanges two occupied BT slots."""
    if if_revision is None:
        raise ValueError("Bluetooth input swap requires preview confirmation")
    return update(lambda plan: _proposed(plan, "swap-bt", first, second),
                  directory, if_revision=_check_revision(if_revision))


def bind_bluetooth(address, slot, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "bind-bt", address, slot),
                  directory, if_revision=if_revision)


def unbind_bluetooth(address, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "unbind-bt", address),
                  directory, if_revision=if_revision)


def set_mode(mode, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "mode", mode),
                  directory, if_revision=if_revision)


SOURCE_STATUS_FRESH_SECONDS = 30
SOURCE_STATUS_FIELDS = frozenset({
    "lan_reserved", "bluetooth_assigned", "bluetooth_node_observed",
    "managed_loopback_running", "virtual_sink_observed", "usb_route_ready",
})


def _valid_source_observations(raw):
    if type(raw) is not dict or set(raw) != set(CHANNELS):
        return False
    for values in raw.values():
        if (type(values) is not dict or set(values) != SOURCE_STATUS_FIELDS
                or any(type(x) is not bool for x in values.values())):
            return False
        if values["lan_reserved"] and values["bluetooth_assigned"]:
            return False
        if ((values["bluetooth_node_observed"]
             or values["managed_loopback_running"])
                and not values["bluetooth_assigned"]):
            return False
    return True


def _next_source_check(item):
    """One actionable local diagnostic hint, not an automatic repair."""
    if item["configured_role"] == "unknown":
        return "refresh_private_supervisor_status"
    if item["usb_route_ready"] is False:
        return "inspect_usb_default_output"
    if item["virtual_sink_observed"] is False:
        return "inspect_eq_virtual_sink"
    if item["configured_role"] == "unassigned":
        return "assign_source_or_leave_unused"
    if item["configured_role"] == "lan_reserved":
        return "verify_opt_in_lan_receiver"
    if item.get("bluez_connected_property") is False:
        return "inspect_bluetooth_device_connection"
    if item["bluetooth_source_node_seen"] is False:
        return "inspect_bluetooth_pipewire_source"
    if item["managed_loopback_process_running"] is False:
        return "inspect_managed_loopback"
    if item["eq_to_usb_direct_link_observed"] is None:
        return "inspect_pipewire_graph"
    if item["eq_to_usb_direct_link_observed"] is False:
        return "inspect_possible_intermediary_links"
    return "verify_actual_speaker_audio"


def interpret_source_status(status, *, now=None):
    """Use only allowlisted fixed-slot booleans; stale evidence is UNKNOWN."""
    now = int(time.time() if now is None else now)
    if type(status) is not dict:
        status = {}
    updated = status.get("updated_at")
    fresh = (type(updated) is int and type(now) is int
             and 0 <= now - updated <= SOURCE_STATUS_FRESH_SECONDS)
    policy_ok = status.get("route_policy_valid")
    raw = status.get("source_slot_observations")
    available = (fresh
                 and status.get("source_slot_observations_version") == 1
                 and type(status.get("source_slot_observations_version")) is int
                 and policy_ok is True and _valid_source_observations(raw))
    # Only accept a fixed, anonymous, same-poll PipeWire topology summary.
    # Old/stale status files have UNKNOWN link evidence; raw graph IDs never
    # enter this local report. A missing direct edge is not proof of silence.
    graph_inspected = status.get("pipewire_graph_inspection_available")
    direct_links = status.get("eq_output_usb_direct_links")
    graph_valid = (
        available and type(graph_inspected) is bool
        and type(direct_links) is list
        and len(direct_links) <= len(CHANNELS)
        and all(type(slot) is str and slot in CHANNELS for slot in direct_links)
        and len(set(direct_links)) == len(direct_links)
        and (graph_inspected or not direct_links)
    )
    graph_available = graph_inspected if graph_valid else None
    observed_direct = set(direct_links) if graph_available is True else set()
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
            "eq_to_usb_direct_link_observed": (
                slot in observed_direct if graph_available is True else None
            ),
            "bluetooth_connected": "unverified",
            "audio_stream_available": "unverified",
            "audible_playback": "unverified",
        }
        inputs[slot]["next_local_check"] = _next_source_check(inputs[slot])
    return {
        "mode": "local-source-observations-read-only",
        "fresh": bool(fresh),
        "observations_available": bool(available),
        "status_age_seconds": now - updated if fresh else None,
        "route_policy_valid": policy_ok if fresh and type(policy_ok) is bool else None,
        "pipewire_graph_inspection_available": graph_available,
        "inputs": inputs,
        "interpretation": (
            "Source nodes, managed loopback processes and EQ-to-USB direct "
            "links are PipeWire observations, not PCM or sound measurements. "
            "No direct link observed may mean intermediary adapter nodes. "
            "Bluetooth audio, an audible speaker and hardware remain unverified."
        ),
        "source_settings_written": False,
        "hardware_verified": False,
        "release_ready": False,
    }


# Fixed translations only: never pass raw PipeWire, BlueZ or policy text
# to the human-readable terminal view.
_SOURCE_ROLE_LABELS = {
    "unknown": "Unknown",
    "lan_reserved": "LAN reserved",
    "bluetooth_assigned": "Bluetooth assigned",
    "unassigned": "Unassigned",
}
_SOURCE_NEXT_LABELS = {
    "refresh_private_supervisor_status": "Refresh private supervisor status",
    "inspect_usb_default_output": "Inspect USB default output",
    "inspect_eq_virtual_sink": "Inspect EQ virtual sink",
    "assign_source_or_leave_unused": "Assign a source or leave this input unused",
    "verify_opt_in_lan_receiver": "Verify the opt-in LAN receiver",
    "inspect_bluetooth_device_connection": "Inspect Bluetooth device connection",
    "inspect_bluetooth_pipewire_source": "Inspect Bluetooth PipeWire source",
    "inspect_managed_loopback": "Inspect managed loopback process",
    "inspect_pipewire_graph": "Inspect PipeWire graph",
    "inspect_possible_intermediary_links": "Check intermediary PipeWire links",
    "verify_actual_speaker_audio": "Test actual speaker audio manually",
}


def format_source_status_text(report):
    """Render safe fixed-field guidance for the authorized local terminal.

    Never print raw device identifiers or free-form upstream values. This
    output neither probes the hardware nor confirms actual audio delivery.
    """
    if (type(report) is not dict or type(report.get("inputs")) is not dict
            or set(report["inputs"]) != set(CHANNELS)
            or type(report.get("observations_available")) is not bool):
        raise ValueError("Invalid private source report")
    status = ("available" if report["observations_available"]
              else "unknown (missing, unsafe or stale)")
    lines = [
        "AudioHub local source diagnostics (read-only)",
        "Runtime evidence: " + status,
    ]
    fields = (
        ("USB", "usb_route_ready"),
        ("BT node", "bluetooth_source_node_seen"),
        ("Loopback", "managed_loopback_process_running"),
        ("EQ-to-USB direct", "eq_to_usb_direct_link_observed"),
        ("BlueZ property", "bluez_connected_property"),
    )
    marks = {True: "yes", False: "no", None: "?"}
    for slot in CHANNELS:
        item = report["inputs"][slot]
        if type(item) is not dict:
            raise ValueError("Invalid private source slot")
        role = item.get("configured_role")
        check = item.get("next_local_check")
        if (type(role) is not str or role not in _SOURCE_ROLE_LABELS
                or type(check) is not str or check not in _SOURCE_NEXT_LABELS):
            raise ValueError("Invalid private source guidance")
        values = []
        for label, key in fields:
            value = item.get(key)
            if type(value) not in (bool, type(None)):
                raise ValueError("Invalid private source field")
            values.append(label + ": " + marks[value])
        lines.append(slot + " (" + _SOURCE_ROLE_LABELS[role] + ")")
        lines.append("  " + " | ".join(values))
        lines.append("  Next: " + _SOURCE_NEXT_LABELS[check])
    lines.append(
        "Note: direct PipeWire links and optional BlueZ properties are not "
        "proof of PCM samples or audible sound."
    )
    lines.append(
        "BlueZ property is queried ONLY with --probe-bluetooth; "
        "? also means unqueried/unavailable."
    )
    return "\n".join(lines)


_ROUTE_ACTION_LABELS = {
    "set-lan": "Select LAN input",
    "swap-lan": "Exchange LAN and Bluetooth inputs",
    "swap-bt": "Exchange two Bluetooth inputs",
    "bind-bt": "Assign a Bluetooth input",
    "unbind-bt": "Unassign a Bluetooth input",
    "mode": "Change source discovery mode",
}


def _private_route_lines(plan, labels):
    """Only fixed slot and source-index labels, never real MAC addresses."""
    lines = ["  Mode: " + plan["mode"]]
    by_slot = {slot: "Unreserved" for slot in CHANNELS}
    by_slot[plan["lan_slot"]] = "LAN reserved"
    for address, slot in plan["bluetooth"].items():
        by_slot[slot] = labels[address]
    for slot in CHANNELS:
        lines.append("  " + slot + ": " + by_slot[slot])
    return lines


def format_route_slots_text(report):
    """Readable current private reservation map; redact Bluetooth addresses."""
    if (type(report) is not dict or report.get("mode") != "source-slots-read-only"
            or type(report.get("slots")) is not dict
            or set(report["slots"]) != set(CHANNELS)
            or type(report.get("free_slots")) is not list
            or report.get("policy_written") is not False
            or report.get("connected_devices_verified") is not False
            or report.get("audible_playback_verified") is not False):
        raise ValueError("Invalid private slot report")
    _check_revision(report.get("revision"))
    assigned = {}
    for slot in CHANNELS:
        entry = report["slots"][slot]
        if (type(entry) is not dict
                or set(entry) != {"lan_reserved", "manual_bluetooth_addresses",
                                 "free_for_manual_assignment"}
                or type(entry["lan_reserved"]) is not bool
                or type(entry["free_for_manual_assignment"]) is not bool
                or type(entry["manual_bluetooth_addresses"]) is not list
                or len(entry["manual_bluetooth_addresses"]) > 1):
            raise ValueError("Invalid private slot reservation")
        for addr in entry["manual_bluetooth_addresses"]:
            mac = canonical_mac(addr)
            if mac != addr or mac in assigned:
                raise ValueError("Invalid private source binding")
            assigned[mac] = slot
    plan = validate({
        "schema": SCHEMA, "mode": report.get("route_policy"),
        "lan_slot": report.get("lan_slot"), "bluetooth": assigned,
    })
    if (_slots(plan) != report["slots"] or
            report["free_slots"] != [
                slot for slot in CHANNELS
                if _slots(plan)[slot]["free_for_manual_assignment"]
            ]):
        raise ValueError("Inconsistent private reservation map")
    labels = {addr: "Bluetooth source " + str(i + 1)
              for i, addr in enumerate(sorted(assigned))}
    return "\n".join([
        "AudioHub current source reservations (read-only)",
        *_private_route_lines(plan, labels),
        "Unreserved slots are not proof of inactive Bluetooth audio.",
        "No connection, PCM or audible speaker has been verified.",
    ])


def format_route_preview_text(report):
    """One-screen privacy-safe plan comparison for a separate local approval."""
    if (type(report) is not dict or report.get("mode") != "source-route-preview-only"
            or report.get("action") not in _ROUTE_ACTION_LABELS
            or type(report.get("would_change")) is not bool
            or report.get("separate_confirmation_recommended") is not True
            or report.get("policy_written") is not False
            or report.get("connected_devices_verified") is not False
            or report.get("audible_playback_verified") is not False):
        raise ValueError("Invalid private route preview")
    revision = _check_revision(report.get("revision"))
    current = validate(report.get("current"))
    proposed = validate(report.get("proposed"))
    if report["would_change"] != (current != proposed):
        raise ValueError("Inconsistent source routing preview")
    labels = {addr: "Bluetooth source " + str(i + 1)
              for i, addr in enumerate(sorted(
                  set(current["bluetooth"]) | set(proposed["bluetooth"])))}
    lines = [
        "AudioHub source routing preview (read-only)",
        "Action: " + _ROUTE_ACTION_LABELS[report["action"]],
        "Current:",
        *_private_route_lines(current, labels),
        "Proposed:",
        *_private_route_lines(proposed, labels),
        "Change requested: " + ("yes" if report["would_change"] else "no"),
    ]
    if current["mode"] == "auto" and proposed["mode"] == "manual":
        lines.append("Warning: automatic Bluetooth discovery would be disabled.")
    if current["bluetooth"] != proposed["bluetooth"]:
        lines.append("Warning: affected running sources may restart on the next poll.")
    lines.extend([
        "Review the PRIVATE route policy revision before any separate confirmation:",
        "Revision: " + revision,
        "No routing policy or devices were changed by this preview.",
        "This view does not prove pairing, connection, PCM or audible sound.",
    ])
    return "\n".join(lines)


def read_source_report(*, path=None, now=None):
    """Read one local owner-private runtime status JSON without writing."""
    from .runtime import STATE, read_json
    return interpret_source_status(read_json(STATE if path is None else path, {}), now=now)




def _bluez_connected_property(output, address):
    """Accept only the uniquely identified BlueZ device Connected=yes/no.

    Ignore all peer names; fail closed on ambiguous devices, duplicate flags,
    malformed output or control bytes. Never echo raw BlueZ output.
    """
    if type(output) is not str or not 0 < len(output) <= 4096:
        return None
    if any(ord(char) < 32 and char not in (chr(10), chr(13), chr(9)) for char in output):
        return None
    header = "Device " + canonical_mac(address)
    matches = 0
    flags = []
    for line in output.splitlines():
        item = line.strip()
        if item.startswith("Device "):
            if item == header or item.startswith(header + " "):
                matches += 1
            else:
                return None
        elif item.startswith("Connected:"):
            value = item[len("Connected:"):].strip()
            if value not in ("yes", "no"):
                return None
            flags.append(value == "yes")
    return flags[0] if matches == 1 and len(flags) == 1 else None


def probe_bluez_connections(*, directory=None, status_path=None, now=None):
    """Opt-in read-only local BlueZ device property for manual BT slots.

    BlueZ Connected=true proves a local BlueZ property ONLY, not A2DP
    streaming, decoded audio, owner authentication or audible playback.
    """
    report = read_source_report(path=status_path, now=now)
    report["bluez_probe"] = "not_attempted"
    for slot in CHANNELS:
        report["inputs"][slot]["bluez_connected_property"] = None
    if not report["observations_available"]:
        report["bluez_probe"] = "runtime_evidence_unavailable"
        return report
    directory = Path(directory) if directory is not None else (
        Path.home() / ".config" / "audiohub")
    try:
        fd = _private_dir(directory, create=False)
    except (OSError, ValueError):
        report["bluez_probe"] = "policy_unavailable"
        return report
    try:
        plan, revision = _stable_policy(fd)
        if plan["mode"] != "manual":
            report["bluez_probe"] = "automatic_assignments_not_probed"
            return report
        slots = {slot for slot in CHANNELS
                 if report["inputs"][slot]["configured_role"] == "bluetooth_assigned"}
        if (set(plan["bluetooth"].values()) != slots
                or report["inputs"][plan["lan_slot"]]["configured_role"] != "lan_reserved"):
            report["bluez_probe"] = "runtime_policy_mismatch"
            return report
        pending = {}
        for address, slot in sorted(plan["bluetooth"].items()):
            result = bounded_command_output(
                ("bluetoothctl", "info", address), timeout=3, max_bytes=4096)
            pending[slot] = (
                _bluez_connected_property(result.stdout, address)
                if result is not None and result.returncode == 0 else None
            )
        new_plan, new_revision = _stable_policy(fd)
        if new_revision != revision or new_plan != plan:
            report["bluez_probe"] = "policy_changed_during_probe"
            return report
        for slot, value in pending.items():
            report["inputs"][slot]["bluez_connected_property"] = value
            report["inputs"][slot]["next_local_check"] = _next_source_check(
                report["inputs"][slot]
            )
        report["bluez_probe"] = "manual_assignments_queried"
    except (OSError, ValueError, TypeError, UnicodeError):
        report["bluez_probe"] = "policy_unavailable"
    finally:
        os.close(fd)
    return report


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Local-only AudioHub lab routing; not owner onboarding or Bluetooth trust")
    parser.add_argument("--preview", action="store_true",
                        help="Preview a routing change without writing policy or devices")
    parser.add_argument("--format", choices=("json", "text"), default="json",
                        help="JSON (default); text for read-only status, slots and route previews")
    parser.add_argument("--probe-bluetooth", action="store_true",
                        help="Status only: read manual BlueZ connection property, never connect or pair")
    parser.add_argument("--confirm-local-route-change", action="store_true",
                        help="Explicitly approve a revision-guarded local routing policy change")
    parser.add_argument("--if-preview-revision", metavar="REV",
                        help="Require exact source policy revision from a prior --preview")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show")
    sub.add_parser("slots", help="Read-only reserved and free mixer slot overview")
    sub.add_parser("status", help="Read-only anonymized observed runtime source states")
    lan = sub.add_parser("set-lan")
    lan.add_argument("slot", choices=CHANNELS)
    swap = sub.add_parser(
        "swap-lan", help="Swap LAN with one manual Bluetooth slot; preview and confirmation required")
    swap.add_argument("slot", choices=CHANNELS)
    bt_swap = sub.add_parser(
        "swap-bt", help="Exchange two occupied manual Bluetooth slots; confirmation required")
    bt_swap.add_argument("first_slot", choices=CHANNELS)
    bt_swap.add_argument("second_slot", choices=CHANNELS)
    bt = sub.add_parser("bind-bt")
    bt.add_argument("address")
    bt.add_argument("slot", choices=CHANNELS)
    unbind = sub.add_parser("unbind-bt")
    unbind.add_argument("address")
    mode = sub.add_parser("mode")
    mode.add_argument("value", choices=MODES)
    args = parser.parse_args(argv)

    try:
        if args.action in ("show", "slots", "status"):
            if (args.preview or args.confirm_local_route_change
                    or args.if_preview_revision is not None
                    or (args.probe_bluetooth and args.action != "status")
                    or (args.format != "json" and args.action not in ("status", "slots"))):
                raise ValueError("Status-only actions do not accept route changes")
            if args.action == "status":
                value = (probe_bluez_connections() if args.probe_bluetooth
                         else read_source_report())
            else:
                value = load() if args.action == "show" else route_slots()
        else:
            if args.probe_bluetooth or (args.format != "json" and not args.preview):
                raise ValueError("Text route formatting requires a read-only preview")
            target = (args.slot if args.action in ("set-lan", "swap-lan") else
                      args.first_slot if args.action == "swap-bt" else
                      args.value if args.action == "mode" else args.address)
            slot = (args.slot if args.action == "bind-bt" else
                    args.second_slot if args.action == "swap-bt" else None)
            if args.preview:
                if args.confirm_local_route_change or args.if_preview_revision is not None:
                    raise ValueError("Preview must be read-only")
                value = preview_route(args.action, target, slot)
            else:
                if bool(args.confirm_local_route_change) != (
                        args.if_preview_revision is not None):
                    raise ValueError("Guarded route change needs both approval and revision")
                revision = args.if_preview_revision
                if revision is not None:
                    _check_revision(revision)
                if args.action in ("swap-lan", "swap-bt") and revision is None:
                    raise ValueError("Input swap requires prior preview confirmation")
                if args.action == "set-lan":
                    value = set_lan(args.slot, if_revision=revision)
                elif args.action == "swap-lan":
                    value = swap_lan_with_bluetooth(args.slot, if_revision=revision)
                elif args.action == "swap-bt":
                    value = swap_bluetooth_inputs(
                        args.first_slot, args.second_slot, if_revision=revision)
                elif args.action == "bind-bt":
                    value = bind_bluetooth(args.address, args.slot,
                                           if_revision=revision)
                elif args.action == "unbind-bt":
                    value = unbind_bluetooth(args.address, if_revision=revision)
                else:
                    value = set_mode(args.value, if_revision=revision)
    except StaleRoutePreview:
        # A guarded write under the route-policy lock was refused. Only a
        # NEW read-only preview may be shown; never retry or apply it.
        try:
            fresh = preview_route(args.action, target, slot)
        except (OSError, ValueError, UnicodeError, TypeError):
            parser.exit(4, "AudioHub route not changed: stale preview; fresh view unavailable.\\n")
        print(json.dumps({
            "status": "route-preview-stale", "policy_written": False,
            "fresh_preview": fresh, "connected_devices_verified": False,
        }, sort_keys=True))
        parser.exit(4, "AudioHub route not changed: inspect fresh preview and confirm again.\\n")
    except (OSError, ValueError, UnicodeError, TypeError):
        # Do not echo private device addresses, policy JSON or filesystem paths.
        parser.exit(2, "AudioHub route not changed or unavailable.\\n")
    if args.format == "text":
        if args.action == "status":
            print(format_source_status_text(value))
        elif args.action == "slots":
            print(format_route_slots_text(value))
        else:
            print(format_route_preview_text(value))
    else:
        print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
