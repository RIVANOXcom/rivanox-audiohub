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
        # Exclusive publication: EEXIST never replaces a pre-existing file.
        os.link(tmp, filename, src_dir_fd=dirfd, dst_dir_fd=dirfd,
                follow_symlinks=False)
        os.fsync(dirfd)
    finally:
        # Only our random temporary file is removed; user files are untouched.
        try:
            os.unlink(tmp, dir_fd=dirfd)
        except FileNotFoundError:
            pass


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
                   confirm=None, out=print, require_terminal=True,
                   allow_neutral=False):
    """Export only validated EQ bands and INACTIVE user volume presets."""
    _guard(require_terminal=require_terminal)
    data, version = _source_snapshot(settings_path, profile_path)
    if (not allow_neutral and not data["profiles"] and all(
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


def _profile_merge_delta(incoming, existing):
    """Determine a non-destructive union; do not expose private profile names."""
    if type(incoming) is not dict or type(existing) is not dict:
        raise ValueError("Private profile catalogs must be objects")
    if not incoming:
        raise ValueError("Archive has no custom volume profiles to merge")
    identical = sum(name in existing and existing[name] == levels
                    for name, levels in incoming.items())
    conflicts = sum(name in existing and existing[name] != levels
                    for name, levels in incoming.items())
    added = sum(name not in existing for name in incoming)
    count = len(existing) + added
    return {
        "existing": len(existing), "archived": len(incoming),
        "identical": identical, "conflicts": conflicts, "new": added,
        "resulting": count, "limit": mixer_control.MAX_CUSTOM_PROFILES,
        "can_merge": conflicts == 0 and count <= mixer_control.MAX_CUSTOM_PROFILES,
    }


def _merge_preflight(external, profile_path):
    """Preview private archive and validated target catalog without writes."""
    path = Path(profile_path)
    if path.name != "volume-profiles.json":
        raise ValueError("Invalid local volume profile catalog path")
    data, digest = _load(external)
    existing = mixer_control.list_volume_profiles(path=path)["profiles"]
    return data, digest, _profile_merge_delta(data["profiles"], existing)


def plan_profiles(external, *, profile_path=mixer_control.PROFILE_PATH,
                  out=print, require_terminal=True):
    """Read-only non-sensitive profile merge preview, no lock or file creation."""
    _guard(require_terminal=require_terminal)
    _, digest, plan = _merge_preflight(external, profile_path)
    out("Private profile merge preview: " + str(plan["existing"]) +
        " existing, " + str(plan["archived"]) + " archived, " +
        str(plan["identical"]) + " identical, " +
        str(plan["new"]) + " new, " + str(plan["conflicts"]) +
        " conflicting; resulting " + str(plan["resulting"]) +
        "/" + str(plan["limit"]) + ".")
    out("Result: " + ("safe to merge" if plan["can_merge"]
                      else "MERGE REFUSED: resolve conflicting names or capacity manually") +
        "; archive SHA256 " + digest + ". Read-only; no audio changes.")
    return plan


def merge_profiles(external, *, profile_path=mixer_control.PROFILE_PATH,
                   confirm=None, out=print, require_terminal=True):
    """Add only missing INACTIVE profiles; preserve every existing name/value.

    Does not replace any pre-existing profile value, even when archive and
    target share a name. Under the existing private mixer-writer lock, the
    entire candidate catalog is validated again after explicit confirmation.
    """
    _guard(require_terminal=require_terminal)
    profile_path = Path(profile_path)
    data, digest, plan = _merge_preflight(external, profile_path)
    if not plan["can_merge"]:
        raise ValueError("Merge blocked: conflicting profile or eight-profile limit")
    if not plan["new"]:
        out("All archived volume profiles already match; nothing written.")
        return True
    out("Private profile merge preview: " + str(plan["identical"]) +
        " identical and " + str(plan["new"]) + " missing; existing " +
        str(plan["existing"]) + " unchanged, result " +
        str(plan["resulting"]) + "/" + str(plan["limit"]) + ".")
    out("Only inactive saved profiles will be added; live volumes, EQ and mutes stay unchanged.")
    if not _confirm("MERGE", confirm):
        out("Profile merge cancelled; no new profiles saved.")
        return False
    after, after_digest = _load(external)
    if digest != after_digest or data != after:
        raise OSError("Source profile archive changed after confirmation")
    dirfd = _private_parent_fd(profile_path, create=True)
    lockfd = None
    try:
        lockfd = os.open(mixer_control.LOCK_NAME, os.O_RDWR | os.O_CREAT
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
        meta = os.fstat(lockfd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                or meta.st_nlink != 1 or meta.st_mode & 0o077):
            raise PermissionError("Unsafe private profile writer lock")
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        catalog, revision = mixer_control._profile_catalog_with_revision(
            profile_path, dirfd)
        latest = _profile_merge_delta(data["profiles"], catalog["profiles"])
        if not latest["can_merge"]:
            raise ValueError("Local profiles changed or conflict; merge cancelled")
        if not latest["new"]:
            out("All saved profiles now match; nothing written.")
            return True
        merged = dict(catalog["profiles"])
        for name, levels in data["profiles"].items():
            if name not in merged:
                merged[name] = levels
        value = {"version": 1, "profiles": dict(sorted(merged.items()))}
        # A competing editor, even one not honoring our writer lock, must
        # not silently invalidate the catalog version seen in this review.
        if mixer_control._profile_catalog_with_revision(
                profile_path, dirfd)[1] != revision:
            raise OSError("Local private profiles changed during merge")
        if mixer_control._state_identity(profile_path, dirfd) is None:
            raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) +
                   "\n").encode("ascii")
            _publish_exclusive(dirfd, profile_path.name, raw)
        else:
            from .runtime import atomic_json
            atomic_json(profile_path, value)
        out("Merged " + str(latest["new"]) +
            " inactive profiles; all earlier names/values preserved." +
            " No live volume, mute or EQ changes.")
        return True
    finally:
        if lockfd is not None:
            os.close(lockfd)
        os.close(dirfd)


def verify_merged(external, *, settings_path=SETTINGS,
                  profile_path=mixer_control.PROFILE_PATH, out=print,
                  require_terminal=True):
    """Read-only: every archived profile and EQ band matches; extras allowed."""
    _guard(require_terminal=require_terminal)
    data, digest = _load(external)
    state, _ = mixer_control._preview_snapshot(path=settings_path)
    saved = mixer_control.list_volume_profiles(path=profile_path)["profiles"]
    if (any(saved.get(name) != values
            for name, values in data["profiles"].items())
            or any(state[slot][band] != data["eq"][slot][band]
                   for slot in CHANNELS for band in EQ_BANDS)):
        raise ValueError("An archived profile or EQ band is missing or differs")
    out("All " + str(len(data["profiles"])) +
        " archived inactive profiles and nine EQ bands match; " +
        str(len(saved) - len(data["profiles"])) +
        " additional local profiles preserved. SHA256 " + digest +
        ". Read-only; no physical audio verified.")
    return True


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


def _music_destination_plan(external, music_dir):
    """Read-only SHA checks for bounded source WAVs against the new music folder.

    The archive is the source. Existing destinations must match by content and
    safety constraints, never just filename. Missing WAVs may be copied later
    using the existing exclusive --resume command; none are written here.
    """
    source_fd = music_transfer._private_dir(external)
    try:
        target_fd = music_transfer._private_dir(music_dir)
        try:
            first, second = os.fstat(source_fd), os.fstat(target_fd)
            if (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino):
                raise ValueError("Private archive and new music directory must differ")
            # A legitimately empty old Pi4 music folder must not block
            # migration of saved EQ and inactive profiles. Never mistake
            # unexpected destination WAVs for a clean empty-data migration.
            files, size = music_transfer._source_list(
                external, source_fd, allow_empty=True)
            if not files:
                target_files, _ = music_transfer._source_list(
                    music_dir, target_fd, allow_empty=True)
                if target_files:
                    raise ValueError("Empty WAV archive conflicts with nonempty local music")
            matches = 0
            for item in files:
                match = music_transfer._matching_destination(
                    source_fd, target_fd, item)
                if match is not None:
                    matches += 1
            again, size_after = music_transfer._source_list(
                external, source_fd, allow_empty=True)
            if files != again or size != size_after:
                raise OSError("Private WAV archive changed during preview")
            if not files:
                current_target, _ = music_transfer._source_list(
                    music_dir, target_fd, allow_empty=True)
                if current_target:
                    raise OSError("New music folder changed during empty archive preview")
            return {
                "wav_total": len(files), "wav_bytes": size,
                "wav_matched": matches, "wav_missing": len(files) - matches,
                "wav_copy_needed": matches < len(files),
            }
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)


def _verify_wavs_or_proven_empty(source, target):
    """Read-only verification scoped ONLY to full preset+WAV SD migration.

    Regular WAV transfer verify stays strict and requires real WAV data.
    Empty is accepted only when *both* distinct private directories are
    safely validated and visibly contain zero supported/unsafe WAV entries.
    A zero-file result never asserts a file was copied or audio verified.
    """
    source_fd = music_transfer._private_dir(source)
    try:
        target_fd = music_transfer._private_dir(target)
        try:
            a, b = os.fstat(source_fd), os.fstat(target_fd)
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                raise ValueError("Old and new private WAV directories must differ")
            source_files, _ = music_transfer._source_list(
                source, source_fd, allow_empty=True)
            if source_files:
                return music_transfer.transfer(
                    "backup", target, music_dir=source, verify=True,
                    out=lambda _message: None, require_terminal=False)
            target_files, _ = music_transfer._source_list(
                target, target_fd, allow_empty=True)
            if target_files:
                raise ValueError("Expected empty WAV target contains music")
            source_again, _ = music_transfer._source_list(
                source, source_fd, allow_empty=True)
            target_again, _ = music_transfer._source_list(
                target, target_fd, allow_empty=True)
            if source_again or target_again:
                raise OSError("Empty WAV inventory changed during SD check")
            return True
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)


def plan_new_sd(external, *, settings_path=SETTINGS,
                profile_path=mixer_control.PROFILE_PATH,
                music_dir=music_transfer.DEFAULT_MUSIC_DIR,
                out=print, require_terminal=True):
    """Explain the safe next manual restore actions; never copy or modify.

    A destination collision whose bytes differ is a hard error, not a
    permission to overwrite. This is a snapshot for planning, NOT a
    durability guarantee or substitute for post-copy hash verification.
    """
    _guard(require_terminal=require_terminal)
    music = _music_destination_plan(external, music_dir)
    data, _ = _load(external)
    saved = mixer_control.list_volume_profiles(path=profile_path)["profiles"]
    if data["profiles"]:
        profiles = _profile_merge_delta(data["profiles"], saved)
    else:
        profiles = {
            "existing": len(saved), "archived": 0, "identical": 0,
            "conflicts": 0, "new": 0, "resulting": len(saved),
            "limit": mixer_control.MAX_CUSTOM_PROFILES,
            "can_merge": True,
        }
    state, _ = mixer_control._preview_snapshot(path=settings_path)
    eq_changes = sum(
        state[slot][band] != data["eq"][slot][band]
        for slot in CHANNELS for band in EQ_BANDS
    )
    eq_overwrite = eq_changes > 0 and any(
        state[slot][band] != 0 for slot in CHANNELS for band in EQ_BANDS
    )
    plan = {
        **music,
        "profile_existing": profiles["existing"],
        "profile_archived": profiles["archived"],
        "profile_identical": profiles["identical"],
        "profile_missing": profiles["new"],
        "profile_conflicts": profiles["conflicts"],
        "profile_limit_exceeded": profiles["resulting"] > profiles["limit"],
        "eq_bands_different": eq_changes,
        "eq_non_neutral_conflict": eq_overwrite,
        "ready_for_final_readonly_check": (
            not music["wav_copy_needed"]
            and profiles["conflicts"] == 0
            and profiles["new"] == 0
            and not profiles["resulting"] > profiles["limit"]
            and eq_changes == 0
        ),
        "no_files_changed": True, "owner_identity_transferred": False,
        "hardware_playback_verified": False,
    }
    if music["wav_total"] == 0:
        out("Both protected music folders contain zero supported WAVs. "
            "Only saved EQ/inactive profile data can be migrated; "
            "no WAV transfer or musical sound verified.")
    out("New SD read-only plan: " + str(music["wav_total"]) +
        " archived WAVs, " + str(music["wav_matched"]) + " identical, " +
        str(music["wav_missing"]) + " missing; " +
        str(profiles["new"]) + " inactive profiles missing, " +
        str(profiles["identical"]) + " identical, " +
        str(profiles["conflicts"]) + " conflicting; " +
        str(eq_changes) + " EQ band differences.")
    if music["wav_copy_needed"]:
        out("NEXT (separate local COPY confirmation): "
            "audiohub-music-transfer restore PRIVATE_FOLDER --resume")
    if profiles["conflicts"] or profiles["resulting"] > profiles["limit"]:
        out("BLOCKED: differing profile names or limit; do not overwrite local profiles.")
    elif profiles["new"]:
        out("NEXT (separate MERGE confirmation): "
            "audiohub-presets-transfer merge-profiles PRIVATE_FOLDER")
    if eq_overwrite:
        out("BLOCKED: existing non-neutral EQ conflicts; do not overwrite automatically.")
    elif eq_changes:
        out("NEXT (separate APPLY-EQ confirmation): "
            "audiohub-presets-transfer restore-eq PRIVATE_FOLDER")
    out("FINAL (read-only): audiohub-presets-transfer check-new PRIVATE_FOLDER")
    out("No music, EQ, volumes, mutes, identities or files changed; "
        "no physical sound or SD flash verified.")
    return plan


def check_backup(external, old_music, old_config, *, out=print,
                 require_terminal=True):
    """Read-only source-to-archive proof before manual SD replacement.

    Caller must provide already-mounted private source paths. Old SD is
    never mounted, edited or accessed with elevated privileges here.
    """
    _guard(require_terminal=require_terminal)
    old_config = Path(old_config)
    if (not old_config.is_absolute() or ".." in old_config.parts
            or len(str(old_config)) > 1024):
        raise ValueError("Old SD config must be an absolute private directory")
    data, archive_hash = _load(external)
    original, _ = _source_snapshot(
        old_config / "settings.json", old_config / "volume-profiles.json")
    if data != original:
        raise ValueError("EQ or inactive profiles differ from old SD backup")
    _verify_wavs_or_proven_empty(old_music, external)
    out("Original SD to private backup: all supported WAV bytes and saved "
        "EQ/inactive profiles match, preset SHA256 " + archive_hash + ".")
    out("Read-only check, no flash, no owner/BT trust transfer, no hardware proof.")
    return True


def check_new(external, *, settings_path=SETTINGS,
              profile_path=mixer_control.PROFILE_PATH,
              music_dir=music_transfer.DEFAULT_MUSIC_DIR,
              out=print, require_terminal=True):
    """Read-only archive-to-new-SD verification of BOTH supported data sets."""
    _guard(require_terminal=require_terminal)
    _verify_wavs_or_proven_empty(external, music_dir)
    verify_merged(external, settings_path=settings_path,
                  profile_path=profile_path, out=lambda _message: None,
                  require_terminal=False)
    out("New SD data check passed: all archived supported WAVs have identical "
        "private copies, all archived inactive profiles and saved EQ bands match.")
    out("This proves requested stored data only, NOT live PipeWire, "
        "audible hardware, owner onboarding, or OS/SD update safety.")
    return True


def backup_guided(external, old_music, old_config, *,
                  out=print, require_terminal=True,
                  confirm_copy=None, confirm_save=None):
    """Safe offline first backup from an operator-mounted READ-ONLY old SD.

    Preflight BOTH data sets before the first write, then require independent
    COPY and SAVE consent when needed. Only the already private external
    archive may receive new files. Resume interrupted WAV copies by checksum
    and skip an existing identical saved preset archive. Final combined
    source-to-archive verification is read-only.
    """
    _guard(require_terminal=require_terminal)
    old_config = Path(old_config)
    if (not old_config.is_absolute() or ".." in old_config.parts
            or len(str(old_config)) > 1024):
        raise ValueError("Old SD config requires an absolute private path")
    config_settings = old_config / "settings.json"
    config_profiles = old_config / "volume-profiles.json"

    original, revision = _source_snapshot(config_settings, config_profiles)
    # The source and archive private directory descriptors, all bounded WAV
    # source names and *every* existing same-name hash are checked read-only.
    wav = _music_destination_plan(old_music, external)

    # Do not accept an existing but mismatched preset archive, even if WAV
    # copies would otherwise be safe. The operator must keep both originals
    # and resolve conflicts manually, not replace any existing file.
    archive_fd = music_transfer._private_dir(external)
    try:
        try:
            os.stat(FILENAME, dir_fd=archive_fd, follow_symlinks=False)
        except FileNotFoundError:
            archived = False
        else:
            archived = True
    finally:
        os.close(archive_fd)
    if archived:
        previous, _ = _load(external)
        if previous != original:
            raise ValueError("Existing preset archive differs from old SD")
    if wav["wav_total"] == 0:
        out("Empty old-SD music and archive confirmed read-only; "
            "saved EQ/profiles still require separate SAVE consent.")
    out("Old SD backup review: " + str(wav["wav_total"]) +
        " supported WAVs, " + str(wav["wav_matched"]) +
        " already matching, " + str(wav["wav_missing"]) +
        " requiring COPY; saved EQ/inactive profile archive " +
        ("matches" if archived else "needs SAVE") + ".")
    out("Only a separate private archive is written. Old SD, owner identity, "
        "Bluetooth, Wi-Fi, routes and live audio are untouched.")

    def check_old_presets():
        current, current_revision = _source_snapshot(
            config_settings, config_profiles)
        if current != original or current_revision != revision:
            raise OSError("Old SD audio presets changed during backup")

    if wav["wav_copy_needed"]:
        out("Step 1/2 – COPY only missing supported WAVs from already mounted "
            "old SD; matching archive WAVs are skipped.")
        completed = music_transfer.transfer(
            "backup", external, music_dir=old_music, resume=True,
            confirm=confirm_copy, out=out, require_terminal=False)
        if completed is not True:
            out("Guided backup STOPPED before WAV copy; original SD unchanged.")
            return False
    else:
        out("Step 1/2 – existing WAV archive already matches; no copy needed.")
    # Never proceed to SAVE while WAV data has gaps or conflicts. A
    # genuinely empty protected old-SD music folder may still preserve EQ
    # and inactive profiles; no meaningless WAV file copy is claimed.
    _verify_wavs_or_proven_empty(old_music, external)
    check_old_presets()

    if not archived:
        out("Step 2/2 – save only three archived EQ curves and INACTIVE volume "
            "profiles with distinct SAVE consent. No keys or current levels.")
        completed = export_presets(
            external, settings_path=config_settings,
            profile_path=config_profiles, confirm=confirm_save,
            out=out, require_terminal=False, allow_neutral=True)
        if completed is not True:
            out("Guided backup STOPPED at SAVE; existing verified WAV copies "
                "remain available for a later explicit resume.")
            return False
    else:
        out("Step 2/2 – private preset archive already identical; no SAVE needed.")

    check_old_presets()
    out("Final step – READ-ONLY verify old SD WAV hashes and saved presets "
        "against the complete external private archive.")
    checked = check_backup(
        external, old_music, str(old_config),
        out=out, require_terminal=False)
    out("Old SD backup verified for supported WAVs, saved EQ and inactive "
        "profiles. No SD flash, physical sound or owner transfer proved.")
    return checked


def restore_guided(external, *, settings_path=SETTINGS,
                   profile_path=mixer_control.PROFILE_PATH,
                   music_dir=music_transfer.DEFAULT_MUSIC_DIR,
                   out=print, require_terminal=True,
                   confirm_copy=None, confirm_profiles=None, confirm_eq=None):
    """One reviewed SD data migration with THREE distinct operator consents.

    No action until combined read-only WAV/EQ/profile preflight passes.
    Reuse the existing safe WAV resume, profile merge and neutral-only EQ
    writers rather than implementing a separate transfer mechanism.
    Cancellation leaves previously completed copies intact, so a later
    invocation can continue without overwriting any original data.
    """
    _guard(require_terminal=require_terminal)
    data, fingerprint = _load(external)
    out("Guided SD restore: REVIEW first; only archived WAVs and saved "
        "inactive audio presets are eligible. No identity or OS migration.")
    plan = plan_new_sd(
        external, settings_path=settings_path, profile_path=profile_path,
        music_dir=music_dir, out=out, require_terminal=False)
    if (plan["profile_conflicts"] or plan["profile_limit_exceeded"]
            or plan["eq_non_neutral_conflict"]):
        raise ValueError("Existing local profiles/EQ require manual resolution")
    if plan["ready_for_final_readonly_check"]:
        out("Archive already present; running final READ-ONLY comparison.")
        return check_new(
            external, settings_path=settings_path, profile_path=profile_path,
            music_dir=music_dir, out=out, require_terminal=False)

    def check_archive():
        latest, latest_hash = _load(external)
        if latest_hash != fingerprint or latest != data:
            raise OSError("Private preset archive changed during guided restore")

    check_archive()
    if plan["wav_copy_needed"]:
        out("Step 1/3 – restore only missing WAVs with separate COPY consent; "
            "exact existing matches are skipped. No files overwritten.")
        completed = music_transfer.transfer(
            "restore", external, music_dir=music_dir, resume=True,
            confirm=confirm_copy, out=out, require_terminal=False)
        if completed is not True:
            out("Guided restore STOPPED after WAV cancellation. Any earlier "
                "verified copies are retained; rerun to resume.")
            return False
        # Before touching mixer saved state, the complete WAV source set
        # must agree byte-for-byte with private destination files.
        music_transfer.transfer(
            "restore", external, music_dir=music_dir, verify=True,
            out=lambda _line: None, require_terminal=False)
        check_archive()
    else:
        out("Step 1/3 – all archived WAVs already match; no copy needed.")

    if plan["profile_missing"]:
        check_archive()
        out("Step 2/3 – add only missing INACTIVE profiles with separate MERGE "
            "consent; existing profiles and live levels remain untouched.")
        complete = merge_profiles(
            external, profile_path=profile_path, confirm=confirm_profiles,
            out=out, require_terminal=False)
        if complete is not True:
            out("Guided restore STOPPED at profile confirmation. Existing "
                "WAV copies are retained; no automatic rollback.")
            return False
        check_archive()
    else:
        out("Step 2/3 – archived inactive profiles already match, or none "
            "exist; no profile write needed.")

    if plan["eq_bands_different"]:
        check_archive()
        out("Step 3/3 – save only neutral-to-archived EQ with separate APPLY-EQ "
            "consent; no PipeWire stage, restart or live sound change.")
        complete = restore_eq(
            external, settings_path=settings_path, confirm=confirm_eq,
            out=out, require_terminal=False)
        if complete is not True:
            out("Guided restore STOPPED at EQ confirmation. Earlier saved "
                "copies/profiles are retained; no automatic rollback.")
            return False
        check_archive()
    else:
        out("Step 3/3 – all archived EQ bands already match; no write needed.")

    out("Final step – verify archived WAV hashes and all saved preset values "
        "READ ONLY before claiming stored-data equality.")
    verified = check_new(
        external, settings_path=settings_path, profile_path=profile_path,
        music_dir=music_dir, out=out, require_terminal=False)
    check_archive()
    out("Guided stored-data migration verified. No device ownership, live "
        "PipeWire sound, SD/OS update or physical hardware test implied.")
    return verified


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print("Offline Pi4 non-secret audio preset transfer, no owner migration.")
        print("Usage: audiohub-presets-transfer export|inspect|plan-profiles|restore-profiles|merge-profiles|restore-eq|verify|verify-merged|plan-new|check-new ABSOLUTE_PRIVATE_FOLDER")
        print("       audiohub-presets-transfer check-backup PRIVATE_BACKUP OLD_MUSIC_DIR OLD_CONFIG_DIR")
        print("       audiohub-presets-transfer backup-guided PRIVATE_BACKUP OLD_MUSIC_DIR OLD_CONFIG_DIR")
        print("       audiohub-presets-transfer restore-guided ABSOLUTE_PRIVATE_ARCHIVE")
        print("       audiohub-presets-transfer export-old OLD_SD_PRIVATE_CONFIG_DIR ABSOLUTE_PRIVATE_FOLDER")
        print("Export SAVE; strict restore RESTORE; conflict-free profile merge MERGE.")
        print("Saved EQ APPLY-EQ to neutral EQ only; verify-merged permits extra local profiles.")
        print("restore-guided requires separate COPY, MERGE and APPLY-EQ, then read-only verification.")
        print("backup-guided requires separate COPY and SAVE, then read-only verification.")
        print("Never imports keys, Bluetooth trust, Wi-Fi, IDs, live volume/mutes or OS.")
        return 0
    old_sd_mode = len(args) == 3 and args[0] == "export-old"
    backup_check_mode = len(args) == 4 and args[0] in ("check-backup", "backup-guided")
    if not (old_sd_mode or backup_check_mode or (len(args) == 2 and args[0] in (
            "export", "inspect", "plan-profiles", "restore-profiles",
            "merge-profiles", "restore-eq", "verify", "verify-merged",
            "plan-new", "check-new", "restore-guided"))):
        print("Choose an explicit preset action and an absolute private folder.")
        return 2
    try:
        if backup_check_mode:
            action = check_backup if args[0] == "check-backup" else backup_guided
            result = action(args[1], args[2], args[3])
        elif old_sd_mode:
            old_dir = Path(args[1])
            if (not old_dir.is_absolute() or ".." in old_dir.parts or
                    len(str(old_dir)) > 1024):
                raise ValueError("Unsafe read-only old SD configuration location")
            result = export_presets(
                args[2], settings_path=old_dir / "settings.json",
                profile_path=old_dir / "volume-profiles.json")
        else:
            operation = {"export": export_presets, "inspect": inspect,
                         "plan-profiles": plan_profiles,
                         "restore-profiles": restore_profiles,
                         "merge-profiles": merge_profiles,
                         "restore-eq": restore_eq,
                         "verify": verify, "verify-merged": verify_merged,
                         "plan-new": plan_new_sd, "check-new": check_new,
                         "restore-guided": restore_guided}[args[0]]
            result = operation(args[1])
        return 0 if result is not False else 1
    except (OSError, ValueError, TypeError, UnicodeError,
            mixer_control.MixerControlUnavailable):
        print("Private preset operation safely refused or incomplete; no owner data transferred.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
