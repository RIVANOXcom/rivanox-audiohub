# SPDX-License-Identifier: AGPL-3.0-only
"""Unprivileged offline controls for live AudioHub volume and mute settings.

This CLI creates no HTTP API, network listener, Bluetooth trust, audio
process or EQ rewrite. The existing supervisor reads the atomically updated
private settings on its next poll and applies conservative gain attenuation.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .mixer import CHANNELS, EQ_BANDS, defaults, patch_settings, requested_mix_controls
from .runtime import SETTINGS, STATE, _private_parent_fd, read_json, atomic_json

LOCK_NAME = ".mixer-settings.lock"
PROFILE_PATH = SETTINGS.with_name("volume-profiles.json")
MAX_CUSTOM_PROFILES = 8
PROFILE_FIELDS = ("master", *CHANNELS)
_PROFILE_NAME = re.compile(r"[a-z][a-z0-9-]{0,23}", re.ASCII)

# Conservative convenience starting points, NOT calibrated output levels.
# In every preset, existing per-input mute and stored EQ are untouched.
# Volume order: master, music, laptop, tablet.
PRESET_VOLUMES = {
    "quiet": (15, 25, 25, 25),
    "balanced": (30, 40, 40, 40),
    "music-priority": (30, 55, 20, 20),
}

# Fixed, conservative starting points; NOT a hearing test or calibrated EQ.
# Tuple order matches EQ_BANDS (bass, mid, treble). All other mixer controls
# are kept intact. The saved EQ is NOT automatically staged or applied live.
EQ_PRESET_CURVES = {
    "warm": (3, 0, -1),
    "voice": (-2, 3, 1),
    "detail": (0, 1, 3),
}


def eq_preset_patch(slot, name):
    """One-slot, fixed 3-band curve for a reviewed private EQ transaction."""
    if type(slot) is not str or slot not in CHANNELS:
        raise MixerControlUnavailable("Unknown local EQ input")
    if type(name) is not str or name not in EQ_PRESET_CURVES:
        raise MixerControlUnavailable("Unknown local EQ sound profile")
    return {slot: dict(zip(EQ_BANDS, EQ_PRESET_CURVES[name]))}


def reset_input_eq_patch(slot):
    """Neutralize one input's three EQ bands in a single guarded change."""
    if type(slot) is not str or slot not in CHANNELS:
        raise MixerControlUnavailable("Unknown local EQ input")
    return {slot: {band: 0 for band in EQ_BANDS}}


def copy_input_eq_patch(source, destination, *, path=SETTINGS):
    """Read one exact private mixer generation to copy three source EQ bands.

    Do not copy volume, mute, source roles or private device identities. The
    returned revision MUST match the reviewed preview and be guarded again
    under the exclusive writer lock before any save.
    """
    if (type(source) is not str or source not in CHANNELS
            or type(destination) is not str or destination not in CHANNELS
            or source == destination):
        raise MixerControlUnavailable("Select two different local EQ inputs")
    current, revision = _preview_snapshot(path=path)
    return ({destination: {
        band: current[source][band] for band in EQ_BANDS
    }}, revision)


def swap_input_eq_patch(left, right, *, path=SETTINGS):
    """Exchange both inputs' three saved EQ bands in ONE private generation.

    Neither input's volume/mute nor the master, third input or device routing
    may change. Pin both source curves to the SAME read-only mixer revision;
    the confirmed writer must compare that revision under its exclusive lock.
    """
    if (type(left) is not str or left not in CHANNELS
            or type(right) is not str or right not in CHANNELS
            or left == right):
        raise MixerControlUnavailable("Select two different local EQ inputs")
    current, revision = _preview_snapshot(path=path)
    return ({
        left: {band: current[right][band] for band in EQ_BANDS},
        right: {band: current[left][band] for band in EQ_BANDS},
    }, revision)


def isolate_input_patch(slot):
    """Atomically mute ONLY the other inputs; never unmute or raise gain.

    This is a conservative local audio-isolation helper, not a solo control
    that silently switches on a previously muted or zero-level input.
    """
    if type(slot) is not str or slot not in CHANNELS:
        raise MixerControlUnavailable("Unknown local input slot")
    return {other: {"mute": True} for other in CHANNELS if other != slot}


def _isolation_restore_patch(slot, baseline):
    """Restore exactly two other mutes from a strict operator-owned snapshot."""
    source = _decode_baseline(baseline)
    return {other: {"mute": source[other]["mute"]}
            for other in CHANNELS if other != slot}


def preview_restore_isolation(slot, baseline, *, path=SETTINGS):
    """Refuse to restore mutes unless the whole mixer still matches isolation.

    An operator-provided baseline is not proof that isolation occurred. It
    is only a bounded original settings snapshot. Validate ALL controls,
    including the selected channel's mute, master and EQ, before proposing
    two precise other-channel mute restorations. A second snapshot's revision
    must match: otherwise a concurrent or ABA edit invalidates the preview.
    """
    patch = isolate_input_patch(slot)
    original = _decode_baseline(baseline)
    expected = patch_settings(original, patch)
    current, revision = _preview_snapshot(path=path)
    if current != expected:
        raise MixerControlUnavailable(
            "Mixer settings differ from the expected isolated baseline")
    to_restore = _isolation_restore_patch(slot, baseline)
    plan = preview_change(to_restore, path=path)
    if plan["revision"] != revision:
        raise MixerControlUnavailable(
            "Mixer settings changed during isolation restore preview")
    return {
        **plan,
        "operation": "isolation-restore-preview",
        "source": slot,
        "scope": "two-other-input-mutes-only",
        "baseline_trust": "operator_supplied_not_authenticated",
        "other_controls_preserved": True,
        "selected_input_mute_preserved": True,
        "requires_separate_revision_guarded_confirmation": True,
    }


def restore_isolation(slot, baseline, *, path=SETTINGS,
                      confirmed=False, if_revision=None):
    """Atomically restore two mutes only, after an independently reviewed plan.

    Revalidate the untrusted baseline and the current isolated snapshot before
    entering the existing exclusive-lock, revision-checked mixer writer.
    If any actor writes in the interval, the writer refuses the old revision.
    Never restore volume/EQ/master, route sources or unmute the selected input.
    """
    if confirmed is not True or type(if_revision) is not str:
        raise MixerControlUnavailable(
            "Explicit guarded local isolation restore confirmation required")
    plan = preview_restore_isolation(slot, baseline, path=path)
    if if_revision != plan["revision"]:
        raise StaleMixerPreview("Private mixer isolation restore preview is stale")
    return change(_isolation_restore_patch(slot, baseline),
                  path=path, confirmed=True, if_revision=if_revision)


def preset_patch(name):
    """Generate one explicit, schema-validated volume-only profile patch."""
    if type(name) is not str or name not in PRESET_VOLUMES:
        raise MixerControlUnavailable("Unknown local mixer preset")
    master, music, laptop, tablet = PRESET_VOLUMES[name]
    return {
        "master": master,
        "music": {"volume": music},
        "laptop": {"volume": laptop},
        "tablet": {"volume": tablet},
    }


class MixerControlUnavailable(RuntimeError):
    """Sanitized local status; never echo untrusted private file contents."""


class StaleMixerPreview(MixerControlUnavailable):
    """A conditional write was refused because the preview became stale."""


class StaleProfilePreview(MixerControlUnavailable):
    """The private catalog changed since the operator reviewed its version."""


def _check_profile_name(name):
    if type(name) is not str or _PROFILE_NAME.fullmatch(name) is None:
        raise MixerControlUnavailable("Invalid local volume profile name")
    return name


def _profile_levels(values):
    """Reject extra keys, booleans and unbounded levels in private profiles."""
    if (type(values) is not dict or set(values) != set(PROFILE_FIELDS)
            or any(type(values[key]) is not int or not 0 <= values[key] <= 100
                   for key in PROFILE_FIELDS)):
        raise MixerControlUnavailable("Invalid local volume profile levels")
    return {key: values[key] for key in PROFILE_FIELDS}


def _profile_patch(values):
    valid = _profile_levels(values)
    return {"master": valid["master"],
            **{slot: {"volume": valid[slot]} for slot in CHANNELS}}


def _profile_catalog(path, dirfd):
    """Read only a private regular profile catalog; reject corrupt state."""
    try:
        os.stat(path.name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return {"version": 1, "profiles": {}}
    fallback = {"__invalid_private_profile_catalog__": True}
    data = read_json(path, fallback)
    if data is fallback or type(data) is not dict or set(data) != {"version", "profiles"}:
        raise MixerControlUnavailable("Unsafe or invalid private volume profiles")
    if (type(data["version"]) is not int or data["version"] != 1
            or type(data["profiles"]) is not dict
            or len(data["profiles"]) > MAX_CUSTOM_PROFILES):
        raise MixerControlUnavailable("Invalid private volume profiles")
    for name, values in data["profiles"].items():
        _check_profile_name(name)
        _profile_levels(values)
    return data


def _profile_catalog_with_revision(path, dirfd):
    """Validated catalog + private file generation, including ABA replacements."""
    before = _state_identity(path, dirfd)
    catalog = _profile_catalog(path, dirfd)
    if before != _state_identity(path, dirfd):
        raise MixerControlUnavailable("Private profile catalog changed during read")
    raw = json.dumps({"identity": before, "catalog": catalog},
                     sort_keys=True, separators=(",", ":"), allow_nan=False)
    return catalog, "p1-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def profile_selection_overview(*, path=PROFILE_PATH, settings_path=SETTINGS):
    """List all saved profiles with projected effects on current requests.

    Read just ONE catalog and ONE mixer-settings generation; refuse a
    simultaneous atomic replacement of either. No locks, writes, routing,
    EQ changes, sound measurements or automatic profile selection.
    """
    path, settings_path = _profile_snapshot_paths(path, settings_path)
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    try:
        dirfd = _private_parent_fd(path, create=False)
    except FileNotFoundError:
        # No profile catalog or mixer settings can exist in a missing
        # private directory. Do not create it merely to show the choices.
        current, mixer_revision = _preview_snapshot(path=settings_path)
        catalog = {"version": 1, "profiles": {}}
        profile_revision = None
    else:
        try:
            before_profile = _state_identity(path, dirfd)
            before_mixer = _state_identity(settings_path, dirfd)
            catalog, profile_revision = _profile_catalog_with_revision(path, dirfd)
            current, mixer_revision = _state_with_revision(settings_path, dirfd)
            if (before_profile != _state_identity(path, dirfd)
                    or before_mixer != _state_identity(settings_path, dirfd)):
                raise MixerControlUnavailable("Private profile or mixer changed during selection")
        finally:
            os.close(dirfd)
    requested = _profile_levels({
        "master": current["master"],
        **{slot: current[slot]["volume"] for slot in CHANNELS},
    })
    muted = [slot for slot in CHANNELS if current[slot]["mute"]]
    choices = []
    for name in sorted(catalog["profiles"]):
        values = _profile_levels(catalog["profiles"][name])
        deltas = {field: values[field] - requested[field]
                  for field in PROFILE_FIELDS}
        changed = [field for field in PROFILE_FIELDS if deltas[field] != 0]
        choices.append({
            "name": name,
            "requested_volumes": values,
            "deltas_from_current": deltas,
            "would_change": changed,
            "already_matches": not changed,
            "muted_sources_remaining_muted": list(muted),
            "volume_changes_while_muted": [
                slot for slot in muted if deltas[slot] != 0
            ],
        })
    return {
        "mode": "profile-choices-read-only",
        "current_requested_volumes": requested,
        "profiles": choices,
        "profile_count": len(choices),
        "profile_limit": MAX_CUSTOM_PROFILES,
        "mixer_revision": mixer_revision,
        "profile_revision": profile_revision,
        "preview_selected_with": "--preview profile NAME",
        "apply_requires_separate_confirmation": True,
        "mute_states_preserved": True,
        "stored_eq_preserved": True,
        "profile_written": False, "mixer_settings_written": False,
        "audible_playback_verified": False,
    }


def compare_profile_to_current(name, *, path=PROFILE_PATH,
                               settings_path=SETTINGS):
    """Show requested mixer levels alongside one saved volume profile.

    Both settings and the profile catalog are read from a private directory
    without creating any files or locks. Reject an intervening replacement
    of EITHER file instead of presenting a misleading mixed generation.
    No active or stored values are changed, and no audio is measured.
    """
    _check_profile_name(name)
    path, settings_path = _profile_snapshot_paths(path, settings_path)
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    try:
        dirfd = _private_parent_fd(path, create=False)
    except FileNotFoundError:
        raise MixerControlUnavailable("Private volume profile catalog not found") from None
    try:
        profile_identity = _state_identity(path, dirfd)
        mixer_identity = _state_identity(settings_path, dirfd)
        catalog, profile_revision = _profile_catalog_with_revision(path, dirfd)
        current, mixer_revision = _state_with_revision(settings_path, dirfd)
        if (_state_identity(path, dirfd) != profile_identity
                or _state_identity(settings_path, dirfd) != mixer_identity):
            raise MixerControlUnavailable("Private mixer or profile changed during comparison")
    finally:
        os.close(dirfd)
    if name not in catalog["profiles"]:
        raise MixerControlUnavailable("Named volume profile does not exist")
    saved = _profile_levels(catalog["profiles"][name])
    requested = _profile_levels({
        "master": current["master"],
        **{slot: current[slot]["volume"] for slot in CHANNELS},
    })
    differences = [
        {"control": field, "saved": saved[field], "current": requested[field],
         "delta": requested[field] - saved[field]}
        for field in PROFILE_FIELDS if saved[field] != requested[field]
    ]
    return {
        "mode": "profile-vs-current-only", "profile": name,
        "saved_volumes": saved, "current_volumes": requested,
        "differences": differences, "same_levels": not differences,
        "profile_revision": profile_revision, "mixer_revision": mixer_revision,
        "profile_written": False, "mixer_settings_written": False,
        "audible_playback_verified": False,
    }


def compare_volume_profiles(left, right, *, path=PROFILE_PATH):
    """Read one private catalog generation and compare only four volume fields.

    No lock, directory creation, settings write or audio action is performed.
    If a concurrent atomic writer changes this file mid-read, refuse to
    present a potentially mismatched comparison of two generations.
    """
    _check_profile_name(left)
    _check_profile_name(right)
    if left == right:
        raise MixerControlUnavailable("Choose two distinct profiles for comparison")
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    path = Path(path)
    try:
        dirfd = _private_parent_fd(path, create=False)
    except FileNotFoundError:
        raise MixerControlUnavailable("Private volume profile catalog not found") from None
    try:
        catalog, revision = _profile_catalog_with_revision(path, dirfd)
    finally:
        os.close(dirfd)
    profiles = catalog["profiles"]
    if left not in profiles or right not in profiles:
        raise MixerControlUnavailable("Named volume profile does not exist")
    first = _profile_levels(profiles[left])
    second = _profile_levels(profiles[right])
    differences = [
        {"control": field, "left": first[field], "right": second[field],
         "delta": second[field] - first[field]}
        for field in PROFILE_FIELDS if first[field] != second[field]
    ]
    return {
        "mode": "profile-compare-only",
        "left": left, "right": right,
        "left_volumes": first, "right_volumes": second,
        "differences": differences, "same_levels": not differences,
        "profile_revision": revision,
        "profile_written": False, "mixer_settings_written": False,
        "audible_playback_verified": False,
    }


def preview_profile_copy(source, destination, *, path=PROFILE_PATH):
    """Plan an immutable volume-only local copy, with NO file or lock creation."""
    _check_profile_name(source)
    _check_profile_name(destination)
    if source == destination:
        raise MixerControlUnavailable("Profile copy needs a different destination")
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    path = Path(path)
    try:
        dirfd = _private_parent_fd(path, create=False)
    except FileNotFoundError:
        raise MixerControlUnavailable("Private volume profile catalog not found") from None
    try:
        catalog, revision = _profile_catalog_with_revision(path, dirfd)
    finally:
        os.close(dirfd)
    if source not in catalog["profiles"]:
        raise MixerControlUnavailable("Source volume profile not found")
    if destination in catalog["profiles"]:
        raise MixerControlUnavailable("Destination volume profile already exists")
    if len(catalog["profiles"]) >= MAX_CUSTOM_PROFILES:
        raise MixerControlUnavailable("Private volume profile limit reached")
    return {
        "mode": "profile-copy-preview",
        "source": source, "destination": destination,
        "volumes": _profile_levels(catalog["profiles"][source]),
        "profile_revision": revision,
        "profile_written": False, "source_unchanged": True,
        "mixer_settings_written": False, "audible_playback_verified": False,
    }


def copy_volume_profile(source, destination, *, path=PROFILE_PATH,
                        if_profile_revision=None, confirmed=False):
    """One locked, revision-guarded clone of volumes; never overwrite originals."""
    if confirmed is not True:
        raise MixerControlUnavailable("Explicit local profile save confirmation required")
    _check_profile_name(source)
    _check_profile_name(destination)
    if source == destination:
        raise MixerControlUnavailable("Profile copy needs a different destination")
    if (type(if_profile_revision) is not str or len(if_profile_revision) != 67
            or not if_profile_revision.startswith("p1-")
            or any(c not in "0123456789abcdef" for c in if_profile_revision[3:])):
        raise MixerControlUnavailable("Valid private profile revision required")

    def source_levels(dirfd):
        current, revision = _profile_catalog_with_revision(Path(path), dirfd)
        if revision != if_profile_revision:
            raise StaleProfilePreview("Private volume profile preview became stale")
        if source not in current["profiles"]:
            raise MixerControlUnavailable("Source volume profile no longer exists")
        return current["profiles"][source]

    result = _save_profile_under_lock(destination, source_levels, path=path)
    return {"profile_copied_from": source, **result, "source_unchanged": True}


def list_volume_profiles(*, path=PROFILE_PATH):
    """Read private profiles with NO directory/file/lock creation."""
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    path = Path(path)
    try:
        dirfd = _private_parent_fd(path, create=False)
    except FileNotFoundError:
        return {"version": 1, "profiles": {}}
    try:
        return _profile_catalog(path, dirfd)
    finally:
        os.close(dirfd)


def saved_profile_patch(name, *, path=PROFILE_PATH):
    _check_profile_name(name)
    profiles = list_volume_profiles(path=path)["profiles"]
    if name not in profiles:
        raise MixerControlUnavailable("Local volume profile does not exist")
    return _profile_patch(profiles[name])


def _save_profile_under_lock(name, levels_from_snapshot, *, path):
    """Serialize private profile creation with CLI mixer writers.

    The supplier runs inside the same exclusive lock, so it may safely
    compare the live mixer settings generation before persisting a profile.
    No mixer settings are written by this helper.
    """
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    path = Path(path)
    dirfd = _private_parent_fd(path, create=True)
    lockfd = None
    try:
        lockfd = os.open(LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                         | os.O_CLOEXEC, 0o600, dir_fd=dirfd)
        st = os.fstat(lockfd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077):
            raise MixerControlUnavailable("Unsafe private profile writer lock")
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        catalog = _profile_catalog(path, dirfd)
        if name in catalog["profiles"]:
            raise MixerControlUnavailable("Local volume profile already exists")
        if len(catalog["profiles"]) >= MAX_CUSTOM_PROFILES:
            raise MixerControlUnavailable("Private volume profile limit reached")
        values = _profile_levels(levels_from_snapshot(dirfd))
        catalog["profiles"][name] = values
        atomic_json(path, catalog)
        return {"profile_saved": name, "volumes": values,
                "mixer_settings_written": False,
                "audible_playback_verified": False}
    finally:
        if lockfd is not None:
            os.close(lockfd)
        os.close(dirfd)


def save_volume_profile(name, master, music, laptop, tablet, *,
                        path=PROFILE_PATH, confirmed=False):
    """Create one immutable private volume profile; do not apply it."""
    if confirmed is not True:
        raise MixerControlUnavailable("Explicit local profile save confirmation required")
    _check_profile_name(name)
    values = _profile_levels(dict(zip(PROFILE_FIELDS,
                                      (master, music, laptop, tablet))))
    return _save_profile_under_lock(name, lambda _dirfd: values, path=path)


def _profile_snapshot_paths(path, settings_path):
    """Only a profile catalog next to its own local mixer settings is valid."""
    path, settings_path = Path(path), Path(settings_path)
    if (path.name != "volume-profiles.json" or settings_path.name != "settings.json"
            or path.parent != settings_path.parent):
        raise MixerControlUnavailable("Local profile and mixer paths must share a directory")
    return path, settings_path


def preview_current_profile(name, *, path=PROFILE_PATH, settings_path=SETTINGS):
    """Read-only snapshot of existing REQUESTED levels, never hardware sound."""
    _check_profile_name(name)
    path, settings_path = _profile_snapshot_paths(path, settings_path)
    catalog = list_volume_profiles(path=path)
    if name in catalog["profiles"]:
        raise MixerControlUnavailable("Local volume profile already exists")
    if len(catalog["profiles"]) >= MAX_CUSTOM_PROFILES:
        raise MixerControlUnavailable("Private volume profile limit reached")
    current, revision = _preview_snapshot(path=settings_path)
    levels = {"master": current["master"],
              **{slot: current[slot]["volume"] for slot in CHANNELS}}
    return {
        "mode": "profile-capture-preview", "name": name,
        "revision": revision, "volumes": _profile_levels(levels),
        "profile_written": False, "mixer_settings_written": False,
        "audible_playback_verified": False,
    }


def capture_current_profile(name, *, path=PROFILE_PATH, settings_path=SETTINGS,
                            if_revision=None, confirmed=False):
    """Save validated current requested volumes if the operator's snapshot matches.

    Capture and catalog creation share the same exclusive writer lock. A
    concurrent mixer change (including EQ or an ABA generation) rejects the
    entire profile creation, without touching active settings.
    """
    if confirmed is not True:
        raise MixerControlUnavailable("Explicit local profile save confirmation required")
    _check_profile_name(name)
    if (type(if_revision) is not str or len(if_revision) != 67
            or not if_revision.startswith("v1-")
            or any(c not in "0123456789abcdef" for c in if_revision[3:])):
        raise MixerControlUnavailable("A valid preview revision is required")
    path, settings_path = _profile_snapshot_paths(path, settings_path)

    def current_levels(dirfd):
        current, revision = _state_with_revision(settings_path, dirfd)
        if revision != if_revision:
            raise StaleMixerPreview("Local volume profile capture preview is stale")
        return {"master": current["master"],
                **{slot: current[slot]["volume"] for slot in CHANNELS}}

    return _save_profile_under_lock(name, current_levels, path=path)

def _existing_state(path, dirfd):
    """Reject malformed existing state instead of overwriting with defaults."""
    try:
        os.stat(path.name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return defaults()
    fallback = {"__invalid_private_mixer_state__": True}
    current = read_json(path, fallback)
    if current is fallback:
        raise MixerControlUnavailable("Existing private mixer settings unsafe or unreadable")
    try:
        return patch_settings(current, {})
    except (TypeError, ValueError) as exc:
        raise MixerControlUnavailable("Existing private mixer settings invalid") from None


def show(*, path=SETTINGS):
    """Read existing valid user-private settings; never create a file."""
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    try:
        dirfd = _private_parent_fd(Path(path), create=False)
    except FileNotFoundError:
        return defaults()
    try:
        return _existing_state(Path(path), dirfd)
    finally:
        os.close(dirfd)


def _valid_acknowledged_controls(value):
    if type(value) is not dict or set(value) != {"master", *CHANNELS}:
        return False
    if type(value["master"]) is not int or not 0 <= value["master"] <= 100:
        return False
    for slot in CHANNELS:
        ctl = value[slot]
        if (type(ctl) is not dict or set(ctl) != {"volume", "mute"}
                or type(ctl["volume"]) is not int or not 0 <= ctl["volume"] <= 100
                or type(ctl["mute"]) is not bool):
            return False
    return True


def application_status(*, path=SETTINGS, runtime_path=STATE, now=None):
    """Read-only, private local comparison; never claim audible sound.

    'accepted' means every requested mixer command returned successfully on a
    recent complete supervisor poll with USB + all three EQ sinks present.
    'pending' means a newer/different requested level has not been observed.
    Missing, stale, unsafe, or legacy status is ALWAYS unavailable.
    """
    requested = requested_mix_controls(show(path=path))
    snapshot = read_json(runtime_path, {})
    at = snapshot.get("updated_at")
    now = int(time.time()) if now is None else now
    fresh = (type(now) is int and type(at) is int and 0 <= now - at <= 15)
    acknowledged = snapshot.get("mixer_controls_accepted")
    if (not fresh or snapshot.get("usb_route_ready") is not True
            or not _valid_acknowledged_controls(acknowledged)):
        state = "unavailable"
        pending_controls = None
    else:
        # Pinpoint only bounded, fixed mixer fields, never arbitrary keys or
        # device identifiers. No per-field positive claim without complete,
        # fresh acknowledgement of the whole PipeWire control command set.
        pending_controls = []
        if requested["master"] != acknowledged["master"]:
            pending_controls.append("master")
        for slot in CHANNELS:
            for control in ("volume", "mute"):
                if requested[slot][control] != acknowledged[slot][control]:
                    pending_controls.append(slot + "." + control)
        state = "pending" if pending_controls else "accepted"
    return {"requested": requested, "supervisor": state,
            "pending_controls": pending_controls,
            # Local-only timestamp from the SAME private snapshot as the
            # accepted controls; do not trust it if the snapshot is stale.
            "supervisor_updated_at": at if fresh else None,
            "audible_playback_verified": False}


def _state_identity(path, dirfd):
    """Stat one private regular file, without traversing a symlink."""
    try:
        st = os.stat(path.name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
            or st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) & 0o077):
        raise MixerControlUnavailable("Unsafe private mixer settings file")
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _state_with_revision(path, dirfd):
    """Read validated settings from one stable file generation, no writes.

    Atomic CLI replacements change inode identity even if values return to
    their original state (A -> B -> A). Reject a concurrent change during
    the read, rather than issuing a revision from mismatched snapshots.
    """
    before = _state_identity(path, dirfd)
    current = _existing_state(path, dirfd)
    if before != _state_identity(path, dirfd):
        raise MixerControlUnavailable("Private mixer settings changed during read")
    data = json.dumps({"identity": before, "settings": current},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    return current, "v1-" + hashlib.sha256(data.encode("utf-8")).hexdigest()


def _preview_snapshot(*, path=SETTINGS):
    """Read a preview generation without creating directories or lock files."""
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    path = Path(path)
    try:
        dirfd = _private_parent_fd(path, create=False)
    except FileNotFoundError:
        # A never-initialized mixer still has a deterministic preview version.
        raw = json.dumps({"identity": None, "settings": defaults()},
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
        return defaults(), "v1-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    try:
        return _state_with_revision(path, dirfd)
    finally:
        os.close(dirfd)


def _baseline_token(settings):
    """Encode only bounded known master/input/EQ controls; no files or IDs."""
    value = [1, settings["master"], [
        [settings[slot]["volume"], settings[slot]["mute"],
         *(settings[slot][band] for band in EQ_BANDS)]
        for slot in CHANNELS
    ]]
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("ascii")
    return "b1-" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_baseline(value):
    """Strict compact operator-supplied baseline, never untrusted JSON keys."""
    if (type(value) is not str or not 4 <= len(value) <= 256
            or not value.startswith("b1-")):
        raise MixerControlUnavailable("Invalid private mixer comparison baseline")
    token = value[3:]
    if not token or any(ch not in
                        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                        for ch in token):
        raise MixerControlUnavailable("Invalid private mixer comparison baseline")
    try:
        raw = base64.b64decode(token + "=" * (-len(token) % 4),
                               altchars=b"-_", validate=True)
        if len(raw) > 200:
            raise ValueError("Oversized mixer comparison baseline")
        val = json.loads(raw)
        if (type(val) is not list or len(val) != 3 or type(val[0]) is not int
                or val[0] != 1 or type(val[1]) is not int
                or type(val[2]) is not list or len(val[2]) != len(CHANNELS)):
            raise ValueError("Invalid mixer comparison shape")
        state = {"master": val[1]}
        for slot, controls in zip(CHANNELS, val[2]):
            if (type(controls) is not list or len(controls) != 5
                    or type(controls[0]) is not int
                    or type(controls[1]) is not bool
                    or any(type(x) is not int for x in controls[2:])):
                raise ValueError("Invalid mixer comparison controls")
            state[slot] = {
                "volume": controls[0], "mute": controls[1],
                **dict(zip(EQ_BANDS, controls[2:]))
            }
        state = patch_settings(defaults(), state)
        if _baseline_token(state) != value:
            raise ValueError("Noncanonical mixer comparison baseline")
        return state
    except (ValueError, TypeError, UnicodeError, binascii.Error, OverflowError):
        raise MixerControlUnavailable("Invalid private mixer comparison baseline") from None


def _control_differences(before, after, *, fields=("volume", "mute")):
    """Readable fixed-order changes; include EQ only in baseline comparisons."""
    differences = []
    if before["master"] != after["master"]:
        differences.append({"control": "master", "previous": before["master"],
                            "current": after["master"]})
    for slot in CHANNELS:
        for field in fields:
            if before[slot][field] != after[slot][field]:
                differences.append({
                    "control": slot + "." + field,
                    "previous": before[slot][field],
                    "current": after[slot][field],
                })
    return differences


def preview_change(patch, *, path=SETTINGS, baseline=None):
    """Show a validated prospective request; no lock, write, or audio action.

    The returned opaque revision may be passed to an independently confirmed
    change, which compares it UNDER the existing exclusive writer lock.
    Return only known volume/mute fields, never private routes or IDs.
    """
    try:
        previous = _decode_baseline(baseline) if baseline is not None else None
        current, revision = _preview_snapshot(path=path)
        before = requested_mix_controls(current)
        desired = patch_settings(current, patch)
        after = requested_mix_controls(desired)
    except (TypeError, ValueError):
        raise MixerControlUnavailable("Invalid mixer preview setting") from None
    changes = []
    if before["master"] != after["master"]:
        changes.append("master")
    for slot in CHANNELS:
        for field in ("volume", "mute"):
            if before[slot][field] != after[slot][field]:
                changes.append(slot + "." + field)
    compared = (_control_differences(
        previous, current, fields=("volume", "mute", *EQ_BANDS)
    ) if previous is not None else None)
    planned = _control_differences(before, after)
    eq_changes = [
        {"source": slot, "band": band, "before": current[slot][band],
         "after": desired[slot][band]}
        for slot in CHANNELS for band in EQ_BANDS
        if current[slot][band] != desired[slot][band]
    ]
    return {
        "mode": "preview-only",
        "revision": revision,
        "comparison_baseline": _baseline_token(current),
        # null means no prior snapshot was provided; [] means same values.
        # A previous opaque revision alone cannot reveal past control values.
        "changed_since_baseline": compared,
        "planned_changes": planned,
        "before": before,
        "after": after,
        "would_change": changes,
        "eq_changes": eq_changes,
        "eq_live_applied": False,
        "settings_written": False,
        "supervisor_applied": False,
        "audible_playback_verified": False,
    }


def _profile_selection_impact(plan, name):
    """Make one already-computed read-only profile preview human-actionable.

    Derive everything from the SAME before/after snapshots/revision to avoid
    racing a second settings read. A profile patch is volume-only; any mute
    difference would violate that safety promise and is refused.
    """
    _check_profile_name(name)
    before, after = plan["before"], plan["after"]
    controls = []
    for slot in CHANNELS:
        old, new = before[slot], after[slot]
        if old["mute"] != new["mute"]:
            raise MixerControlUnavailable("Profile preview cannot modify mute state")
        previous, requested = old["volume"], new["volume"]
        controls.append({
            "source": slot,
            "previous": previous,
            "requested": requested,
            "delta": requested - previous,
            "mute_preserved": True,
            "stays_muted": old["mute"],
            "volume_change_while_muted": old["mute"] and previous != requested,
        })
    master_before, master_after = before["master"], after["master"]
    changed = (master_before != master_after
               or any(row["delta"] != 0 for row in controls))
    muted = [row["source"] for row in controls if row["stays_muted"]]
    return {
        "profile": name,
        "master": {
            "previous": master_before, "requested": master_after,
            "delta": master_after - master_before,
        },
        "sources": controls,
        "changed": changed,
        "muted_sources_remaining_muted": muted,
        "mute_states_preserved": True,
        "stored_eq_preserved": True,
        "separate_confirmation_required": True,
        "requested_levels_only": True,
        "audible_playback_verified": False,
    }


def change(patch, *, path=SETTINGS, confirmed=False, if_revision=None):
    """Apply one bounded, atomic user-requested control patch.

    Lock serializes concurrent *CLI writers*. The running supervisor reads
    each atomic snapshot (old or new) and applies the controls on a future
    poll. No arbitrary source, device ID or gain command is accepted.
    """
    if confirmed is not True:
        raise MixerControlUnavailable("Explicit local mixer change confirmation required")
    if if_revision is not None and (
            type(if_revision) is not str or len(if_revision) != 67
            or not if_revision.startswith("v1-")
            or any(ch not in "0123456789abcdef" for ch in if_revision[3:])):
        raise MixerControlUnavailable("Invalid preview revision")
    if os.geteuid() == 0:
        raise MixerControlUnavailable("Use the unprivileged audiohub account")
    path = Path(path)
    dirfd = _private_parent_fd(path, create=True)
    lockfd = None
    try:
        lockfd = os.open(
            LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=dirfd,
        )
        st = os.fstat(lockfd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077):
            raise MixerControlUnavailable("Unsafe private mixer settings lock")
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        if if_revision is None:
            current = _existing_state(path, dirfd)
        else:
            current, actual_revision = _state_with_revision(path, dirfd)
            if actual_revision != if_revision:
                raise StaleMixerPreview("Mixer preview no longer current")
        try:
            desired = patch_settings(current, patch)
        except (TypeError, ValueError):
            raise MixerControlUnavailable("Invalid mixer setting") from None
        atomic_json(path, desired)
        return desired
    finally:
        if lockfd is not None:
            os.close(lockfd)
        os.close(dirfd)


def wait_for_supervisor(saved, *, checks=10, saved_at=None):
    """Bounded follow-up for a saved request; never measure actual sound.

    Require a complete fresh acknowledgement timestamped *after* the save:
    a recent matching status from before the write cannot prove new delivery.
    If another local writer changes the request, report 'superseded' rather
    than attributing that writer's acknowledgement to this invocation.
    This reads status only; it never re-applies an update automatically.
    """
    expected = requested_mix_controls(saved)
    # The saved settings have just been atomically committed by the caller.
    # Require an ACK from a *subsequent* supervisor poll, not merely a
    # recent ACK matching the same levels from an earlier cycle.
    saved_after = int(time.time()) if saved_at is None else saved_at
    if (type(checks) is not int or not 0 <= checks <= 10
            or type(saved_after) is not int):
        raise ValueError("Invalid bounded supervisor wait")
    result = "unavailable"
    pending = None
    for attempt in range(checks + 1):
        try:
            current = application_status()
        except (MixerControlUnavailable, OSError, ValueError, TypeError):
            current = {}
        if type(current) is not dict:
            current = {}
        current_requested = current.get("requested")
        if current_requested is not None and current_requested != expected:
            result = "superseded"
            pending = None
            break
        if current_requested == expected and current.get("supervisor") == "accepted":
            observed_at = current.get("supervisor_updated_at")
            if type(observed_at) is int and observed_at > saved_after:
                result = "accepted"
                pending = []
                break
            # An older matching success can belong to a *previous* setting
            # cycle. It is not evidence of post-write acceptance.
            result = "pending" if type(observed_at) is int else "unavailable"
            pending = None
        elif current_requested == expected and current.get("supervisor") == "pending":
            result = "pending"
            pending = current.get("pending_controls")
        else:
            result = "unavailable"
            pending = None
        if attempt < checks:
            time.sleep(1)
    return {"settings_written": True, "saved_request": expected,
            "delivery_state": result, "pending_controls": pending,
            "audible_playback_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline-only AudioHub levels and mute, not a remote mixer API"
    )
    parser.add_argument("--confirm-local-mixer-change", action="store_true",
                        help="Explicitly approve an atomic local settings update")
    parser.add_argument("--confirm-local-profile-save", action="store_true",
                        help="Explicitly create one immutable private custom volume profile")
    parser.add_argument("--preview", action="store_true",
                        help="Show requested changes without writing any settings")
    parser.add_argument("--if-preview-revision", metavar="REV",
                        help="Require matching revision from a recent --preview before saving")
    parser.add_argument("--if-profile-revision", metavar="PROFILE_REV",
                        help="Require same private catalog version for confirmed copy-profile")
    parser.add_argument("--compare-baseline", metavar="BASELINE",
                        help="Compare current inputs and stored EQ to an earlier preview snapshot")
    parser.add_argument("--wait-for-supervisor", action="store_true",
                        help="After confirmed save, check for software acceptance for up to 10 seconds")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("show", help="Read-only current private mixer controls")
    commands.add_parser("status", help="Local saved vs supervisor-accepted levels (not sound)")
    master = commands.add_parser("set-master", help="Set master requested volume 0..100")
    master.add_argument("percent", type=int)
    channel = commands.add_parser("set-volume", help="Set a channel volume 0..100")
    channel.add_argument("slot", choices=CHANNELS)
    channel.add_argument("percent", type=int)
    mute = commands.add_parser("mute", help="Set a channel mute (on/off)")
    mute.add_argument("slot", choices=CHANNELS)
    mute.add_argument("value", choices=("on", "off"))
    eq = commands.add_parser(
        "set-eq",
        help="Save one bounded 3-band EQ setting for explicit later PipeWire "
             "filter staging (NOT a live EQ change). Requires revision preview",
    )
    eq.add_argument("slot", choices=CHANNELS)
    eq.add_argument("band", choices=EQ_BANDS)
    eq.add_argument("db", type=int, help="Integer gain -12..12 dB")
    curve = commands.add_parser(
        "set-eq-curve",
        help="Atomically store one input's three bounded EQ bands (-12..12 dB). "
             "Requires a reviewed preview revision; NOT live PipeWire EQ",
    )
    curve.add_argument("slot", choices=CHANNELS)
    for band in EQ_BANDS:
        curve.add_argument(band, type=int, help="Integer gain -12..12 dB")
    copy_eq = commands.add_parser(
        "copy-eq",
        help="Copy all three saved EQ bands to another fixed input in ONE "
             "guarded local change; does not update running PipeWire filters",
    )
    copy_eq.add_argument("source", choices=CHANNELS)
    copy_eq.add_argument("destination", choices=CHANNELS)
    swap_eq = commands.add_parser(
        "swap-eq",
        help="Exchange two fixed inputs' three saved EQ bands in ONE "
             "revision-guarded local change; NOT a live PipeWire EQ change",
    )
    swap_eq.add_argument("left", choices=CHANNELS)
    swap_eq.add_argument("right", choices=CHANNELS)
    reset_eq = commands.add_parser(
        "reset-eq",
        help="Set one source's three saved EQ bands to 0 dB atomically; "
             "not a live PipeWire EQ change",
    )
    reset_eq.add_argument("slot", choices=CHANNELS)
    sound_eq = commands.add_parser(
        "eq-preset",
        help="Preview or separately confirm a fixed three-band EQ sound profile. "
             "Only private saved settings change; NOT live PipeWire or sound.",
    )
    sound_eq.add_argument("slot", choices=CHANNELS)
    sound_eq.add_argument("name", choices=tuple(EQ_PRESET_CURVES))
    commands.add_parser(
        "mute-all", help="Atomically request mute on all three inputs"
    )
    restore = commands.add_parser(
        "unmute-selected",
        help="Atomically restore one or two explicitly named inputs, never all three",
    )
    restore.add_argument("slots", nargs="+", choices=CHANNELS)
    isolate = commands.add_parser(
        "isolate-input",
        help="Mute both other inputs atomically; selected mute remains unchanged. "
             "Requires reviewed preview revision and separate local confirmation",
    )
    isolate.add_argument("slot", choices=CHANNELS)
    undo_isolation = commands.add_parser(
        "restore-isolation",
        help="Safely restore the other two pre-isolation mutes from a private "
             "baseline, requiring separate preview and exact revision confirmation",
    )
    undo_isolation.add_argument("slot", choices=CHANNELS)
    undo_isolation.add_argument("baseline", help="b1-... snapshot from the original isolation preview")
    preset = commands.add_parser(
        "preset",
        help="Request one conservative named volume preset, without unmuting or changing EQ",
    )
    preset.add_argument("name", choices=tuple(PRESET_VOLUMES))
    commands.add_parser("list-profiles",
                        help="List private custom volume profiles without changing anything")
    commands.add_parser(
        "profile-choices",
        help="Read-only overview of all saved profiles versus current requested levels and mutes",
    )
    save_profile = commands.add_parser(
        "save-profile", help="Store custom volume levels privately; do not apply them")
    save_profile.add_argument("name")
    for field in PROFILE_FIELDS:
        save_profile.add_argument(field, type=int)
    capture = commands.add_parser(
        "save-current-profile",
        help="Preview or capture current requested mixer volumes as a private profile")
    capture.add_argument("name")
    copy = commands.add_parser(
        "copy-profile",
        help="Preview or separately confirm copying a private profile to a new name",
    )
    copy.add_argument("source")
    copy.add_argument("destination")
    compare = commands.add_parser(
        "compare-profiles",
        help="Compare two saved private volume profiles read-only",
    )
    compare.add_argument("left")
    compare.add_argument("right")
    live_compare = commands.add_parser(
        "compare-profile-current",
        help="Read-only compare a saved volume profile with current requested mixer levels",
    )
    live_compare.add_argument("name")
    custom = commands.add_parser(
        "profile", help="Preview or explicitly apply a saved custom volume profile")
    custom.add_argument("name")
    mix = commands.add_parser(
        "set-mix", help="Atomically set master and all three input volumes 0..100"
    )
    mix.add_argument("master", type=int)
    for slot in CHANNELS:
        mix.add_argument(slot, type=int)
    args = parser.parse_args(argv)
    try:
        # Isolation can change two channels. A basic boolean confirmation is
        # intentionally insufficient: require the EXACT reviewed mixer
        # generation to prevent applying an old choice to a newer mix.
        if args.action in (
                "isolate-input", "restore-isolation", "set-eq",
                "copy-eq", "reset-eq", "swap-eq", "set-eq-curve",
                "eq-preset") and (
                args.confirm_local_profile_save
                or args.if_profile_revision is not None
                or (args.action == "restore-isolation"
                    and args.compare_baseline is not None)
                or (args.action in ("swap-eq", "eq-preset") and (
                    args.compare_baseline is not None
                    or args.wait_for_supervisor))
                or (args.preview and (
                    args.confirm_local_mixer_change
                    or args.if_preview_revision is not None
                    or args.wait_for_supervisor))
                or (not args.preview and (
                    not args.confirm_local_mixer_change
                    or args.if_preview_revision is None))):
            raise MixerControlUnavailable(
                "Input isolation/restore needs preview and a separate revision-guarded confirmation")
        if args.action in ("compare-profiles", "compare-profile-current",
                           "profile-choices") and (
                args.preview or args.confirm_local_mixer_change
                or args.confirm_local_profile_save or args.wait_for_supervisor
                or args.if_preview_revision is not None
                or args.if_profile_revision is not None
                or args.compare_baseline is not None):
            raise MixerControlUnavailable("Profile comparison is already read-only")
        if args.if_profile_revision is not None and args.action != "copy-profile":
            raise MixerControlUnavailable("Profile revision is only for copying profiles")
        if args.action == "copy-profile" and (
                args.confirm_local_mixer_change or args.wait_for_supervisor
                or args.compare_baseline is not None
                or args.if_preview_revision is not None
                or (args.preview and (
                    args.confirm_local_profile_save
                    or args.if_profile_revision is not None))
                or (not args.preview and (
                    not args.confirm_local_profile_save
                    or args.if_profile_revision is None))):
            raise MixerControlUnavailable("Profile copy requires preview or separate guarded confirmation")
        if args.confirm_local_profile_save and args.action not in (
                "save-profile", "save-current-profile", "copy-profile"):
            raise MixerControlUnavailable("Private profile save confirmation not applicable")
        if args.action == "save-current-profile" and (
                args.confirm_local_mixer_change or args.wait_for_supervisor
                or args.compare_baseline is not None
                or (args.preview and (
                    args.confirm_local_profile_save
                    or args.if_preview_revision is not None))
                or (not args.preview and (
                    not args.confirm_local_profile_save
                    or args.if_preview_revision is None))):
            raise MixerControlUnavailable("Capture requires preview or confirmed revision")
        if args.action == "save-profile" and (
                args.preview or args.confirm_local_mixer_change
                or args.wait_for_supervisor or args.if_preview_revision is not None
                or args.compare_baseline is not None):
            raise MixerControlUnavailable("Profile save is separate from mixer changes")
        if args.action == "list-profiles" and (
                args.preview or args.confirm_local_mixer_change
                or args.confirm_local_profile_save or args.wait_for_supervisor
                or args.if_preview_revision is not None
                or args.compare_baseline is not None):
            raise MixerControlUnavailable("Profile listing is read-only")
        if args.preview and (args.confirm_local_mixer_change
                             or args.action in ("show", "status", "list-profiles")):
            raise MixerControlUnavailable("Preview is read-only for change commands")
        if args.wait_for_supervisor and (args.preview
                                         or not args.confirm_local_mixer_change
                                         or args.action in ("show", "status")):
            raise MixerControlUnavailable("Supervisor wait requires confirmed change")
        if args.if_preview_revision is not None and args.action != "save-current-profile" and (
                args.preview or not args.confirm_local_mixer_change
                or args.action in ("show", "status")):
            raise MixerControlUnavailable("Preview revision requires confirmed change")
        if args.compare_baseline is not None:
            if (args.action in ("show", "status")
                    or not (args.preview or (
                        args.confirm_local_mixer_change
                        and args.if_preview_revision is not None))):
                raise MixerControlUnavailable("Baseline requires preview or guarded change")
            # Reject malformed snapshots BEFORE a guarded save, never after it.
            _decode_baseline(args.compare_baseline)
        if args.action == "show":
            state = show()
        elif args.action == "status":
            state = application_status()
        elif args.action == "restore-isolation":
            if args.preview:
                state = preview_restore_isolation(args.slot, args.baseline)
            else:
                state = restore_isolation(
                    args.slot, args.baseline,
                    confirmed=args.confirm_local_mixer_change,
                    if_revision=args.if_preview_revision)
        elif args.action == "list-profiles":
            state = list_volume_profiles()
        elif args.action == "profile-choices":
            state = profile_selection_overview()
        elif args.action == "compare-profiles":
            state = compare_volume_profiles(args.left, args.right)
        elif args.action == "compare-profile-current":
            state = compare_profile_to_current(args.name)
        elif args.action == "save-profile":
            state = save_volume_profile(
                args.name, *(getattr(args, key) for key in PROFILE_FIELDS),
                confirmed=args.confirm_local_profile_save)
        elif args.action == "save-current-profile":
            if args.preview:
                state = preview_current_profile(args.name)
            else:
                state = capture_current_profile(
                    args.name, if_revision=args.if_preview_revision,
                    confirmed=args.confirm_local_profile_save)
        elif args.action == "copy-profile":
            if args.preview:
                state = preview_profile_copy(args.source, args.destination)
            else:
                state = copy_volume_profile(
                    args.source, args.destination,
                    if_profile_revision=args.if_profile_revision,
                    confirmed=args.confirm_local_profile_save)
        else:
            if args.action == "set-master":
                patch = {"master": args.percent}
            elif args.action == "set-volume":
                patch = {args.slot: {"volume": args.percent}}
            elif args.action == "set-mix":
                # One validated atomic snapshot prevents partial intermediate
                # levels during a supervised poll; preserve every mute/EQ.
                patch = {"master": args.master}
                patch.update({slot: {"volume": getattr(args, slot)} for slot in CHANNELS})
            elif args.action == "set-eq":
                # This stores a bounded EQ parameter; the running PipeWire
                # filter graph is NOT reconfigured. Stage separately.
                if not -12 <= args.db <= 12:
                    raise MixerControlUnavailable("Local EQ must be -12..12 dB")
                patch = {args.slot: {args.band: args.db}}
            elif args.action == "set-eq-curve":
                # A single guarded private generation avoids three separately
                # confirmed edits (and intermediate incomplete EQ curves).
                values = {band: getattr(args, band) for band in EQ_BANDS}
                if any(type(value) is not int or not -12 <= value <= 12
                       for value in values.values()):
                    raise MixerControlUnavailable("Local EQ must be -12..12 dB")
                patch = {args.slot: values}
            elif args.action == "copy-eq":
                patch, source_revision = copy_input_eq_patch(
                    args.source, args.destination
                )
                if (not args.preview
                        and source_revision != args.if_preview_revision):
                    raise StaleMixerPreview("EQ copy source has changed")
            elif args.action == "swap-eq":
                patch, source_revision = swap_input_eq_patch(
                    args.left, args.right
                )
                if (not args.preview
                        and source_revision != args.if_preview_revision):
                    raise StaleMixerPreview("EQ swap sources have changed")
            elif args.action == "reset-eq":
                patch = reset_input_eq_patch(args.slot)
            elif args.action == "eq-preset":
                # A fixed named sound profile always changes all three saved
                # bands together under the same guarded private transaction.
                # No filter stage, PipeWire process or audible gain is touched.
                patch = eq_preset_patch(args.slot, args.name)
            elif args.action == "isolate-input":
                # The selected source's mute, volume, EQ and routing stay
                # untouched. Never implicitly unmute a source in a lab.
                patch = isolate_input_patch(args.slot)
            elif args.action == "mute-all":
                # One private atomic snapshot, not three independent updates.
                # Preserve master, volume and EQ. Do not auto-unmute later.
                patch = {slot: {"mute": True} for slot in CHANNELS}
            elif args.action == "unmute-selected":
                # No implicit all-input restore; bound to a unique subset of
                # at most two. One settings transaction with no intermediate
                # three-way unmute, preserving other mutes, volumes and EQ.
                if len(args.slots) > 2 or len(args.slots) != len(set(args.slots)):
                    raise MixerControlUnavailable("Select one or two distinct inputs")
                patch = {slot: {"mute": False} for slot in args.slots}
            elif args.action == "preset":
                # Single atomic settings update; only requested master and
                # per-input volumes are changed. Keep mute and EQ intact.
                patch = preset_patch(args.name)
            elif args.action == "profile":
                # Custom profiles are volume-only snapshots in a separate
                # private file, NEVER an automatic mute/EQ or routing change.
                patch = saved_profile_patch(args.name)
            else:
                patch = {args.slot: {"mute": args.value == "on"}}
            if args.preview:
                extras = ({"baseline": args.compare_baseline}
                          if args.compare_baseline is not None else {})
                state = preview_change(patch, **extras)
                if (args.action in ("copy-eq", "swap-eq")
                        and state["revision"] != source_revision):
                    raise MixerControlUnavailable(
                        "EQ source changed during read-only preview"
                    )
                if args.action in ("set-eq-curve", "eq-preset"):
                    state["eq_operation"] = args.action
                    state["target_input"] = args.slot
                    state["eq_staging_separate"] = True
                    if args.action == "eq-preset":
                        state["eq_preset"] = args.name
                        state["preset_curve_db"] = {
                            band: patch[args.slot][band] for band in EQ_BANDS
                        }
                        state["preset_not_calibrated"] = True
                if args.action in ("copy-eq", "reset-eq", "swap-eq"):
                    state["eq_operation"] = args.action
                    state["copy_source"] = (
                        args.source if args.action == "copy-eq" else None
                    )
                    state["target_input"] = (
                        args.destination if args.action == "copy-eq"
                        else args.slot if args.action == "reset-eq" else None
                    )
                    state["swap_inputs"] = (
                        [args.left, args.right] if args.action == "swap-eq" else None
                    )
                    state["eq_staging_separate"] = True
                if args.action == "profile":
                    state["profile_impact"] = _profile_selection_impact(
                        state, args.name)
            else:
                kwargs = ({"if_revision": args.if_preview_revision}
                          if args.if_preview_revision is not None else {})
                state = change(patch, confirmed=args.confirm_local_mixer_change,
                               **kwargs)
                if args.action in ("set-eq", "set-eq-curve", "copy-eq",
                                    "reset-eq", "swap-eq", "eq-preset"):
                    state = {
                        "requested_eq_settings_saved": True,
                        "pipewire_eq_staged": False,
                        "pipewire_eq_live_applied": False,
                        "next_step": "Preview and separately stage EQ in audiohub.eq_setup",
                        "settings": state,
                    }
    except StaleProfilePreview:
        # Failed compare-and-save is a no-op. A new read-only plan requires
        # the operator to review and submit another explicit confirmation.
        try:
            fresh = preview_profile_copy(args.source, args.destination)
        except (MixerControlUnavailable, OSError, ValueError, TypeError):
            parser.exit(4, "Profile not copied: catalog changed. "
                           "Fresh preview unavailable.\n")
        print(json.dumps({
            "status": "profile-copy-stale",
            "profile_written": False, "source_unchanged": True,
            "mixer_settings_written": False, "fresh_preview": fresh,
            "audible_playback_verified": False,
        }, sort_keys=True))
        parser.exit(4, "Profile not copied: review the fresh copy preview "
                       "and separately confirm its new profile revision.\n")
    except StaleMixerPreview:
        if args.action == "swap-eq":
            # A stale EQ exchange must never offer a preview computed using
            # old curve values. Re-snapshot BOTH sides, then verify that the
            # preview is still pinned to the same new generation.
            try:
                fresh_patch, fresh_revision = swap_input_eq_patch(
                    args.left, args.right)
                refreshed = preview_change(fresh_patch)
                if refreshed["revision"] != fresh_revision:
                    raise MixerControlUnavailable("EQ swap changed during refresh")
                refreshed["eq_operation"] = "swap-eq"
                refreshed["swap_inputs"] = [args.left, args.right]
                refreshed["eq_staging_separate"] = True
            except (MixerControlUnavailable, OSError, ValueError, TypeError):
                parser.exit(4, "EQ not swapped: mixer changed. "
                               "Fresh preview unavailable.\n")
            print(json.dumps({
                "status": "eq-swap-stale",
                "settings_written": False,
                "fresh_preview": refreshed,
                "audible_playback_verified": False,
            }, sort_keys=True))
            parser.exit(4, "EQ not swapped: review a fresh preview and "
                           "separately confirm its new revision.\n")
        if args.action == "restore-isolation":
            parser.exit(4, "Isolation mutes not restored: mixer changed. "
                           "Inspect a new read-only preview; no automatic restore.\n")
        if args.action == "save-current-profile":
            # Never auto-capture a later state after a stale revision. The
            # operator must inspect the new read-only snapshot and consent.
            try:
                fresh = preview_current_profile(args.name)
            except (MixerControlUnavailable, OSError, ValueError, TypeError):
                parser.exit(4, "Profile not saved: mixer state changed. "
                               "Fresh preview unavailable.\\n")
            print(json.dumps({
                "status": "profile-capture-stale",
                "profile_written": False, "mixer_settings_written": False,
                "fresh_preview": fresh,
                "audible_playback_verified": False,
            }, sort_keys=True))
            parser.exit(4, "Profile not saved: inspect a fresh capture preview "
                           "and separately confirm its new revision.\\n")
        # The guarded save was rejected UNDER the writer lock. Offer only a
        # fresh read-only projection so the operator can decide again. It is
        # never silently applied, even if a concurrent writer changed state.
        try:
            extras = ({"baseline": args.compare_baseline}
                      if args.compare_baseline is not None else {})
            refreshed = preview_change(patch, **extras)
            if args.action == "profile":
                refreshed["profile_impact"] = _profile_selection_impact(
                    refreshed, args.name)
        except (MixerControlUnavailable, OSError, PermissionError, ValueError, TypeError):
            parser.exit(4, "AudioHub mixer not changed: preview is outdated. "
                           "Fresh preview unavailable; inspect local settings.\n")
        print(json.dumps({
            "status": "preview-stale",
            "settings_written": False,
            "fresh_preview": refreshed,
            "audible_playback_verified": False,
        }, sort_keys=True))
        parser.exit(4, "AudioHub mixer not changed: review the fresh preview "
                       "and explicitly confirm with its new revision.\n")
    except (MixerControlUnavailable, OSError, PermissionError, ValueError) as exc:
        # Local file state must never be echoed on error, including exceptions
        # with filesystem paths or arbitrary untrusted keys.
        parser.exit(2, "AudioHub mixer not changed or unavailable.\n")
    if args.wait_for_supervisor:
        report = wait_for_supervisor(state)
        print(json.dumps(report, sort_keys=True))
        print("Settings saved locally. Only recent complete supervisor command "
              "acceptance is checked; no audible output was measured.")
        if report["delivery_state"] != "accepted":
            parser.exit(3, "Settings saved, but supervisor confirmation not obtained. "
                           "Inspect the local status before any further change.\n")
        return
    print(json.dumps(state, sort_keys=True))
    if args.preview:
        print("Preview only: no settings saved and no PipeWire command applied. "
              "Another local writer may change settings before separate confirmation.")
    elif args.action == "status":
        print("Supervisor acceptance means a recent complete set of PipeWire commands "
              "returned successfully; no hardware audio was measured.")
    elif args.action in ("save-profile", "save-current-profile", "copy-profile"):
        if args.preview:
            print("Read-only private profile preview: no profile or mixer settings saved.")
        else:
            print("Private volume profile saved; active mixer settings unchanged.")
    elif args.action not in ("show", "list-profiles", "compare-profiles",
                              "compare-profile-current", "profile-choices"):
        print("Saved locally; running supervisor applies validated gains on its next poll. "
              "No physical output or audible playback was verified.")


if __name__ == "__main__":
    main()
