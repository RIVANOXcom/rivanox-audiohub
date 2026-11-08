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
    parser.add_argument("--confirm-local-eq-stage", action="store_true")
    parser.add_argument("--if-preview-revision", metavar="REV")
    args = parser.parse_args(argv)
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
    else:
        if args.confirm_local_eq_stage or args.if_preview_revision is not None:
            parser.error("EQ stage options require --stage-saved")
        _write_eq_payload(pipewire_filter_config(defaults()).encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv[1:])
