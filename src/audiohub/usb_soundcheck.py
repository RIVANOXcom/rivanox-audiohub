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

from .discovery import choose_usb_output, pipewire_nodes, props
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


def run_soundcheck(*, confirmed=False):
    """Only explicit unprivileged console invocation can send the test pulse."""
    if confirmed is not True:
        raise SoundcheckUnavailable("Explicit isolated USB test confirmation required")
    if os.geteuid() == 0:
        raise SoundcheckUnavailable("Run the USB soundcheck as unprivileged audiohub user")
    target = safe_usb_target()
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
    args = parser.parse_args(argv)
    try:
        run_soundcheck(confirmed=args.confirm_isolated_usb_test)
    except SoundcheckUnavailable as exc:
        parser.exit(2, str(exc) + "\n")
    print(
        "Low-level left-then-right USB audio playback command completed. "
        "This is NOT proof of audible sound; record what you actually heard."
    )


if __name__ == "__main__":
    main()
