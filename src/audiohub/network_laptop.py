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
import time

from .discovery import choose_usb_output, pipewire_nodes, virtual_sinks

TARGET = "audiohub.laptop"
PORT = 4010
MAX_PCM = 1152
HEADER_SIZE = 5
HEALTH_CHECK_SECONDS = 3.0
IDLE_SECONDS = 5.0


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
    if (sender.is_multicast or sender.is_unspecified or sender.is_reserved
            or not (sender.is_private or sender.is_loopback)):
        raise ValueError("Sender must be a specific private or loopback IPv4 address")
    if (bind.is_multicast or bind.is_reserved
            or not (bind.is_private or bind.is_loopback or bind.is_unspecified)):
        raise ValueError("Bind only to a private, loopback or explicit all-interface IPv4 address")
    return str(sender), str(bind), port


def accepted_pcm(packet, peer, sender_ip):
    """Reject other LAN senders and malformed frames before starting a player."""
    if not isinstance(peer, tuple) or not peer or peer[0] != sender_ip:
        return None
    return parse_scream_packet(packet)


def player_command():
    """Use an explicit PipeWire sink instead of auto-routing to another output."""
    return [
        "pw-cat", "--playback", "--raw", "--format=s16",
        "--rate=48000", "--channels=2", "--channel-map=stereo",
        "--target=" + TARGET, "--latency=100ms", "-",
    ]


def check_audio_target():
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
    if TARGET not in virtual_sinks(nodes):
        raise RuntimeError("Laptop virtual sink unavailable")
    if choose_usb_output(nodes) is None:
        raise RuntimeError("USB audio output unavailable")


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


def serve(sender_ip, bind_ip, port):
    """Experimental single-sender receiver; no default image service is installed."""
    check_audio_target()
    player = None
    retry_after = 0.0
    last_written_at = None
    next_health_check = 0.0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.settimeout(1.0)
        udp.bind((bind_ip, port))
        try:
            while True:
                now = time.monotonic()
                if player is not None:
                    if last_written_at is not None and now - last_written_at >= IDLE_SECONDS:
                        close_player(player)
                        player = None
                    elif now >= next_health_check:
                        next_health_check = now + HEALTH_CHECK_SECONDS
                        try:
                            check_audio_target()
                        except RuntimeError:
                            # Never keep playing if the chosen USB or laptop sink vanishes.
                            close_player(player)
                            player = None
                            retry_after = now + 2.0
                try:
                    packet, peer = udp.recvfrom(2048)
                except socket.timeout:
                    continue
                pcm = accepted_pcm(packet, peer, sender_ip)
                if pcm is None:
                    continue
                if player is not None and player.poll() is not None:
                    close_player(player)
                    player = None
                if player is None:
                    if time.monotonic() < retry_after:
                        continue
                    retry_after = time.monotonic() + 2.0
                    try:
                        check_audio_target()
                        player = subprocess.Popen(
                            player_command(), stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            bufsize=0, close_fds=True,
                        )
                        if player.stdin is None:
                            raise RuntimeError("Audio output pipe unavailable")
                        os.set_blocking(player.stdin.fileno(), False)
                        next_health_check = now + HEALTH_CHECK_SECONDS
                    except (OSError, RuntimeError):
                        close_player(player)
                        player = None
                        continue
                try:
                    # One PCM packet fits within PIPE_BUF on Linux. Never block
                    # indefinitely waiting for a failed/stalled audio process.
                    written = os.write(player.stdin.fileno(), pcm)
                except BlockingIOError:
                    # A full buffer causes a packet drop, not an unbounded queue.
                    continue
                except OSError:
                    close_player(player)
                    player = None
                    continue
                if written != len(pcm):
                    close_player(player)
                    player = None
                else:
                    last_written_at = now
        finally:
            close_player(player)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sender-ip", required=True, help="Expected Windows IPv4 source")
    parser.add_argument("--bind-ip", required=True, help="Explicit IPv4 receiver interface")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--unsafe-lan-test", action="store_true",
                        help="Opt in to unauthenticated, trusted-LAN test only")
    args = parser.parse_args(argv)
    try:
        sender, bind, port = validate_options(
            args.sender_ip, args.bind_ip, args.port, args.unsafe_lan_test
        )
        serve(sender, bind, port)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, "AudioHub experimental receiver unavailable: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
