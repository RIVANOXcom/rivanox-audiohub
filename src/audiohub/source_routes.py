# SPDX-License-Identifier: AGPL-3.0-only
"""Private offline source-to-slot policy, never remote ownership authority.

A route plan describes *which eligible* BlueZ source or manually started
Scream transport may use each stable mixer slot. It never pairs a Bluetooth
device, trusts a MAC as an identity, opens a UDP socket or grants ownership.
The existing untrusted Scream receiver remains opt-in in an isolated lab.
"""
from __future__ import annotations

import fcntl
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


def update(mutate, directory=None):
    """Atomic source-policy change from a controlled local console only."""
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
        current = _read(fd)
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


def set_lan(slot, directory=None):
    if type(slot) is not str or slot not in CHANNELS:
        raise ValueError("Unknown input slot")
    def change(plan):
        plan["lan_slot"] = slot
        return plan
    return update(change, directory)


def bind_bluetooth(address, slot, directory=None):
    mac = canonical_mac(address)
    if type(slot) is not str or slot not in CHANNELS:
        raise ValueError("Unknown input slot")
    def change(plan):
        if plan["mode"] == "auto":
            plan["mode"] = "manual"
            plan["bluetooth"] = {}
        plan["bluetooth"][mac] = slot
        return plan
    return update(change, directory)


def unbind_bluetooth(address, directory=None):
    mac = canonical_mac(address)
    def change(plan):
        if plan["mode"] != "manual" or mac not in plan["bluetooth"]:
            raise ValueError("Bluetooth address is not manually bound")
        del plan["bluetooth"][mac]
        return plan
    return update(change, directory)


def set_mode(mode, directory=None):
    if mode not in MODES:
        raise ValueError("Invalid source policy mode")
    def change(plan):
        plan["mode"] = mode
        # Explicit mode change drops stale source-specific authorizations.
        plan["bluetooth"] = {}
        return plan
    return update(change, directory)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Local-only AudioHub lab routing; not owner onboarding or Bluetooth trust")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show")
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
        if args.action == "show":
            value = load()
        elif args.action == "set-lan":
            value = set_lan(args.slot)
        elif args.action == "bind-bt":
            value = bind_bluetooth(args.address, args.slot)
        elif args.action == "unbind-bt":
            value = unbind_bluetooth(args.address)
        else:
            value = set_mode(args.value)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, "AudioHub route not changed: " + str(exc) + "\n")
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
