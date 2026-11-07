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
import time

from .mixer import CHANNELS, defaults, patch_settings, requested_mix_controls
from .runtime import SETTINGS, STATE, _private_parent_fd, read_json, atomic_json

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


def preview_change(patch, *, path=SETTINGS):
    """Show a validated prospective request; no lock, write, or audio action.

    A preview is a snapshot rather than a reservation: another local writer
    may save different settings before an independently confirmed action.
    Return only known volume/mute fields, never private routes or IDs.
    """
    try:
        current = show(path=path)
        before = requested_mix_controls(current)
        after = requested_mix_controls(patch_settings(current, patch))
    except (TypeError, ValueError):
        raise MixerControlUnavailable("Invalid mixer preview setting") from None
    changes = []
    if before["master"] != after["master"]:
        changes.append("master")
    for slot in CHANNELS:
        for field in ("volume", "mute"):
            if before[slot][field] != after[slot][field]:
                changes.append(slot + "." + field)
    return {
        "mode": "preview-only",
        "before": before,
        "after": after,
        "would_change": changes,
        "settings_written": False,
        "supervisor_applied": False,
        "audible_playback_verified": False,
    }


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
    parser.add_argument("--preview", action="store_true",
                        help="Show requested changes without writing any settings")
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
    commands.add_parser(
        "mute-all", help="Atomically request mute on all three inputs"
    )
    restore = commands.add_parser(
        "unmute-selected",
        help="Atomically restore one or two explicitly named inputs, never all three",
    )
    restore.add_argument("slots", nargs="+", choices=CHANNELS)
    mix = commands.add_parser(
        "set-mix", help="Atomically set master and all three input volumes 0..100"
    )
    mix.add_argument("master", type=int)
    for slot in CHANNELS:
        mix.add_argument(slot, type=int)
    args = parser.parse_args(argv)
    try:
        if args.preview and (args.confirm_local_mixer_change
                             or args.action in ("show", "status")):
            raise MixerControlUnavailable("Preview is read-only for change commands")
        if args.wait_for_supervisor and (args.preview
                                         or not args.confirm_local_mixer_change
                                         or args.action in ("show", "status")):
            raise MixerControlUnavailable("Supervisor wait requires confirmed change")
        if args.action == "show":
            state = show()
        elif args.action == "status":
            state = application_status()
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
            else:
                patch = {args.slot: {"mute": args.value == "on"}}
            if args.preview:
                state = preview_change(patch)
            else:
                state = change(patch, confirmed=args.confirm_local_mixer_change)
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
    elif args.action != "show":
        print("Saved locally; running supervisor applies validated gains on its next poll. "
              "No physical output or audible playback was verified.")


if __name__ == "__main__":
    main()
