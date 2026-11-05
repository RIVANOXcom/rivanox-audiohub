# SPDX-License-Identifier: AGPL-3.0-only
"""Manual, unverified Windows Scream UDP receiver for the laptop PipeWire sink.

This is deliberately not enabled by an image, systemd unit or the web UI.
Scream UDP has no sender authentication; IP filtering cannot stop spoofing.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import socket
import subprocess
import sys
import time

from .discovery import choose_usb_output, pipewire_nodes, virtual_sinks
from .network_buffer import PcmPacketBuffer, ReceiverCounters
from .source_routes import lan_target

TARGET = "audiohub.laptop"
PORT = 4010
MAX_PCM = 1152
HEADER_SIZE = 5
HEALTH_CHECK_SECONDS = 3.0
ROUTE_POLICY_CHECK_SECONDS = 1.0
IDLE_SECONDS = 5.0
# Only explicit local IPv4 host addresses are allowed for manual opt-in tests.
# ipaddress.is_private alone also includes link-local/special ranges.
TEST_NETS = tuple(ipaddress.IPv4Network(net) for net in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"
))


def _specific_test_ip(ip):
    return any(ip in net for net in TEST_NETS) and not (
        ip.is_unspecified or ip.is_multicast or ip.is_reserved
    )



def parse_scream_packet(packet):
    """Accept only legacy 48 kHz / 16-bit / stereo little-endian Scream PCM."""
    if not isinstance(packet, bytes):
        return None
    if not HEADER_SIZE + 4 <= len(packet) <= HEADER_SIZE + MAX_PCM:
        return None
    if packet[0:3] != bytes((1, 16, 2)):
        return None
    # Stereo positions: FL and FR, or a sender which leaves the mask unset.
    if int.from_bytes(packet[3:5], "little") not in (0, 3):
        return None
    pcm = packet[HEADER_SIZE:]
    return pcm if len(pcm) % 4 == 0 else None


def validate_options(sender_ip, bind_ip, port, enabled):
    """Require conscious LAN-test opt-in and narrowly scoped IPv4 addresses."""
    if not enabled:
        raise ValueError("Explicit --unsafe-lan-test opt-in is required")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    try:
        sender = ipaddress.IPv4Address(sender_ip)
        bind = ipaddress.IPv4Address(bind_ip)
    except ipaddress.AddressValueError as exc:
        raise ValueError("IPv4 addresses are required") from exc
    if not _specific_test_ip(sender):
        raise ValueError("Sender must be a specific RFC1918 or loopback IPv4 host")
    if not _specific_test_ip(bind):
        raise ValueError("Bind must be a specific RFC1918 or loopback IPv4 interface")
    return str(sender), str(bind), port


def accepted_pcm(packet, peer, sender_ip):
    """Reject other LAN senders and malformed frames before starting a player."""
    if not isinstance(peer, tuple) or not peer or peer[0] != sender_ip:
        return None
    return parse_scream_packet(packet)


def player_command(target=TARGET):
    """Use an explicit PipeWire sink instead of auto-routing to another output."""
    if target not in ("audiohub.music", "audiohub.laptop", "audiohub.tablet"):
        raise ValueError("Unsupported manual audio target")
    return [
        "pw-cat", "--playback", "--raw", "--format=s16",
        "--rate=48000", "--channels=2", "--channel-map=stereo",
        "--target=" + target, "--latency=100ms", "-",
    ]


def check_audio_target(target=TARGET):
    """Fail closed if the intended virtual channel or USB output is missing."""
    try:
        result = subprocess.run(
            ["pw-dump"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("PipeWire node inspection failed") from exc
    if result.returncode != 0:
        raise RuntimeError("PipeWire node inspection failed")
    nodes = pipewire_nodes(result.stdout)
    if target not in ("audiohub.music", "audiohub.laptop", "audiohub.tablet") or target not in virtual_sinks(nodes):
        raise RuntimeError("Laptop virtual sink unavailable")
    output = choose_usb_output(nodes)
    if output is None:
        raise RuntimeError("USB audio output unavailable")
    # AudioHub's EQ filters ultimately play to the system default.
    # Before opening the manual UDP test socket, reassert only the
    # currently recognized USB sink; never silently fall back to HDMI.
    try:
        selected = subprocess.run(
            ["wpctl", "set-default", str(output["id"])],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("USB output routing not ready") from exc
    if selected.returncode != 0:
        raise RuntimeError("USB output routing not ready")


def close_player(process):
    if process is None:
        return
    try:
        if process.stdin is not None:
            process.stdin.close()
    except OSError:
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def serve(sender_ip, bind_ip, port, *, unsafe_lan_test=False, prefill_packets=1, diagnostics=False):
    """Manually gated receiver with finite PCM backlog and opt-in counters.

    This does not reconstruct missing/reordered UDP packets or authenticate
    the claimed sender. Keep the listener off in normal product operation.
    """
    # Do not permit internal callers to bypass the CLI unsafe-LAN gate.
    sender_ip, bind_ip, port = validate_options(sender_ip, bind_ip, port, unsafe_lan_test)
    backlog = PcmPacketBuffer(prefill=prefill_packets)
    target = lan_target()  # Private local route plan, not a CLI/UDP source field.
    check_audio_target(target)
    counters = ReceiverCounters()
    player = None
    retry_after = 0.0
    last_written_at = None
    next_health_check = 0.0
    next_policy_check = 0.0
    next_report_at = None

    def stop_player():
        nonlocal player, last_written_at
        if player is not None:
            close_player(player)
            counters.player_stopped += 1
        player = None
        last_written_at = None
        backlog.clear()  # Never replay stale audio across player/USB loss.

    def report(now=None, *, final=False):
        nonlocal next_report_at
        if not diagnostics:
            return
        if not final and now < next_report_at:
            return
        counters.backlog_dropped = backlog.dropped_oldest
        print("audiohub.network " + counters.json_line(), file=sys.stderr, flush=True)
        if not final:
            next_report_at = now + 60.0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.settimeout(0.02)
        udp.bind((bind_ip, port))
        try:
            while True:
                now = time.monotonic()
                # Do not keep playing into a stale input when the operator
                # changes the manual LAN slot. Exit and require a fresh opt-in.
                if now >= next_policy_check:
                    next_policy_check = now + ROUTE_POLICY_CHECK_SECONDS
                    if lan_target() != target:
                        raise RuntimeError("LAN route changed; restart isolated test receiver")
                if next_report_at is None:
                    next_report_at = now + 60.0
                report(now)
                if player is not None:
                    if last_written_at is not None and now - last_written_at >= IDLE_SECONDS:
                        counters.idle_shutdown += 1
                        stop_player()
                    elif now >= next_health_check:
                        next_health_check = now + HEALTH_CHECK_SECONDS
                        try:
                            check_audio_target(target)
                        except RuntimeError:
                            counters.output_lost += 1
                            stop_player()
                            retry_after = now + 2.0

                try:
                    packet, peer = udp.recvfrom(2048)
                except socket.timeout:
                    packet = None
                    peer = None

                if packet is not None:
                    counters.datagrams += 1
                    if not isinstance(peer, tuple) or not peer or peer[0] != sender_ip:
                        counters.foreign_sender += 1
                        continue
                    pcm = parse_scream_packet(packet)
                    if pcm is None:
                        counters.invalid_format += 1
                        continue
                    counters.accepted += 1
                    if player is not None and player.poll() is not None:
                        stop_player()
                    backlog.append(pcm)

                ready = backlog.peek()
                if ready is None:
                    continue
                if player is None:
                    if time.monotonic() < retry_after:
                        backlog.clear()
                        continue
                    retry_after = time.monotonic() + 2.0
                    try:
                        check_audio_target(target)
                        player = subprocess.Popen(
                            player_command(target), stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            bufsize=0, close_fds=True,
                        )
                        if player.stdin is None:
                            raise RuntimeError("Audio output pipe unavailable")
                        os.set_blocking(player.stdin.fileno(), False)
                        next_health_check = now + HEALTH_CHECK_SECONDS
                        counters.player_started += 1
                    except (OSError, RuntimeError):
                        stop_player()
                        continue
                try:
                    # One PCM packet fits within PIPE_BUF on Linux. Preserve
                    # whole packet boundaries; backpressure retains up to 16.
                    written = os.write(player.stdin.fileno(), ready)
                except BlockingIOError:
                    counters.write_blocked += 1
                    continue
                except OSError:
                    counters.write_failed += 1
                    stop_player()
                    continue
                if written != len(ready):
                    # Partial PCM frames are not replayed after output failure.
                    counters.write_failed += 1
                    stop_player()
                else:
                    backlog.consume()
                    last_written_at = now
        finally:
            stop_player()
            report(final=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sender-ip", required=True, help="Expected Windows IPv4 source")
    parser.add_argument("--bind-ip", required=True, help="Explicit IPv4 receiver interface")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--unsafe-lan-test", action="store_true",
                        help="Opt in to unauthenticated, trusted-LAN test only")
    parser.add_argument("--prefill-packets", type=int, default=1,
                        help="Require 1-16 received PCM packets before starting playback")
    parser.add_argument("--diagnostics", action="store_true",
                        help="Write aggregate counters to stderr every 60 s and on shutdown")
    args = parser.parse_args(argv)
    try:
        sender, bind, port = validate_options(
            args.sender_ip, args.bind_ip, args.port, args.unsafe_lan_test
        )
        serve(sender, bind, port,
              unsafe_lan_test=args.unsafe_lan_test,
              prefill_packets=args.prefill_packets, diagnostics=args.diagnostics)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, "AudioHub experimental receiver unavailable: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
