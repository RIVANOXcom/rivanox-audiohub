# SPDX-License-Identifier: AGPL-3.0-only
"""Offline, operator-confirmed, private EQ and inactive volume-profile transfer.

Explicitly exclude owner identity, routes, MAC addresses, pairing, TLS, keys,
Wi-Fi, active volume and mute. Nothing starts audio, stages EQ, opens a socket
or grants release approval. Source storage is never edited.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys

from . import mixer_control, music_transfer
from .mixer import CHANNELS, EQ_BANDS
from .runtime import SETTINGS, _private_parent_fd

SCHEMA = "audiohub-portable-presets/1"
FILENAME = "audiohub-presets.json"
MAX_BYTES = 8192
CHUNK = 4096


def _guard(*, require_terminal=True):
    if os.geteuid() == 0:
        raise PermissionError("Only the unprivileged owner may transfer presets")
    if require_terminal and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise PermissionError("Trusted local terminal is required")


def _confirm(word, callback=None):
    if callback is not None:
        return callback() is True
    try:
        print("Type exactly " + word + " then Enter; anything else cancels.")
        return sys.stdin.readline(16) == word + "\n"
    except (OSError, UnicodeError, ValueError, EOFError):
        return False


def _strict_pairs(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate preset JSON member")
        values[key] = value
    return values


def _no_float(_value):
    raise ValueError("Preset values must be bounded integers")


def _validate(value):
    if type(value) is not dict or set(value) != {"schema", "eq", "profiles"}:
        raise ValueError("Unrecognized preset snapshot schema")
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported preset schema version")
    eq, profiles = value["eq"], value["profiles"]
    if type(eq) is not dict or set(eq) != set(CHANNELS):
        raise ValueError("Preset EQ must have exactly three inputs")
    cleaned_eq = {}
    for slot in CHANNELS:
        curve = eq[slot]
        if type(curve) is not dict or set(curve) != set(EQ_BANDS):
            raise ValueError("Invalid three-band EQ preset")
        if any(type(curve[band]) is not int or not -12 <= curve[band] <= 12
               for band in EQ_BANDS):
            raise ValueError("EQ presets require integer -12..12 dB")
        cleaned_eq[slot] = {band: curve[band] for band in EQ_BANDS}
    if type(profiles) is not dict or len(profiles) > mixer_control.MAX_CUSTOM_PROFILES:
        raise ValueError("Volume preset catalog limit exceeded")
    cleaned_profiles = {}
    for name, values in profiles.items():
        mixer_control._check_profile_name(name)
        cleaned_profiles[name] = mixer_control._profile_levels(values)
    return {"schema": SCHEMA, "eq": cleaned_eq,
            "profiles": dict(sorted(cleaned_profiles.items()))}


def _encode(value):
    raw = (json.dumps(_validate(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Private preset archive is too large")
    return raw


def _read_external(dirfd):
    fd = os.open(FILENAME, os.O_RDONLY | os.O_NONBLOCK |
                 os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_nlink != 1 or before.st_mode & 0o077
                or not 0 < before.st_size <= MAX_BYTES):
            raise PermissionError("Unsafe private preset archive")
        raw = os.read(fd, MAX_BYTES + 1)
        after = os.fstat(fd)
        entry = os.stat(FILENAME, dir_fd=dirfd, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size,
                              s.st_mtime_ns, s.st_ctime_ns)
        if (len(raw) != before.st_size or identity(before) != identity(after)
                or identity(after) != identity(entry)):
            raise OSError("Preset archive changed during read")
        value = json.loads(raw.decode("ascii"), object_pairs_hook=_strict_pairs,
                           parse_constant=_no_float, parse_float=_no_float)
        return _validate(value), hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def _publish_exclusive(dirfd, filename, raw):
    """Fsync a private temporary file and hardlink it under an absent name."""
    tmp = ".audiohub-presets-" + secrets.token_hex(12) + ".part"
    out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                  os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
    try:
        os.fchmod(out, 0o600)
        done = 0
        while done < len(raw):
            written = os.write(out, raw[done:])
            if written <= 0:
                raise OSError("Incomplete private preset write")
            done += written
        os.fsync(out)
    finally:
        os.close(out)
    try:
        os.link(tmp, filename, src_dir_fd=dirfd, dst_dir_fd=dirfd,
                follow_symlinks=False)
        os.fsync(dirfd)
    finally:
        os.unlink(tmp, dir_fd=dirfd)


def _source_snapshot(settings_path, profile_path):
    settings_path, profile_path = Path(settings_path), Path(profile_path)
    mixer_control._profile_snapshot_paths(profile_path, settings_path)
    dirfd = _private_parent_fd(settings_path, create=False)
    try:
        current, revision = mixer_control._state_with_revision(settings_path, dirfd)
        catalog, profile_revision = mixer_control._profile_catalog_with_revision(
            profile_path, dirfd)
        after, revision_after = mixer_control._state_with_revision(settings_path, dirfd)
        _, profile_after = mixer_control._profile_catalog_with_revision(profile_path, dirfd)
        if revision != revision_after or profile_revision != profile_after or current != after:
            raise OSError("Private preset source changed during preview")
        data = {"schema": SCHEMA,
                "eq": {slot: {band: current[slot][band] for band in EQ_BANDS}
                       for slot in CHANNELS},
                "profiles": catalog["profiles"]}
        return _validate(data), (revision, profile_revision)
    finally:
        os.close(dirfd)


def export_presets(external, *, settings_path=SETTINGS,
                   profile_path=mixer_control.PROFILE_PATH,
                   confirm=None, out=print, require_terminal=True):
    """Export only validated EQ bands and INACTIVE user volume presets."""
    _guard(require_terminal=require_terminal)
    data, version = _source_snapshot(settings_path, profile_path)
    if (not data["profiles"] and all(
            all(value == 0 for value in data["eq"][slot].values())
            for slot in CHANNELS)):
        raise ValueError("No customized EQ or volume profiles to export")
    dirfd = music_transfer._private_dir(external)
    try:
        try:
            os.stat(FILENAME, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Preset archive already exists; no overwrite")
        raw = _encode(data)
        out("Private preset export preview: 3 EQ curves, " +
            str(len(data["profiles"])) + " inactive volume profiles; no identities.")
        if not _confirm("SAVE", confirm):
            out("Preset export cancelled with no new file.")
            return False
        data_after, version_after = _source_snapshot(settings_path, profile_path)
        if data != data_after or version != version_after:
            raise OSError("Preset source changed before export")
        _publish_exclusive(dirfd, FILENAME, raw)
        out("Preset archive saved, SHA256 " + hashlib.sha256(raw).hexdigest() +
            ". Existing settings and audio untouched.")
        return True
    finally:
        os.close(dirfd)


def _load(external):
    dirfd = music_transfer._private_dir(external)
    try:
        return _read_external(dirfd)
    finally:
        os.close(dirfd)


def inspect(external, *, settings_path=SETTINGS,
            profile_path=mixer_control.PROFILE_PATH, out=print,
            require_terminal=True):
    """Read-only archive check and non-sensitive current preset comparison."""
    _guard(require_terminal=require_terminal)
    data, digest = _load(external)
    current, _ = mixer_control._preview_snapshot(path=settings_path)
    existing = mixer_control.list_volume_profiles(path=profile_path)["profiles"]
    changed = [slot + "." + band for slot in CHANNELS for band in EQ_BANDS
               if current[slot][band] != data["eq"][slot][band]]
    collisions = sorted(set(existing) & set(data["profiles"]))
    out("Private preset archive valid: 3 EQ curves; " +
        str(len(data["profiles"])) + " saved volume profiles; " +
        str(len(changed)) + " EQ band differences; " +
        str(len(collisions)) + " existing profile name collisions.")
    out("Archive SHA256 " + digest +
        ". Inspection read-only; no live EQ, volume or audio changes.")
    return data


def restore_profiles(external, *, profile_path=mixer_control.PROFILE_PATH,
                     confirm=None, out=print, require_terminal=True):
    """Publish inactive profile catalog exclusively, under existing writer lock."""
    _guard(require_terminal=require_terminal)
    data, digest = _load(external)
    profiles = data["profiles"]
    if not profiles:
        raise ValueError("Archive contains no custom volume profiles")
    profile_path = Path(profile_path)
    if profile_path.name != "volume-profiles.json":
        raise ValueError("Invalid local volume profile target")
    out("Restore preview: " + str(len(profiles)) +
        " inactive volume profiles; active volumes/mutes/EQ unchanged.")
    if not _confirm("RESTORE", confirm):
        out("Profile restoration cancelled without writing.")
        return False
    if _load(external)[1] != digest:
        raise OSError("Private preset archive changed after confirmation")
    dirfd = _private_parent_fd(profile_path, create=True)
    lockfd = None
    try:
        lockfd = os.open(mixer_control.LOCK_NAME, os.O_RDWR | os.O_CREAT
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
        lock = os.fstat(lockfd)
        if (not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.geteuid()
                or lock.st_nlink != 1 or lock.st_mode & 0o077):
            raise PermissionError("Unsafe private mixer lock")
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        try:
            os.stat(profile_path.name, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Local volume profile catalog already exists")
        raw = (json.dumps({"version": 1, "profiles": profiles},
                          sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        _publish_exclusive(dirfd, profile_path.name, raw)
        out("Restored " + str(len(profiles)) +
            " inactive private profiles. No mixer controls applied.")
        return True
    finally:
        if lockfd is not None:
            os.close(lockfd)
        os.close(dirfd)


def restore_eq(external, *, settings_path=SETTINGS, confirm=None, out=print,
               require_terminal=True):
    """Save only EQ bands to initially neutral settings; never restart PipeWire."""
    _guard(require_terminal=require_terminal)
    data, digest = _load(external)
    current, revision = mixer_control._preview_snapshot(path=settings_path)
    patch = {slot: data["eq"][slot] for slot in CHANNELS}
    different = sum(current[slot][band] != data["eq"][slot][band]
                    for slot in CHANNELS for band in EQ_BANDS)
    if not different:
        out("All nine saved EQ bands already match. Nothing written.")
        return True
    if any(current[slot][band] != 0 for slot in CHANNELS for band in EQ_BANDS):
        raise ValueError("Existing non-neutral EQ must not be overwritten")
    out("EQ preview: " + str(different) +
        " of nine saved EQ bands differ from neutral; volume/mutes kept.")
    out("This saves an EQ request only. PipeWire EQ is NOT staged or restarted.")
    if not _confirm("APPLY-EQ", confirm):
        out("EQ restoration cancelled without writing.")
        return False
    if _load(external)[1] != digest:
        raise OSError("Private preset archive changed after confirmation")
    mixer_control.change(patch, path=settings_path, confirmed=True,
                         if_revision=revision)
    out("Saved EQ curves; volume/mute untouched; live sound not updated.")
    return True


def verify(external, *, settings_path=SETTINGS,
           profile_path=mixer_control.PROFILE_PATH, out=print,
           require_terminal=True):
    """Verify saved requests/catalog, not the live PipeWire graph or audible sound."""
    _guard(require_terminal=require_terminal)
    data, digest = _load(external)
    state, _ = mixer_control._preview_snapshot(path=settings_path)
    profiles = mixer_control.list_volume_profiles(path=profile_path)["profiles"]
    if (profiles != data["profiles"] or
            any(state[slot][band] != data["eq"][slot][band]
                for slot in CHANNELS for band in EQ_BANDS)):
        raise ValueError("Saved EQ or profiles do not match the archive")
    out("Private EQ and inactive profile verification passed, archive SHA256 " +
        digest + ". No live audio or owner verification implied.")
    return True


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print("Offline Pi4 non-secret audio preset transfer, no owner migration.")
        print("Usage: audiohub-presets-transfer export|inspect|restore-profiles|restore-eq|verify ABSOLUTE_PRIVATE_FOLDER")
        print("Export SAVE; inactive profiles RESTORE; saved EQ APPLY-EQ to neutral EQ only.")
        print("Never imports keys, Bluetooth trust, Wi-Fi, IDs, live volume/mutes or OS.")
        return 0
    if len(args) != 2 or args[0] not in (
            "export", "inspect", "restore-profiles", "restore-eq", "verify"):
        print("Specify export, inspect, restore-profiles, restore-eq or verify and one folder.")
        return 2
    try:
        operation = {"export": export_presets, "inspect": inspect,
                     "restore-profiles": restore_profiles, "restore-eq": restore_eq,
                     "verify": verify}[args[0]]
        result = operation(args[1])
        return 0 if result is not False else 1
    except (OSError, ValueError, TypeError, UnicodeError,
            mixer_control.MixerControlUnavailable):
        print("Private preset operation safely refused or incomplete; no owner data transferred.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
