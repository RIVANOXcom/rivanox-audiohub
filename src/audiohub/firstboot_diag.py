# SPDX-License-Identifier: AGPL-3.0-only
"""Privacy-bounded, offline Pi first-boot diagnostic for an isolated alpha bench.

Writes only whitelisted aggregate health flags to the removable FAT boot
partition. Not a credential collection, ownership proof, admin API, or
hardware acceptance report. No network/socket/DBus/Bluetooth writes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import secrets
import stat
import time

OUTPUT_DIR = Path("/boot/firmware")
OUTPUT_NAME = "AUDIOHUB-TEST-REPORT.json"
CHECKPOINT_DELAYS = (0, 30, 30, 60, 60, 120, 300)
MAX_RUNTIME_BYTES = 4096
MAX_REPORT_BYTES = 4096
SCHEMA = "rivanox-audiohub-offline-boot-diagnostic/1"


def _bounded(value, upper):
    if type(value) is not int:
        return 0
    return min(max(value, 0), upper)


def _read_runtime(path, user_id):
    """Read bounded, plain, same-UID JSON; never follow a user-controlled link."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != user_id
                or meta.st_nlink != 1 or meta.st_size > MAX_RUNTIME_BYTES):
            return None
        raw = os.read(fd, MAX_RUNTIME_BYTES + 1)
        if len(raw) > MAX_RUNTIME_BYTES:
            return None
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            return None
        return record if type(record) is dict else None
    except OSError:
        return None
    finally:
        os.close(fd)


def sample(runtime_path, user_id, *, now=None, controller_present=False):
    """Strictly non-identifying metrics. Never copy untrusted source strings."""
    now = int(time.time()) if now is None else int(now)
    data = _read_runtime(runtime_path, user_id)
    updated = data.get("updated_at") if data is not None else None
    fresh = (type(updated) is int and 0 <= now - updated <= 90)
    if not fresh:
        return {
            "runtime_status": "unavailable_or_stale",
            "usb_audio_detected": False,
            "usb_audio_route_ready": False,
            "pipewire_links_inspected": 0,
            "eq_usb_direct_links": 0,
            "source_route_policy_valid": False,
            "effective_master_percent": 0,
            "route_start_failures": 0,
            "output_switch_failures": 0,
            "bluetooth_audio_sources": 0,
            "active_audio_routes": 0,
            "virtual_audio_channels": 0,
            "bluetooth_controller_present": bool(controller_present),
        }
    channels = data.get("virtual_channels")
    if type(channels) is not list:
        channels = []
    valid = frozenset(("music", "laptop", "tablet"))
    return {
        "runtime_status": "recent",
        "usb_audio_detected": data.get("usb_output") is True,
        "usb_audio_route_ready": data.get("usb_route_ready") is True,
        "pipewire_links_inspected": _bounded(data.get("pipewire_links_inspected"), 8192),
        "eq_usb_direct_links": len(set(
            slot for slot in (
                data.get("eq_output_usb_direct_links")
                if type(data.get("eq_output_usb_direct_links")) is list else []
            )
            if type(slot) is str and slot in ("music", "laptop", "tablet")
        )),
        "source_route_policy_valid": data.get("route_policy_valid") is True,
        "effective_master_percent": _bounded(data.get("effective_master_percent"), 100),
        "route_start_failures": _bounded(data.get("route_start_failures"), 999),
        "output_switch_failures": _bounded(data.get("output_switch_failures"), 999),
        "bluetooth_audio_sources": _bounded(data.get("bluetooth_source_count"), 2),
        "active_audio_routes": _bounded(data.get("active_routes"), 3),
        "virtual_audio_channels": len(set(
            channel for channel in channels
            if type(channel) is str and channel in valid
        )),
        "bluetooth_controller_present": bool(controller_present),
    }


def write_report(directory, report, *, require_mount=True):
    """Atomic replacement of a small, redacted file on a *mounted* boot FAT.

    False means diagnostics unavailable; never interrupt audio or early boot.
    A removable SD report is an observation, NOT tamper-resistant evidence.
    """
    if require_mount and not os.path.ismount(directory):
        return False
    try:
        raw = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        if len(raw) > MAX_REPORT_BYTES:
            return False
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except (OSError, TypeError, UnicodeError, ValueError):
        return False
    tmp = ".AUDIOHUB-TEST-REPORT-" + secrets.token_hex(8) + ".tmp"
    created = False
    try:
        fd = os.open(
            tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=dirfd,
        )
        created = True
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    return False
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        # rename overwrites a symlink itself, NEVER follows its destination.
        os.replace(tmp, OUTPUT_NAME, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        created = False
        try:
            os.fsync(dirfd)
        except OSError:
            # Some FAT mount combinations cannot fsync directories.
            pass
        return True
    except OSError:
        return False
    finally:
        if created:
            try:
                os.unlink(tmp, dir_fd=dirfd)
            except OSError:
                pass
        os.close(dirfd)


def run_probe(*, sleep=time.sleep, now=time.time, mono=time.monotonic,
              output_dir=OUTPUT_DIR, runtime_path=None, user_id=None,
              controller_path=Path("/sys/class/bluetooth/hci0"),
              require_mount=True):
    """Collect seven bounded snapshots in the first ten minutes after launch."""
    if user_id is None:
        try:
            user_id = pwd.getpwnam("audiohub").pw_uid
        except KeyError:
            return False
    if runtime_path is None:
        runtime_path = Path("/run/user") / str(user_id) / "audiohub/runtime-status.json"
    beginning = mono()
    report = {
        "schema": SCHEMA,
        "classification": "UNVERIFIED_ALPHA_OFFLINE_TEST_ONLY",
        "hardware_accepted": False,
        "owner_authenticated": False,
        "phone_wifi_provisioned": False,
        "network_configuration": "not_inspected",
        "snapshots": [],
    }
    wrote = False
    for delay in CHECKPOINT_DELAYS:
        sleep(delay)
        metrics = sample(
            runtime_path, user_id, now=now(),
            controller_present=controller_path.exists(),
        )
        report["snapshots"].append({
            "seconds_since_probe_start": _bounded(round(mono() - beginning), 3600),
            **metrics,
        })
        # A partial report remains useful even if the Pi is switched off.
        wrote = write_report(output_dir, report, require_mount=require_mount) or wrote
    return wrote


def main():
    # Noncritical alpha diagnostics: never make a failed report block playback.
    try:
        run_probe()
    except (OSError, ValueError, TypeError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
