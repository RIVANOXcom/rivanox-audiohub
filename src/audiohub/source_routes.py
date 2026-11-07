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

from .mixer import CHANNELS

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


def bind_bluetooth(address, slot, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "bind-bt", address, slot),
                  directory, if_revision=if_revision)


def unbind_bluetooth(address, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "unbind-bt", address),
                  directory, if_revision=if_revision)


def set_mode(mode, directory=None, *, if_revision=None):
    return update(lambda plan: _proposed(plan, "mode", mode),
                  directory, if_revision=if_revision)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Local-only AudioHub lab routing; not owner onboarding or Bluetooth trust")
    parser.add_argument("--preview", action="store_true",
                        help="Preview a routing change without writing policy or devices")
    parser.add_argument("--confirm-local-route-change", action="store_true",
                        help="Explicitly approve a revision-guarded local routing policy change")
    parser.add_argument("--if-preview-revision", metavar="REV",
                        help="Require exact source policy revision from a prior --preview")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show")
    sub.add_parser("slots", help="Read-only reserved and free mixer slot overview")
    lan = sub.add_parser("set-lan")
    lan.add_argument("slot", choices=CHANNELS)
    bt = sub.add_parser("bind-bt")
    bt.add_argument("address")
    bt.add_argument("slot", choices=CHANNELS)
    unbind = sub.add_parser("unbind-bt")
    unbind.add_argument("address")
    mode = sub.add_parser("mode")
    mode.add_argument("value", choices=MODES)
    args = parser.parse_args(argv)

    try:
        if args.action in ("show", "slots"):
            if (args.preview or args.confirm_local_route_change
                    or args.if_preview_revision is not None):
                raise ValueError("Status-only actions do not accept route changes")
            value = load() if args.action == "show" else route_slots()
        else:
            target = (args.slot if args.action == "set-lan" else
                      args.value if args.action == "mode" else args.address)
            slot = args.slot if args.action == "bind-bt" else None
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
                if args.action == "set-lan":
                    value = set_lan(args.slot, if_revision=revision)
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
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
