# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit, quiet USB left/right hearing check on an isolated Pi4 test bench.

Never enabled by boot, web requests or Bluetooth discovery. A successful
process exit does NOT prove that a human heard sound or that the full mixing
pipeline works. An authorized operator must record that observation separately.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
import re
import struct
import subprocess
import sys
from threading import Barrier

from .discovery import (_conflicting_node_ids, _parse_pipewire_graph,
                        choose_usb_output, pipewire_nodes, props, virtual_sinks)
from .mixer import CHANNELS
from .process_capture import bounded_command_output

RATE = 48000
GAIN = 0.02  # At most about -34 dBFS, independent of configured mixer gain.
PULSE_FRAMES = 8640  # 180 ms per channel.
GAP_FRAMES = 3840  # 80 ms of silence separates left from right.
MAX_PLAY_SECONDS = 5
MIX_FRAMES = RATE * 2  # Two seconds; sufficient overlap for three Pi4 sinks.
MIX_GAIN = GAIN / 3  # Worst-case in-phase sum <= the direct USB test level.
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


def safe_three_input_targets():
    """Read one consistent graph; require all three EQ paths point ONLY to USB.

    This is topology evidence, not sound verification or proof of physical
    exclusivity. Any graph ambiguity, missing link or other destination
    refuses the entire experiment before any playback process is started.
    """
    inspected = bounded_command_output(("pw-dump",), timeout=5)
    if inspected is None or inspected.returncode != 0:
        raise SoundcheckUnavailable("Mix probe unavailable: PipeWire inspection failed")
    graph = _parse_pipewire_graph(inspected.stdout)
    if graph is None:
        raise SoundcheckUnavailable("Mix probe unavailable: unreliable PipeWire graph")
    nodes = pipewire_nodes(graph)
    if _conflicting_node_ids(nodes):
        raise SoundcheckUnavailable("Mix probe unavailable: ambiguous PipeWire nodes")
    usb = choose_usb_output(nodes)
    if usb is None or type(usb.get("id")) is not int:
        raise SoundcheckUnavailable("Mix probe unavailable: USB speaker not identified")
    usb_id = usb["id"]
    sink_names = virtual_sinks(nodes)
    output_ids = {}
    for slot in CHANNELS:
        name = "audiohub." + slot
        if name not in sink_names:
            raise SoundcheckUnavailable("Mix probe unavailable: EQ input missing")
        outputs = [
            node for node in nodes
            if props(node).get("node.name") == name + ".output"
            and type(node.get("id")) is int and 0 <= node["id"] <= 2**31 - 1
        ]
        if len(outputs) != 1:
            raise SoundcheckUnavailable("Mix probe unavailable: EQ output ambiguous")
        output_ids[slot] = outputs[0]["id"]
    if len(set(output_ids.values())) != len(CHANNELS):
        raise SoundcheckUnavailable("Mix probe unavailable: repeated EQ output identity")
    observed = set()
    for link in graph:
        if type(link) is not dict or link.get("type") != "PipeWire:Interface:Link":
            continue
        info = link.get("info")
        if type(info) is not dict:
            raise SoundcheckUnavailable("Mix probe unavailable: malformed route")
        output_id = info.get("output-node-id")
        input_id = info.get("input-node-id")
        if type(output_id) is not int or type(input_id) is not int:
            raise SoundcheckUnavailable("Mix probe unavailable: malformed route")
        if output_id in output_ids.values():
            if input_id != usb_id:
                raise SoundcheckUnavailable("Mix probe unavailable: EQ route is not USB-only")
            observed.add(output_id)
    if observed != set(output_ids.values()):
        raise SoundcheckUnavailable("Mix probe unavailable: direct USB links not proven")
    return tuple("audiohub." + slot for slot in CHANNELS)


def three_input_pattern(slot):
    """Two-second, fixed, distinct, low-amplitude stereo marker per input.

    Each individually <= 2/3 percent of S16 full-scale. Even an exact,
    in-phase 3-source sum is below the quiet direct USB check peak.
    """
    if type(slot) is not str or slot not in CHANNELS:
        raise SoundcheckUnavailable("Unsupported mix probe input")
    frequency = {"music": 440, "laptop": 554, "tablet": 659}[slot]
    peak = round(32767 * MIX_GAIN)
    ramp = RATE // 100  # 10 ms attack/release to avoid sharp clicks.
    pcm = bytearray()
    for i in range(MIX_FRAMES):
        envelope = min(1.0, i / ramp, (MIX_FRAMES - 1 - i) / ramp)
        level = round(peak * envelope *
                      math.sin(2 * math.pi * frequency * i / RATE))
        pcm.extend(struct.pack("<hh", level, level))
    return bytes(pcm)


def _play_concurrently(proc, payload, barrier):
    """Synchronize feeding all three explicitly targeted playback streams."""
    barrier.wait(timeout=2)
    proc.communicate(input=payload, timeout=MAX_PLAY_SECONDS)
    return proc.returncode


def run_three_input_probe(*, confirmed=False):
    """Explicit, bounded three-stream bench probe; NEVER hardware attestation."""
    if confirmed is not True:
        raise SoundcheckUnavailable("Explicit isolated three-input confirmation required")
    if os.geteuid() == 0:
        raise SoundcheckUnavailable("Run the mix probe as unprivileged audiohub user")
    # Resolve all routes in ONE graph BEFORE opening any playback stream.
    targets = safe_three_input_targets()
    payloads = [three_input_pattern(slot) for slot in CHANNELS]
    procs = []
    try:
        for target in targets:
            procs.append(subprocess.Popen(
                ["pw-cat", "--playback", "--raw", "--format=s16", "--rate=48000",
                 "--channels=2", "--channel-map=stereo", "--target=" + target,
                 "--latency=100ms", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, shell=False,
            ))
        gate = Barrier(len(CHANNELS))
        with ThreadPoolExecutor(max_workers=len(CHANNELS)) as pool:
            pending = [pool.submit(_play_concurrently, p, payload, gate)
                       for p, payload in zip(procs, payloads)]
            for done in as_completed(pending, timeout=MAX_PLAY_SECONDS + 2):
                if done.result() != 0:
                    raise SoundcheckUnavailable("One or more mix test players failed")
    except Exception:
        # Do not leak subprocess stderr, host identifiers or partial results.
        raise SoundcheckUnavailable("Three-input probe unavailable or timed out") from None
    finally:
        # Clean up on every path. Never leave a test player running.
        for proc in procs:
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
    # This only proves three local player calls completed in the lab session.
    # Audible mixing, isolation, EQ response and clipping remain unverified.
    return True

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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--through-input", choices=CHANNELS, default=None,
        metavar="{music,laptop,tablet}",
        help="Test one EQ input when its direct USB link is observed",
    )
    mode.add_argument(
        "--three-input-mix-probe", action="store_true",
        help="Explicitly test three quiet overlapping EQ inputs on an isolated USB bench",
    )
    args = parser.parse_args(argv)
    try:
        if args.three_input_mix_probe:
            run_three_input_probe(confirmed=args.confirm_isolated_usb_test)
        else:
            run_soundcheck(confirmed=args.confirm_isolated_usb_test,
                           through_input=args.through_input)
    except SoundcheckUnavailable as exc:
        parser.exit(2, str(exc) + "\n")
    print(
        "Local audio player command(s) completed. This is NOT proof of "
        "audible sound, three-way mixing or hardware acceptance; "
        "record what you actually heard."
    )


if __name__ == "__main__":
    main()
