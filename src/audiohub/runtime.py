# SPDX-License-Identifier: AGPL-3.0-only
"""Headless Bluetooth -> per-source EQ -> selected USB speaker supervisor.

Source-level safety and recovery model. Actual Pi4 + Edifier sound and
multi-device A2DP feasibility are NOT proven without physical acceptance.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
import subprocess
import time
from pathlib import Path

from .discovery import bluetooth_sources, choose_usb_output, pipewire_nodes, virtual_sinks
from .audio_graph import summarize_links
from .mixer import CHANNELS, defaults, effective_master_gain, patch_settings, volume_commands
from .source_routes import defaults as default_routes, load as load_routes

CONFIG = Path.home() / ".config" / "audiohub"
SETTINGS = CONFIG / "settings.json"
ASSIGNMENTS = CONFIG / "device-channels.json"
STATE = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "audiohub" / "runtime-status.json"

MAX_BT_INPUTS = 2
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 60
MAX_COUNTER = 999
# A source name can only come from a PipeWire Bluetooth source node, never
# free-form user input. Always pass it as a separate argv entry, not a shell.
_SOURCE_NAME = re.compile(r"bluez_input\.[a-zA-Z0-9_.:-]{1,100}\Z")
_BLUETOOTH_MAC = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")


def run(*args, timeout=8):
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None



MAX_RUNTIME_JSON_BYTES = 32 * 1024


def _private_parent_fd(path, *, create=False):
    """Walk absolute parent directories with nofollow at every component.

    The final storage directory must belong to the current unprivileged
    audiohub user and be private (no group/other access). Intermediate
    directories may be system-owned; never follow their symlinks.
    """
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("AudioHub state path must be an absolute safe path")
    parent = path.parent
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in parent.parts[1:]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=fd)
                next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if (info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise PermissionError("AudioHub storage directory must be user-owned and private")
        result = fd
        fd = None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def read_json(path, fallback):
    """Read only one bounded, private regular JSON file, never symlinks."""
    dirfd = None
    filefd = None
    try:
        path = Path(path)
        dirfd = _private_parent_fd(path)
        filefd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            | os.O_CLOEXEC, dir_fd=dirfd
        )
        st = os.fstat(filefd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077
                or not 0 < st.st_size <= MAX_RUNTIME_JSON_BYTES):
            return fallback
        raw = os.read(filefd, MAX_RUNTIME_JSON_BYTES + 1)
        if len(raw) != st.st_size:
            return fallback
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, type(fallback)) else fallback
    except (OSError, ValueError, TypeError, UnicodeError):
        return fallback
    finally:
        if filefd is not None:
            os.close(filefd)
        if dirfd is not None:
            os.close(dirfd)


def atomic_json(path, data):
    """Atomically write private state without predictable .tmp or symlinks.

    A pre-existing symlink/nonregular/hardlinked destination is not silently
    repaired. Writes use random exclusive temp names in an open directory
    FD; the file and directory are fsynced before returning success.
    """
    path = Path(path)
    raw = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False)
           + "\n").encode("utf-8")
    if not 0 < len(raw) <= MAX_RUNTIME_JSON_BYTES:
        raise ValueError("AudioHub state exceeds private storage limit")
    dirfd = _private_parent_fd(path, create=True)
    name = "." + path.name + "." + secrets.token_hex(12) + ".tmp"
    tmpfd = None
    try:
        try:
            prior = os.stat(path.name, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError:
            prior = None
        if prior is not None and (
                not stat.S_ISREG(prior.st_mode) or prior.st_nlink != 1
                or prior.st_uid != os.geteuid()
                or stat.S_IMODE(prior.st_mode) & 0o077):
            raise PermissionError("Unsafe existing AudioHub state destination")
        tmpfd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | os.O_CLOEXEC, 0o600, dir_fd=dirfd
        )
        # A restrictive process umask must not leave an unreadable state file.
        os.fchmod(tmpfd, 0o600)
        with os.fdopen(tmpfd, "wb") as stream:
            tmpfd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path.name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        os.fsync(dirfd)
    finally:
        if tmpfd is not None:
            os.close(tmpfd)
        try:
            os.unlink(name, dir_fd=dirfd)
        except FileNotFoundError:
            pass
        os.close(dirfd)


def backoff_seconds(failures):
    """Exponential restart cap; repeated stream failures must not hot-loop."""
    return min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** min(max(failures - 1, 0), 4)))


def pipewire_loopback_args(source, channel):
    """Explicit capture source and EQ playback target, never a default sink."""
    if (type(source) is not str or _SOURCE_NAME.fullmatch(source) is None
            or channel not in CHANNELS):
        raise ValueError("Unsupported Bluetooth capture or audio channel")
    return [
        "pw-loopback", "--name", "audiohub-" + channel,
        "--channels", "2", "--capture", source,
        "--playback", "audiohub." + channel,
    ]


class Supervisor:
    def __init__(self):
        CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.settings = patch_settings(defaults(), read_json(SETTINGS, {}))
        self.assignments = read_json(ASSIGNMENTS, {})
        self.loopbacks = {}
        self.retry_state = {}
        self.route_failures_total = 0
        self.output_switch_failures = 0
        self.last_default = None
        self.route_plan = default_routes()
        self.route_policy_valid = True

    def _assign(self, sources):
        """Bind Bluetooth only to permitted, non-LAN-reserved mixer slots.

        Auto mode retains legacy stable assignments but never uses the
        configured LAN input slot; manual mode admits only the explicitly
        listed BT MACs. This source allowlist is NOT cryptographic pairing
        or a replacement for owner authentication.
        """
        plan = getattr(self, "route_plan", default_routes())
        lan = plan["lan_slot"]
        allowed = tuple(slot for slot in CHANNELS if slot != lan)
        if plan["mode"] == "manual":
            self.assignments = dict(plan["bluetooth"])
            return
        self.assignments = {
            address: channel
            for address, channel in self.assignments.items()
            if type(address) is str and _BLUETOOTH_MAC.fullmatch(address)
            and channel in allowed
        }
        unique = {}
        assigned = set()
        for address, channel in sorted(self.assignments.items()):
            if channel not in assigned:
                unique[address] = channel
                assigned.add(channel)
        changed = unique != self.assignments
        self.assignments = unique
        for source in sources:
            address = source.get("address")
            if (type(address) is not str or _BLUETOOTH_MAC.fullmatch(address) is None
                    or address in self.assignments):
                continue
            for channel in allowed:
                if channel not in assigned:
                    self.assignments[address] = channel
                    assigned.add(channel)
                    changed = True
                    break
        if changed:
            atomic_json(ASSIGNMENTS, self.assignments)

    def _retry_after_failure(self, address, identity, now):
        retries = getattr(self, "retry_state", {})
        previous = retries.get(address)
        failures = previous[2] + 1 if previous and previous[0] == identity else 1
        retries[address] = (identity, now + backoff_seconds(failures), failures)
        self.retry_state = retries
        self.route_failures_total = min(
            MAX_COUNTER, getattr(self, "route_failures_total", 0) + 1
        )

    @staticmethod
    def _stop_process(process):
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def _stop_all_managed_routes(self):
        """Never leave managed PipeWire players running after a failed poll.

        A cleanup failure escalates to systemd, whose control-group shutdown
        must kill any remaining subprocesses; no Bluetooth addresses or
        source/node identifiers are included in the failure message.
        """
        errors = 0
        for address, (_, _, process) in list(self.loopbacks.items()):
            try:
                self._stop_process(process)
            except Exception:
                errors += 1
            finally:
                self.loopbacks.pop(address, None)
        retries = getattr(self, "retry_state", None)
        if isinstance(retries, dict):
            retries.clear()
        if errors:
            raise RuntimeError("Managed AudioHub routing cleanup failed")

    def poll_safely(self):
        """One supervised cycle; unexpected errors stop every active route."""
        try:
            self.poll()
        except Exception:
            self._stop_all_managed_routes()
            return False
        return True

    def _route(self, sources, sinks, *, now=None):
        """Route up to two Bluetooth inputs; pause all routes without USB.

        A dead pw-loopback is retried with capped exponential backoff, rather
        than spawning a new process on each 5-second poll indefinitely.
        """
        now = time.monotonic() if now is None else now
        self._assign(sources)
        desired = {}
        for source in sources:
            address = source.get("address")
            name = source.get("name")
            channel = self.assignments.get(address)
            target = "audiohub." + channel if channel else None
            if (type(address) is str and _BLUETOOTH_MAC.fullmatch(address)
                    and type(name) is str and _SOURCE_NAME.fullmatch(name)
                    and channel in CHANNELS and channel != getattr(self, "route_plan", default_routes())["lan_slot"] and target in sinks
                    and address not in desired and len(desired) < MAX_BT_INPUTS):
                desired[address] = (name, target)

        retries = getattr(self, "retry_state", {})
        for address, (old_source, old_target, process) in list(self.loopbacks.items()):
            expected = desired.get(address)
            running = process.poll() is None
            if expected == (old_source, old_target) and running:
                retries.pop(address, None)
                continue
            if running:
                self._stop_process(process)
            else:
                if expected == (old_source, old_target):
                    self._retry_after_failure(address, expected, now)
            del self.loopbacks[address]
            if expected != (old_source, old_target):
                retries.pop(address, None)
        for address in list(retries):
            if address not in desired:
                del retries[address]

        for address, identity in desired.items():
            if address in self.loopbacks:
                continue
            previous = retries.get(address)
            if previous and previous[0] == identity and now < previous[1]:
                continue
            if previous and previous[0] != identity:
                retries.pop(address, None)
            name, target = identity
            channel = target.removeprefix("audiohub.")
            try:
                process = subprocess.Popen(
                    pipewire_loopback_args(name, channel),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.loopbacks[address] = (name, target, process)
            except (OSError, ValueError):
                self._retry_after_failure(address, identity, now)

    def poll(self):
        """Reassert the USB default each poll before admitting audio routes."""
        result = run("pw-dump")
        nodes = pipewire_nodes(result.stdout) if result and result.returncode == 0 else []
        graph_links = summarize_links(result.stdout if result and result.returncode == 0 else None)
        output = choose_usb_output(nodes)
        output_id = output.get("id") if output else None
        if type(output_id) is not int or output_id < 0:
            output_id = None
        # A successful selection is required on EVERY poll. Otherwise EQ
        # output auto-linking could silently switch to HDMI/another sink.
        selected = run("wpctl", "set-default", str(output_id)) if output_id is not None else None
        usb_ready = bool(selected and selected.returncode == 0)
        if not usb_ready and output_id is not None:
            self.output_switch_failures = min(
                MAX_COUNTER, getattr(self, "output_switch_failures", 0) + 1
            )
        self.last_default = output_id if usb_ready else None

        sources = bluetooth_sources(nodes)
        sinks = virtual_sinks(nodes)
        try:
            plan = load_routes(CONFIG)
            self.route_policy_valid = True
        except (OSError, ValueError, TypeError, UnicodeError):
            # A corrupt or unsafe route plan cannot silently restore
            # automatic pairing and bind an unknown source.
            plan = default_routes()
            plan["mode"] = "manual"
            self.route_policy_valid = False
        prior = getattr(self, "route_plan", default_routes())
        if prior["mode"] != plan["mode"] and plan["mode"] == "auto":
            self.assignments = read_json(ASSIGNMENTS, {})
        self.route_plan = plan
        self._route(sources if self.route_policy_valid else [],
                    sinks if (usb_ready and self.route_policy_valid) else {})
        try:
            state = patch_settings(defaults(), read_json(SETTINGS, self.settings))
            self.settings = state
            if usb_ready:
                for args in volume_commands(state, {
                    c: sinks["audiohub." + c] for c in CHANNELS
                    if "audiohub." + c in sinks
                }, output_id):
                    run(*args)
        except ValueError:
            # Invalid on-disk mixer values never expand volume or unmute.
            pass
        atomic_json(STATE, {
            "usb_output": bool(output),
            "usb_route_ready": usb_ready,
            # Positive graph evidence only. Missing direct links may reflect
            # PipeWire intermediary adapter nodes, never prove audio absence.
            "pipewire_links_inspected": graph_links["links_inspected"],
            "eq_output_usb_direct_links": [
                slot for slot in CHANNELS
                if graph_links["eq_output_to_usb_direct_link"][slot]
            ],
            "route_policy_valid": self.route_policy_valid,
            # Bounded *requested gain* estimate, not measured sound or a limiter.
            "effective_master_percent": min(
                100, max(0, round(100 * effective_master_gain(self.settings)))
            ),
            "virtual_channels": [c for c in CHANNELS if "audiohub." + c in sinks],
            "bluetooth_source_count": min(len(sources), MAX_BT_INPUTS),
            "active_routes": min(sum(
                1 for _, _, proc in self.loopbacks.values()
                if proc.poll() is None
            ), MAX_BT_INPUTS),
            "route_start_failures": min(getattr(self, "route_failures_total", 0), MAX_COUNTER),
            "output_switch_failures": min(getattr(self, "output_switch_failures", 0), MAX_COUNTER),
            "updated_at": int(time.time()),
        })

    def serve(self):
        try:
            while True:
                self.poll_safely()
                time.sleep(5)
        finally:
            # KeyboardInterrupt and ordinary shutdown must not orphan
            # managed audio processes. systemd also kills the service cgroup.
            self._stop_all_managed_routes()


def main():
    Supervisor().serve()


if __name__ == "__main__":
    main()
