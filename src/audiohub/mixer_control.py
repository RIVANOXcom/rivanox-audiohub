# SPDX-License-Identifier: AGPL-3.0-only
"""Unprivileged offline controls for live AudioHub volume and mute settings.

This CLI creates no HTTP API, network listener, Bluetooth trust, audio
process or EQ rewrite. The existing supervisor reads the atomically updated
private settings on its next poll and applies conservative gain attenuation.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import stat

from .mixer import CHANNELS, defaults, patch_settings
from .runtime import SETTINGS, _private_parent_fd, read_json, atomic_json

LOCK_NAME = ".mixer-settings.lock"


class MixerControlUnavailable(RuntimeError):
    """Sanitized local status; never echo untrusted private file contents."""


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


def change(patch, *, path=SETTINGS, confirmed=False):
    """Apply one bounded, atomic user-requested control patch.

    Lock serializes concurrent *CLI writers*. The running supervisor reads
    each atomic snapshot (old or new) and applies the controls on a future
    poll. No arbitrary source, device ID or gain command is accepted.
    """
    if confirmed is not True:
        raise MixerControlUnavailable("Explicit local mixer change confirmation required")
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
        current = _existing_state(path, dirfd)
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline-only AudioHub levels and mute, not a remote mixer API"
    )
    parser.add_argument("--confirm-local-mixer-change", action="store_true",
                        help="Explicitly approve an atomic local settings update")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("show", help="Read-only current private mixer controls")
    master = commands.add_parser("set-master", help="Set master requested volume 0..100")
    master.add_argument("percent", type=int)
    channel = commands.add_parser("set-volume", help="Set a channel volume 0..100")
    channel.add_argument("slot", choices=CHANNELS)
    channel.add_argument("percent", type=int)
    mute = commands.add_parser("mute", help="Set a channel mute (on/off)")
    mute.add_argument("slot", choices=CHANNELS)
    mute.add_argument("value", choices=("on", "off"))
    args = parser.parse_args(argv)
    try:
        if args.action == "show":
            state = show()
        else:
            if args.action == "set-master":
                patch = {"master": args.percent}
            elif args.action == "set-volume":
                patch = {args.slot: {"volume": args.percent}}
            else:
                patch = {args.slot: {"mute": args.value == "on"}}
            state = change(patch, confirmed=args.confirm_local_mixer_change)
    except (MixerControlUnavailable, OSError, PermissionError, ValueError) as exc:
        # Local file state must never be echoed on error, including exceptions
        # with filesystem paths or arbitrary untrusted keys.
        parser.exit(2, "AudioHub mixer not changed or unavailable.\n")
    print(json.dumps(state, sort_keys=True))
    if args.action != "show":
        print("Saved locally; running supervisor applies validated gains on its next poll. "
              "No physical output or audible playback was verified.")


if __name__ == "__main__":
    main()
