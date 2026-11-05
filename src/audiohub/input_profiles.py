# SPDX-License-Identifier: AGPL-3.0-only
"""Offline-only AudioHub input display names, independent from source transport.

Stable internal PipeWire slot IDs are deliberately unchanged for compatibility.
This module does not bind devices, trust Bluetooth peers, open network ports,
expose profile labels over unauthenticated HTTP, or control actual audio.
Only a local audiohub-user console may write Pi-local profile labels.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import unicodedata

SLOTS = ("music", "laptop", "tablet")
DEFAULT_NAMES = {"music": "Input 1", "laptop": "Input 2", "tablet": "Input 3"}
# A protocol capability, not a fixed device identity. The LAN route must stay
# manually disabled until authenticated ownership and transport are delivered.
TRANSPORT_HINT = {"music": "bluetooth", "laptop": "manual_lan", "tablet": "bluetooth"}
SCHEMA = "audiohub-input-labels/1"
FILENAME = "input-labels.json"
MAX_BYTES = 2048
MAX_NAME_CHARS = 32


def validate_name(value):
    if type(value) is not str:
        raise ValueError("Input name must be a string")
    name = value.strip()
    if not name or len(name) > MAX_NAME_CHARS:
        raise ValueError("Input name must contain 1..32 characters")
    if any(unicodedata.category(char).startswith("C") or char in "<>" for char in name):
        raise ValueError("Control, direction or markup characters are not permitted")
    return name


def validate_labels(labels):
    if type(labels) is not dict or set(labels) != set(SLOTS):
        raise ValueError("Exactly three stable input slots are required")
    normalized = {slot: validate_name(labels[slot]) for slot in SLOTS}
    if len({value.casefold() for value in normalized.values()}) != len(SLOTS):
        raise ValueError("Input names must be distinguishable")
    return normalized


def _safe_dir(path):
    """Open a private directory owned by the effective uid; no symlink dirs."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags)
    st = os.fstat(fd)
    if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o077:
        os.close(fd)
        raise PermissionError("Profile directory must be owned by caller and private")
    return fd


def _read_labels(dirfd):
    try:
        fd = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
    except FileNotFoundError:
        return DEFAULT_NAMES.copy()
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_uid != os.geteuid()
                or stat.S_IMODE(meta.st_mode) & 0o077
                or meta.st_size > MAX_BYTES):
            raise PermissionError("Invalid input-labels file ownership or size")
        data = os.read(fd, MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Input labels exceed size limit")
        parsed = json.loads(data.decode("utf-8"))
        if type(parsed) is not dict or set(parsed) != {"schema", "labels"}:
            raise ValueError("Invalid input-labels data")
        if parsed["schema"] != SCHEMA:
            raise ValueError("Unsupported input-labels version")
        return validate_labels(parsed["labels"])
    finally:
        os.close(fd)


def load_labels(directory=None):
    """Read only; missing file uses generic labels, malformed files fail closed."""
    directory = Path(directory) if directory is not None else Path.home() / ".config" / "audiohub"
    try:
        dirfd = _safe_dir(directory)
    except FileNotFoundError:
        return DEFAULT_NAMES.copy()
    try:
        return _read_labels(dirfd)
    finally:
        os.close(dirfd)


def set_label(slot, label, directory=None):
    """Write one name atomically, offline, with per-dir lock and strict perms.

    A failed operation never resets or partially rewrites a valid profile.
    The caller must already have privileged local console access as audiohub.
    """
    if slot not in SLOTS:
        raise ValueError("Unknown stable input slot")
    label = validate_name(label)
    directory = Path(directory) if directory is not None else Path.home() / ".config" / "audiohub"
    # The image normally creates this 0700 directory for the audiohub user.
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    dirfd = _safe_dir(directory)
    lockfd = None
    temp_name = None
    try:
        lockfd = os.open(".input-labels.lock",
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=dirfd)
        st = os.fstat(lockfd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o077):
            raise PermissionError("Unsafe input profile lock")
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        values = _read_labels(dirfd)
        values[slot] = label
        values = validate_labels(values)
        raw = (json.dumps({"schema": SCHEMA, "labels": values},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise ValueError("Input labels exceed byte limit")
        temp_name = "." + FILENAME + "." + secrets.token_hex(8) + ".tmp"
        fd = os.open(temp_name,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=dirfd)
        try:
            n = 0
            while n < len(raw):
                written = os.write(fd, raw[n:])
                if written <= 0:
                    raise OSError("Unable to persist input labels")
                n += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp_name, FILENAME, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        temp_name = None
        try:
            os.fsync(dirfd)
        except OSError:
            # FAT and some virtual filesystems do not permit fsync(dir).
            pass
        return values
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=dirfd)
            except OSError:
                pass
        if lockfd is not None:
            os.close(lockfd)
        os.close(dirfd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LOCAL console-only input display names; no device pairing or audio control"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("show")
    change = commands.add_parser("set")
    change.add_argument("slot", choices=SLOTS)
    change.add_argument("name")
    args = parser.parse_args(argv)
    try:
        values = (set_label(args.slot, args.name) if args.action == "set"
                  else load_labels())
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, "AudioHub input profile not modified: " + str(exc) + "\n")
    print(json.dumps({"schema": SCHEMA, "labels": values}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
