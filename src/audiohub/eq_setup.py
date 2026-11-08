# SPDX-License-Identifier: AGPL-3.0-only
"""Safely install the three unprivileged PipeWire EQ filters.

This startup utility must not follow a user-controlled symlink when
replacing the local EQ configuration. No network or elevated rights.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
import sys

from .mixer import CHANNELS, EQ_BANDS, defaults, pipewire_filter_config
from .runtime import SETTINGS, _private_parent_fd
from . import mixer_control

MAX_EQ_CONFIG_BYTES = 64 * 1024
EQ_FILE = "90-audiohub-eq.conf"


def _safe_eq_parent_fd(target):
    """Create and open the final user-private directory without symlinks."""
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError("Unsafe PipeWire EQ path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for component in target.parent.parts[1:]:
            try:
                nextfd = os.open(component, flags, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    # Another local instance may create the directory first.
                    # Reopen with O_NOFOLLOW; a raced symlink is still denied.
                    pass
                nextfd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = nextfd
        st = os.fstat(fd)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077):
            raise PermissionError("PipeWire EQ directory must be private")
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def _write_eq_payload(payload):
    if not 0 < len(payload) <= MAX_EQ_CONFIG_BYTES:
        raise ValueError("PipeWire EQ configuration exceeds storage bound")
    target = Path.home() / ".config" / "pipewire" / "pipewire.conf.d" / EQ_FILE
    dirfd = _safe_eq_parent_fd(target)
    temp = "." + target.name + "." + secrets.token_hex(12) + ".tmp"
    created = False
    try:
        try:
            prior = os.stat(target.name, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError:
            prior = None
        # Do not overwrite a symlink, FIFO, hardlink or another user's file.
        if prior is not None and (
                not stat.S_ISREG(prior.st_mode) or prior.st_uid != os.geteuid()
                or prior.st_nlink != 1 or stat.S_IMODE(prior.st_mode) & 0o077):
            raise PermissionError("Unsafe existing PipeWire EQ configuration")
        out = os.open(
            temp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=dirfd,
        )
        created = True
        try:
            os.fchmod(out, 0o600)
            position = 0
            while position < len(payload):
                written = os.write(out, payload[position:])
                if written <= 0:
                    raise OSError("Incomplete PipeWire EQ configuration write")
                position += written
            os.fsync(out)
        finally:
            os.close(out)
        os.replace(temp, target.name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        created = False
        os.fsync(dirfd)
    finally:
        try:
            if created:
                try:
                    os.unlink(temp, dir_fd=dirfd)
                except OSError:
                    # Preserve the original write error even if cleanup fails.
                    pass
        finally:
            os.close(dirfd)


def _saved_eq_report(settings, revision, payload, *, staged):
    """Fixed-schema local summary; no device IDs, user labels or raw files."""
    return {
        "mode": "eq-staged-for-manual-pipewire-restart" if staged else "eq-preview-only",
        "revision": revision,
        "equalizer": {
            slot: {band: settings[slot][band] for band in EQ_BANDS}
            for slot in CHANNELS
        },
        "configuration_sha256": hashlib.sha256(payload).hexdigest(),
        "configuration_staged": staged,
        "pipewire_restarted": False,
        "live_eq_applied": False,
        "hardware_audio_verified": False,
    }


def preview_saved_eq():
    """Show exact saved EQ parameters and candidate config without writing."""
    state, revision = mixer_control._preview_snapshot(path=SETTINGS)
    payload = pipewire_filter_config(state).encode("utf-8")
    if not 0 < len(payload) <= MAX_EQ_CONFIG_BYTES:
        raise ValueError("PipeWire EQ configuration exceeds storage bound")
    return _saved_eq_report(state, revision, payload, staged=False)


def _staged_eq_digest():
    """Read ONLY a private bounded stage file; never create paths or links.

    Return a conservative state and digest, not any device path or file body.
    An unsafe or changing destination cannot be presented as a valid stage.
    """
    target = Path.home() / ".config" / "pipewire" / "pipewire.conf.d" / EQ_FILE
    dirfd = filefd = None
    try:
        dirfd = _private_parent_fd(target, create=False)
        filefd = os.open(
            target.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            | os.O_CLOEXEC, dir_fd=dirfd,
        )
        before = os.fstat(filefd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o077
                or not 0 < before.st_size <= MAX_EQ_CONFIG_BYTES):
            return "unavailable", None
        content = os.read(filefd, MAX_EQ_CONFIG_BYTES + 1)
        after = os.fstat(filefd)
        entry = os.stat(target.name, dir_fd=dirfd, follow_symlinks=False)
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_size,
                    st.st_mtime_ns, st.st_ctime_ns)
        if (len(content) != before.st_size
                or identity(before) != identity(after)
                or identity(after) != identity(entry)):
            return "unavailable", None
        return "available", hashlib.sha256(content).hexdigest()
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError, TypeError):
        return "unavailable", None
    finally:
        if filefd is not None:
            os.close(filefd)
        if dirfd is not None:
            os.close(dirfd)


def compare_staged_eq(*, include_gain_headroom=False):
    """Read-only requested-versus-staged EQ config check, never live audio.

    Read two stable mixer generations around the stage-file inspection;
    refuse a mismatched generation rather than comparing unrelated states.
    A matching file digest is NOT evidence that PipeWire loaded that file.
    """
    state, revision = mixer_control._preview_snapshot(path=SETTINGS)
    payload = pipewire_filter_config(state).encode("utf-8")
    if not 0 < len(payload) <= MAX_EQ_CONFIG_BYTES:
        raise ValueError("PipeWire EQ configuration exceeds storage bound")
    expected_digest = hashlib.sha256(payload).hexdigest()
    file_state, actual_digest = _staged_eq_digest()
    _, second_revision = mixer_control._preview_snapshot(path=SETTINGS)
    if revision != second_revision:
        raise mixer_control.MixerControlUnavailable(
            "Mixer changed during staged EQ comparison")
    status = (
        "missing" if file_state == "missing" else
        "unavailable" if file_state != "available" else
        "matches_saved" if actual_digest == expected_digest else
        "differs_from_saved"
    )
    report = {
        "mode": "read-only-saved-vs-staged-eq",
        "revision": revision,
        "equalizer": {
            slot: {band: state[slot][band] for band in EQ_BANDS}
            for slot in CHANNELS
        },
        "saved_configuration_sha256": expected_digest,
        "staged_configuration_sha256": actual_digest,
        "staging_status": status,
        "configuration_staged_for_saved_eq": status == "matches_saved",
        "settings_written": False,
        "configuration_written": False,
        "pipewire_restarted": False,
        "live_eq_applied": False,
        "hardware_audio_verified": False,
    }
    # Existing stable JSON report stays strictly backward compatible.
    # Only the explicitly human-readable overview requests this extra
    # calculation, derived from the SAME revision-checked mixer state.
    if include_gain_headroom is True:
        report["gain_headroom"] = mixer_control.gain_headroom_projection(state)
    return report


def format_staged_eq_text(report):
    """Plain operator guidance from fixed, locally validated EQ comparison.

    Never print file contents, arbitrary paths, device IDs, or suggest that a
    matching on-disk stage proves PipeWire loaded its configuration.
    """
    explanations = {
        "matches_saved": (
            "Saved EQ matches the existing staged configuration.",
            "A match does not prove PipeWire loaded the stage. A separately "
            "authorized lab reload and actual audible check remain necessary.",
        ),
        "differs_from_saved": (
            "Saved EQ differs from the existing staged configuration.",
            "Next: review python3 -m audiohub.eq_setup --preview-saved; "
            "stage only after separate local consent and fresh revision.",
        ),
        "missing": (
            "No staged EQ configuration was found.",
            "Next: review python3 -m audiohub.eq_setup --preview-saved; "
            "stage only after separate local consent and fresh revision.",
        ),
        "unavailable": (
            "Staged EQ could not be safely inspected.",
            "Next: inspect file ownership and privacy locally. No automatic "
            "repair, staging, or PipeWire reload is performed.",
        ),
    }
    status = report["staging_status"]
    if status not in explanations:
        raise ValueError("Unknown staged EQ status")
    lines = ["AudioHub EQ – saved versus staged (read-only)",
             "Stage: " + status.replace("_", " ")]
    lines.extend(explanations[status][:1])
    lines.append("Saved requests (not verified live audio):")
    for slot in CHANNELS:
        values = report["equalizer"][slot]
        bands = ", ".join(
            f"{band} {values[band]:+d} dB" for band in EQ_BANDS
        )
        lines.append(f"  {slot}: {bands}")
    lines.append(explanations[status][1])
    lines.append("No files written, no PipeWire restart, no audible output verified.")
    return "\n".join(lines)


def _saved_eq_profile_shape(curve):
    """Classify a bounded on-disk EQ curve, never infer the selected preset.

    A gain triple matching a shipped preset does NOT prove the operator
    selected that preset, that the stage is current, or that sound is audible.
    """
    if (type(curve) is not dict or set(curve) != set(EQ_BANDS)
            or any(type(curve[band]) is not int or
                   not -12 <= curve[band] <= 12 for band in EQ_BANDS)):
        raise ValueError("Invalid saved EQ values")
    values = tuple(curve[band] for band in EQ_BANDS)
    if values == (0, 0, 0):
        return "Flat"
    for name, profile in mixer_control.EQ_PRESET_CURVES.items():
        if values == profile:
            return name.capitalize()
    return "Custom"


def format_staged_eq_overview(report):
    """Readable one-stop local view of saved curves and global stage state.

    Reuses the existing safe, stable-generation stage comparison report:
    NEVER re-read private files for names, never fetch live PipeWire state,
    never call staging, never imply per-input stage verification.
    """
    explanations = {
        "matches_saved": (
            "MATCHES saved configuration (entire staged file digest)",
            "No separate staging needed for these saved values. "
            "PipeWire load and audible output are STILL UNVERIFIED.",
        ),
        "differs_from_saved": (
            "DIFFERS from saved configuration (entire staged file digest)",
            "The disk stage may be out of date. Review --preview-saved "
            "and separately approve a fresh revision before staging.",
        ),
        "missing": (
            "MISSING staged configuration file",
            "Review --preview-saved first. Staging requires a separately "
            "approved exact mixer revision; nothing is repaired here.",
        ),
        "unavailable": (
            "UNAVAILABLE / UNSAFE stage inspection",
            "Check local ownership and private file safety. No automatic "
            "repair, staging or PipeWire restart.",
        ),
    }
    if type(report) is not dict or report.get("staging_status") not in explanations:
        raise ValueError("Invalid staged EQ overview status")
    equalizer = report.get("equalizer")
    if type(equalizer) is not dict or set(equalizer) != set(CHANNELS):
        raise ValueError("Invalid saved EQ overview inputs")
    # Validate everything before constructing a possibly misleading partial
    # overview. The returned 'shape' is not claimed as a selected preset.
    rows = []
    for slot in CHANNELS:
        curve = equalizer[slot]
        shape = _saved_eq_profile_shape(curve)
        gains = "  ".join(f"{band} {curve[band]:+d} dB" for band in EQ_BANDS)
        rows.append(f"  {slot:<7} {shape:<7} (shape match) | {gains}")
    status, guidance = explanations[report["staging_status"]]
    gain = report.get("gain_headroom")
    if gain is not None:
        if type(gain) is not dict:
            raise ValueError("Invalid headroom projection")
        master = gain.get("requested_master_percent")
        factor = gain.get("conservative_mix_factor_percent")
        projected = gain.get("projected_master_percent")
        unmuted = gain.get("unmuted_sources")
        if (type(master) is not int or not 0 <= master <= 100
                or type(factor) not in (int, float)
                or not math.isfinite(factor) or not 0 <= factor <= 100
                or type(projected) not in (int, float)
                or not math.isfinite(projected) or not 0 <= projected <= 100
                or type(unmuted) is not list
                or len(unmuted) > len(CHANNELS)
                or len(set(slot for slot in unmuted
                           if type(slot) is str)) != len(unmuted)
                or not all(type(slot) is str and slot in CHANNELS
                           for slot in unmuted)):
            raise ValueError("Invalid headroom projection")
        gain_lines = [
            "REQUESTED MIX HEADROOM (calculated, NOT verified live output):",
            "  Requested master: " +
                str(gain["requested_master_percent"]) + "%",
            "  Unmuted inputs: " +
                (", ".join(gain["unmuted_sources"]) or "none"),
            "  Conservative mix factor: " +
                f'{gain["conservative_mix_factor_percent"]:.2f}%',
            "  Projected capped master: " +
                f'{gain["projected_master_percent"]:.2f}%',
            "  A lower projected master can result from EQ boosts or "
            "simultaneous sources; this does not prove actual volume.",
            "  This estimate is NOT a look-ahead limiter or peak test.",
        ]
    else:
        gain_lines = []
    return "\n".join([
        "AudioHub EQ overview — Pi-local, read-only",
        "SAVED EQ (not necessarily staged or audible):",
        *rows,
        "A named shape match is not proof of preset selection or calibration.",
        *gain_lines,
        "ON-DISK STAGE: " + status,
        guidance,
        "Stage comparison covers ALL three inputs as one file, "
        "not independent per-input live filters.",
        "No mixer settings written, no stage changed, no PipeWire restart.",
        "NOT VERIFIED: current PipeWire load, active EQ, audible speakers.",
    ])


def stage_saved_eq(revision, *, confirmed=False):
    """Only stage a checked mixer generation; never restart PipeWire.

    Hold the existing mixer writer lock across input snapshot and EQ config
    file replacement. Concurrent settings updates cannot slip between them.
    This does not guarantee sound continuity or authorize a service restart.
    """
    if confirmed is not True or os.geteuid() == 0:
        raise PermissionError("Unprivileged explicit local EQ stage confirmation required")
    if (type(revision) is not str or len(revision) != 67
            or not revision.startswith("v1-")
            or any(ch not in "0123456789abcdef" for ch in revision[3:])):
        raise ValueError("Invalid EQ staging preview revision")
    dirfd = _private_parent_fd(SETTINGS, create=False)
    lockfd = None
    try:
        lockfd = os.open(
            mixer_control.LOCK_NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=dirfd,
        )
        st = os.fstat(lockfd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077):
            raise PermissionError("Unsafe private mixer settings lock")
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        state, current_revision = mixer_control._state_with_revision(SETTINGS, dirfd)
        if current_revision != revision:
            raise ValueError("Mixer changed since EQ preview; EQ not staged")
        payload = pipewire_filter_config(state).encode("utf-8")
        _write_eq_payload(payload)
        return _saved_eq_report(state, revision, payload, staged=True)
    finally:
        if lockfd is not None:
            os.close(lockfd)
        os.close(dirfd)


def main(argv=()):
    # Bare invocation remains the original Pi image-build default installer.
    # Only explicitly requested local options read or stage private settings.
    parser = argparse.ArgumentParser(
        description="Local PipeWire EQ configuration; never a live EQ update"
    )
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--preview-saved", action="store_true",
                        help="Preview stored three-band EQ and config digest without writing")
    choice.add_argument("--stage-saved", action="store_true",
                        help="Stage saved EQ config only after reviewed revision and consent")
    choice.add_argument("--compare-staged", action="store_true",
                        help="Read-only compare saved EQ to actual staged config; NOT live audio")
    parser.add_argument("--confirm-local-eq-stage", action="store_true")
    parser.add_argument("--if-preview-revision", metavar="REV")
    parser.add_argument("--format", choices=("json", "text", "overview"),
                        default=None,
                        help="Only with --compare-staged; default JSON remains unchanged")
    args = parser.parse_args(argv)
    if args.format is not None and not args.compare_staged:
        parser.error("--format requires --compare-staged")
    if args.stage_saved:
        if not args.confirm_local_eq_stage or args.if_preview_revision is None:
            parser.error("EQ staging requires explicit confirmation and exact preview revision")
        try:
            output = stage_saved_eq(
                args.if_preview_revision, confirmed=True
            )
        except (OSError, PermissionError, ValueError, mixer_control.MixerControlUnavailable):
            parser.exit(2, "AudioHub local EQ was not staged; recheck private settings.\n")
        print(json.dumps(output, sort_keys=True))
    elif args.preview_saved:
        if args.confirm_local_eq_stage or args.if_preview_revision is not None:
            parser.error("EQ preview cannot confirm or stage changes")
        try:
            output = preview_saved_eq()
        except (OSError, PermissionError, ValueError, mixer_control.MixerControlUnavailable):
            parser.exit(2, "AudioHub local EQ preview unavailable.\n")
        print(json.dumps(output, sort_keys=True))
    elif args.compare_staged:
        if args.confirm_local_eq_stage or args.if_preview_revision is not None:
            parser.error("EQ comparison is read-only; staging flags not allowed")
        try:
            output = (compare_staged_eq(include_gain_headroom=True)
                      if args.format == "overview" else compare_staged_eq())
        except (OSError, PermissionError, ValueError, mixer_control.MixerControlUnavailable):
            parser.exit(2, "AudioHub local staged EQ comparison unavailable.\\n")
        if args.format == "text":
            print(format_staged_eq_text(output))
        elif args.format == "overview":
            print(format_staged_eq_overview(output))
        else:
            print(json.dumps(output, sort_keys=True))
    else:
        if args.confirm_local_eq_stage or args.if_preview_revision is not None:
            parser.error("EQ stage options require --stage-saved")
        _write_eq_payload(pipewire_filter_config(defaults()).encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv[1:])
