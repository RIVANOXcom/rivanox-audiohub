# SPDX-License-Identifier: AGPL-3.0-only
"""Headless Bluetooth -> per-source EQ -> selected USB speaker supervisor.

Source-level safety and recovery model. Actual Pi4 + Edifier sound and
multi-device A2DP feasibility are NOT proven without physical acceptance.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from .discovery import bluetooth_sources, choose_usb_output, pipewire_nodes, virtual_sinks
from .mixer import CHANNELS, defaults, effective_master_gain, patch_settings, volume_commands

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


def read_json(path, fallback):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, type(fallback)) else fallback
    except (OSError, ValueError, TypeError):
        return fallback


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def backoff_seconds(failures):
    """Exponential restart cap; repeated stream failures must not hot-loop."""
    return min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** min(max(failures - 1, 0), 4)))


def pipewire_loopback_args(source, channel):
    """Explicit capture source and EQ playback target, never a default sink."""
    if (type(source) is not str or _SOURCE_NAME.fullmatch(source) is None
            or channel not in ("music", "tablet")):
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

    def _assign(self, sources):
        """Keep paired source assignments stable; never evict another source."""
        self.assignments = {
            address: channel
            for address, channel in self.assignments.items()
            if type(address) is str and _BLUETOOTH_MAC.fullmatch(address)
            and channel in ("music", "tablet")
        }
        # A corrupted on-disk mapping with duplicate channels must not
        # let unrelated sources force two streams into the same EQ input.
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
            for channel in ("music", "tablet"):
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
                    and channel in ("music", "tablet") and target in sinks
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
        self._route(sources, sinks if usb_ready else {})
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
        while True:
            try:
                self.poll()
            except Exception:
                # Untrusted metadata must never kill the headless audio loop.
                pass
            time.sleep(5)


def main():
    Supervisor().serve()


if __name__ == "__main__":
    main()
