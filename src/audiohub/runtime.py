# SPDX-License-Identifier: AGPL-3.0-only
"""Experimental headless USB output and Bluetooth audio routing supervisor.

Requires PipeWire/BlueZ, a matching USB speaker, and two pre-created virtual
EQ sinks. No claiming of hardware validation is implied by this implementation.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .discovery import bluetooth_sources, choose_usb_output, pipewire_nodes, virtual_sinks
from .mixer import CHANNELS, defaults, patch_settings, volume_commands

CONFIG = Path.home() / ".config" / "audiohub"
SETTINGS = CONFIG / "settings.json"
ASSIGNMENTS = CONFIG / "device-channels.json"
STATE = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "audiohub" / "runtime-status.json"


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


class Supervisor:
    def __init__(self):
        CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.settings = patch_settings(defaults(), read_json(SETTINGS, {}))
        self.assignments = read_json(ASSIGNMENTS, {})
        self.loopbacks = {}
        self.last_default = None

    def _assign(self, sources):
        assigned = set(self.assignments.values())
        changed = False
        for source in sources:
            address = source["address"]
            if address in self.assignments:
                continue
            for channel in ("music", "tablet"):
                if channel not in assigned:
                    self.assignments[address] = channel
                    assigned.add(channel)
                    changed = True
                    break
        if changed:
            atomic_json(ASSIGNMENTS, self.assignments)

    def _route(self, sources, sinks):
        """Maintain only routes to existing virtual sinks; restart changed streams."""
        self._assign(sources)
        desired = {}
        for source in sources:
            channel = self.assignments.get(source["address"])
            target = "audiohub." + channel if channel else None
            if target in sinks:
                desired[source["address"]] = (source["name"], target)
        for addr, (previous_source, previous_target, process) in list(self.loopbacks.items()):
            if desired.get(addr) == (previous_source, previous_target) and process.poll() is None:
                continue
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            del self.loopbacks[addr]
        for addr, (source, target) in desired.items():
            if addr in self.loopbacks:
                continue
            try:
                process = subprocess.Popen(
                    ["pw-loopback", "--name", "audiohub-" + target,
                     "--capture", source, "--playback", target],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.loopbacks[addr] = (source, target, process)
            except OSError as exc:
                print("Bluetooth routing failed:", exc, flush=True)

    def poll(self):
        result = run("pw-dump")
        nodes = pipewire_nodes(result.stdout) if result and result.returncode == 0 else []
        output = choose_usb_output(nodes)
        output_id = output.get("id") if output else None
        if output_id is not None and output_id != self.last_default:
            result = run("wpctl", "set-default", str(output_id))
            if result is not None and result.returncode == 0:
                self.last_default = output_id
        if output_id is None:
            self.last_default = None
        sources = bluetooth_sources(nodes)
        sinks = virtual_sinks(nodes)
        # Disconnect managed input loopbacks when the USB speaker disappears.
        self._route(sources, sinks if output_id is not None else {})
        try:
            state = patch_settings(defaults(), read_json(SETTINGS, self.settings))
            self.settings = state
            for args in volume_commands(state, {
                c: sinks["audiohub." + c] for c in CHANNELS
                if "audiohub." + c in sinks
            }, output_id):
                run(*args)
        except ValueError as exc:
            print("Invalid stored mixer settings:", exc, flush=True)
        atomic_json(STATE, {
            "usb_output": bool(output),
            "virtual_channels": [c for c in CHANNELS if "audiohub." + c in sinks],
            "bluetooth_source_count": len(sources),
            "active_routes": sum(1 for _, _, proc in self.loopbacks.values() if proc.poll() is None),
            "updated_at": int(time.time()),
        })

    def serve(self):
        while True:
            try:
                self.poll()
            except Exception as exc:
                print("AudioHub runtime recovery:", exc, flush=True)
            time.sleep(5)


def main():
    Supervisor().serve()


if __name__ == "__main__":
    main()
