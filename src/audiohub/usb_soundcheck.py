# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit, quiet USB left/right hearing check on an isolated Pi4 test bench.

Never enabled by boot, web requests or Bluetooth discovery. A successful
process exit does NOT prove that a human heard sound or that the full mixing
pipeline works. An authorized operator must record that observation separately.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import struct
import subprocess
import sys

from .discovery import (_conflicting_node_ids, _parse_pipewire_graph,
                        choose_usb_output, pipewire_nodes, props, virtual_sinks)
from .mixer import CHANNELS
from .process_capture import bounded_command_output

RATE = 48000
GAIN = 0.02  # At most about -34 dBFS, independent of configured mixer gain.
PULSE_FRAMES = 8640  # 180 ms per channel.
GAP_FRAMES = 3840  # 80 ms of silence separates left from right.
MAX_PLAY_SECONDS = 5
# Never pass arbitrary PipeWire metadata as a CLI target or invoke a shell.
_USB_NAME = re.compile(r"alsa_output\.usb-[a-zA-Z0-9_.:-]{1,160}\Z")


class SoundcheckUnavailable(RuntimeError):
    """No sound is presumed; do not reveal raw device metadata in errors."""


def stereo_pattern():
    """One fixed, short, quiet 48-kHz S16LE left-then-right test pattern.

    Generated from scratch; no copyrighted media, microphone or input files.
    No caller-supplied duration, amplitude, target or waveform is permitted.
    """
    result = bytearray()
    level = round(32767 * GAIN)
    for frames, frequency, channel in (
        (PULSE_FRAMES, 660, 0),
        (GAP_FRAMES, 0, -1),
        (PULSE_FRAMES, 880, 1),
    ):
        for i in range(frames):
            sample = round(level * math.sin(2 * math.pi * frequency * i / RATE)) if frequency else 0
            result.extend(struct.pack("<hh", sample if channel == 0 else 0,
                                      sample if channel == 1 else 0))
    return bytes(result)


def safe_usb_target():
    """Read exactly one bounded PipeWire graph; never use default/HDMI sinks."""
    inspected = bounded_command_output(("pw-dump",), timeout=5)
    if inspected is None or inspected.returncode != 0:
        raise SoundcheckUnavailable("USB soundcheck unavailable: PipeWire inspection failed")
    output = choose_usb_output(pipewire_nodes(inspected.stdout))
    if output is None:
        raise SoundcheckUnavailable("USB soundcheck unavailable: one safe USB output not found")
    name = props(output).get("node.name")
    if type(name) is not str or _USB_NAME.fullmatch(name) is None:
        raise SoundcheckUnavailable("USB soundcheck unavailable: invalid USB output target")
    return name



def safe_input_target(slot):
    """Require an actual virtual EQ sink AND direct link to the USB output.

    The explicit route is inspected read-only. No link or a competing output
    is an UNKNOWN audio path, not proof of no sound; refuse to send test PCM
    rather than risk silent/HDMI playback through a default sink.
    """
    if type(slot) is not str or slot not in CHANNELS:
        raise SoundcheckUnavailable("Unsupported local input test slot")
    inspected = bounded_command_output(("pw-dump",), timeout=5)
    if inspected is None or inspected.returncode != 0:
        raise SoundcheckUnavailable("Input test unavailable: PipeWire inspection failed")
    graph = _parse_pipewire_graph(inspected.stdout)
    if graph is None:
        raise SoundcheckUnavailable("Input test unavailable: unreliable PipeWire graph")
    nodes = pipewire_nodes(graph)
    if _conflicting_node_ids(nodes):
        raise SoundcheckUnavailable("Input test unavailable: ambiguous PipeWire nodes")
    target = "audiohub." + slot
    if target not in virtual_sinks(nodes):
        raise SoundcheckUnavailable("Input test unavailable: requested EQ sink missing")
    usb = choose_usb_output(nodes)
    if usb is None:
        raise SoundcheckUnavailable("Input test unavailable: USB speaker missing")
    # Only the EXACT filter-chain playback node is relevant, not a name
    # supplied by a caller, an arbitrary Link property or a default sink.
    outputs = [
        node for node in nodes
        if props(node).get("node.name") == target + ".output"
        and type(node.get("id")) is int and 0 <= node["id"] <= 2**31 - 1
    ]
    if len(outputs) != 1:
        raise SoundcheckUnavailable("Input test unavailable: EQ output ambiguous")
    output_id = outputs[0]["id"]
    usb_id = usb["id"]
    direct_usb_link = False
    for link in graph:
        if type(link) is not dict or link.get("type") != "PipeWire:Interface:Link":
            continue
        info = link.get("info")
        if type(info) is not dict:
            continue
        if info.get("output-node-id") != output_id:
            continue
        # A signal from this EQ output routed anywhere else is unsafe
        # for this diagnostic. Even a concurrently present USB edge is
        # insufficient if another path is also reachable.
        input_id = info.get("input-node-id")
        if type(input_id) is not int or input_id != usb_id:
            raise SoundcheckUnavailable("Input test unavailable: EQ output not USB-only")
        direct_usb_link = True
    if not direct_usb_link:
        raise SoundcheckUnavailable("Input test unavailable: no direct EQ-to-USB link")
    return target

def run_soundcheck(*, confirmed=False, through_input=None):
    """Only explicit unprivileged console invocation can send the test pulse."""
    if confirmed is not True:
        raise SoundcheckUnavailable("Explicit isolated USB test confirmation required")
    if os.geteuid() == 0:
        raise SoundcheckUnavailable("Run the USB soundcheck as unprivileged audiohub user")
    if through_input is not None and (
            type(through_input) is not str or through_input not in CHANNELS):
        raise SoundcheckUnavailable("Unsupported local input test slot")
    target = (safe_usb_target() if through_input is None
              else safe_input_target(through_input))
    cmd = [
        "pw-cat", "--playback", "--raw", "--format=s16", "--rate=48000",
        "--channels=2", "--channel-map=stereo", "--target=" + target,
        "--latency=100ms", "-",
    ]
    try:
        completed = subprocess.run(
            cmd, input=stereo_pattern(), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False, timeout=MAX_PLAY_SECONDS,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SoundcheckUnavailable("USB test player unavailable or timed out") from None
    if completed.returncode != 0:
        raise SoundcheckUnavailable("USB test player exited unsuccessfully")
    # Success is a process-level signal ONLY; the operator must confirm
    # audible left and right output separately, at low speaker volume.
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-isolated-usb-test", action="store_true",
        help="Explicitly opt into a local low-level left then right soundcheck",
    )
    parser.add_argument(
        "--through-input", choices=CHANNELS, default=None,
        metavar="{music,laptop,tablet}",
        help="Instead of direct USB, test one EQ input only when its direct USB link is observed",
    )
    args = parser.parse_args(argv)
    try:
        run_soundcheck(confirmed=args.confirm_isolated_usb_test,
                       through_input=args.through_input)
    except SoundcheckUnavailable as exc:
        parser.exit(2, str(exc) + "\n")
    print(
        "Low-level left-then-right local audio playback command completed. "
        "This is NOT proof of audible sound or a complete EQ/mix path; "
        "record what you actually heard."
    )


if __name__ == "__main__":
    main()
