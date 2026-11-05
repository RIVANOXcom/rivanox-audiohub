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
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    st = os.fstat(fd)
    if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o077:
        os.close(fd)
        raise PermissionError("Route directory must be user-owned and private")
    return fd


def _read(fd):
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
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
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Source route file too large")
        return validate(json.loads(raw.decode("utf-8")))
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
