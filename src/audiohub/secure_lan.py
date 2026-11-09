# SPDX-License-Identifier: AGPL-3.0-only
"""Manual, explicitly authorized TLS Windows-audio bridge for an isolated lab.

This is NOT a service or automatic image feature. Windows Scream must be
configured to unicast *only to local loopback*, not across the network.
The Pi receives only mutually authenticated TLS 1.3 frames. No default keys,
certificates, web access, network discovery, or unattended setup exist.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import os
import socket
import ssl
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path

from .network_laptop import (
    check_audio_target, close_player, lan_target, parse_scream_packet,
    player_command, validate_options, validate_session_minutes,
)

MAGIC = b"RVX-AUDIO1"
DOMAIN = b"RIVANOX-AUDIOHUB-LAN-TLS-PSK-v1:"
NONCE_BYTES = 32
KEY_BYTES = 32
MAX_PCM_BYTES = 1152
DEFAULT_PORT = 4044
DEFAULT_UDP_PORT = 4010
CONNECTION_SECONDS = 3
FRAME_SECONDS = 2
HEALTH_SECONDS = 3


def validate_key_bytes(key):
    if not isinstance(key, bytes) or len(key) != KEY_BYTES:
        raise ValueError("Exactly 32 secret bytes are required")
    return key


def read_private_key(path):
    """Read a non-linked 0600 regular file; never display its content."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Linked key files are forbidden")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != KEY_BYTES:
            raise ValueError("Key file must be a 32-byte regular file")
        # Windows ACLs cannot be established through POSIX st_mode:
        # Windows operator is responsible for configuring a private ACL.
        if os.name == "posix":
            if info.st_mode & 0o077 or info.st_uid != os.geteuid():
                raise ValueError("Key file must be owned by the caller and mode 0600")
        return validate_key_bytes(os.read(fd, KEY_BYTES + 1))
    finally:
        os.close(fd)


def validate_pin(digest):
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("Certificate SHA256 pin must be 64 lowercase hex digits")
    return digest


def _read_exact(stream, count, deadline):
    if not 1 <= count <= MAX_PCM_BYTES + 2:
        raise ValueError("Frame length rejected")
    chunks = bytearray()
    while len(chunks) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Protocol deadline expired")
        stream.settimeout(min(remaining, 1.0))
        part = stream.recv(count - len(chunks))
        if not part:
            raise ConnectionError("Stream closed")
        chunks.extend(part)
    return bytes(chunks)


def authenticate_server(stream, key):
    """One fresh server challenge per TCP connection; no key sent on wire."""
    validate_key_bytes(key)
    nonce = os.urandom(NONCE_BYTES)
    stream.sendall(MAGIC + nonce)
    proof = _read_exact(stream, 32, time.monotonic() + CONNECTION_SECONDS)
    valid = hmac.compare_digest(proof, hmac.new(key, DOMAIN + nonce, hashlib.sha256).digest())
    stream.sendall(b"\x01" if valid else b"\x00")
    if not valid:
        raise PermissionError("Sender authentication failed")
    return True


def authenticate_client(stream, key):
    validate_key_bytes(key)
    hello = _read_exact(stream, len(MAGIC) + NONCE_BYTES,
                        time.monotonic() + CONNECTION_SECONDS)
    if not hmac.compare_digest(hello[:len(MAGIC)], MAGIC):
        raise PermissionError("Unsupported authenticated audio protocol")
    proof = hmac.new(key, DOMAIN + hello[len(MAGIC):], hashlib.sha256).digest()
    stream.sendall(proof)
    if _read_exact(stream, 1, time.monotonic() + CONNECTION_SECONDS) != b"\x01":
        raise PermissionError("Sender not authorized")
    return True


def make_client_tls(raw, pinned_sha256):
    """TLS 1.3 plus mandatory exact DER certificate pin before any PSK proof."""
    pin = validate_pin(pinned_sha256)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # Replaced by mandatory out-of-band DER pin.
    connection = ctx.wrap_socket(raw)
    try:
        der = connection.getpeercert(binary_form=True)
        if not der or not hmac.compare_digest(hashlib.sha256(der).hexdigest(), pin):
            raise PermissionError("Untrusted Pi TLS certificate")
        return connection
    except BaseException:
        connection.close()
        raise


def make_server_context(cert_file, private_key_file):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(certfile=cert_file, keyfile=private_key_file)
    return ctx


def forward_loopback_pcm(udp, stream, deadline):
    """Forward only valid local Scream packets, with bounded frame sizes."""
    count = 0
    udp.settimeout(0.2)
    stream.settimeout(0.5)
    while time.monotonic() < deadline:
        try:
            packet, peer = udp.recvfrom(2048)
        except socket.timeout:
            continue
        if not isinstance(peer, tuple) or not peer or peer[0] != "127.0.0.1":
            continue
        pcm = parse_scream_packet(packet)
        if pcm is None:
            continue
        stream.sendall(struct.pack("!H", len(pcm)) + pcm)
        count += 1
    return count


def consume_authenticated_pcm(stream, target, deadline):
    """Play verified TLS frames to the private route; no audio after graph loss."""
    starting_generation = check_audio_target(target)
    last_check = time.monotonic()
    process = None
    count = 0
    try:
        while time.monotonic() < deadline:
            if lan_target() != target:
                raise RuntimeError("Private LAN reservation changed")
            now = time.monotonic()
            if now - last_check >= HEALTH_SECONDS:
                if check_audio_target(target) != starting_generation:
                    raise RuntimeError("PipeWire generation changed; stop to avoid stale playback")
                last_check = now
            frame_deadline = min(deadline, time.monotonic() + FRAME_SECONDS)
            length = struct.unpack("!H", _read_exact(stream, 2, frame_deadline))[0]
            if not 4 <= length <= MAX_PCM_BYTES or length % 4:
                raise ValueError("Invalid private stereo PCM frame")
            pcm = _read_exact(stream, length, frame_deadline)
            if process is None:
                process = subprocess.Popen(
                    player_command(target), stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    bufsize=0, close_fds=True,
                )
                if process.stdin is None:
                    raise RuntimeError("PipeWire player unavailable")
                os.set_blocking(process.stdin.fileno(), False)
            if process.poll() is not None:
                raise RuntimeError("Pi audio player exited")
            try:
                written = os.write(process.stdin.fileno(), pcm)
            except (BlockingIOError, OSError) as exc:
                raise RuntimeError("Pi audio write unavailable") from exc
            if written != len(pcm):
                raise RuntimeError("Partial PCM write; stop rather than replay")
            count += 1
    except (TimeoutError, socket.timeout):
        # An idle/slow sender must not hold the listener or the audio player.
        pass
    finally:
        close_player(process)
    return count


def run_server(*, bind_ip, sender_ip, port, key_file, cert_file,
               private_key_file, session_minutes=10, isolated_lab=False):
    if not isolated_lab:
        raise ValueError("Explicit isolated-lab server opt-in required")
    sender_ip, bind_ip, port = validate_options(sender_ip, bind_ip, port, True)
    validate_session_minutes(session_minutes)
    key = read_private_key(key_file)
    ctx = make_server_context(cert_file, private_key_file)
    target = lan_target()
    check_audio_target(target)  # Fail closed before opening the TCP port.
    deadline = time.monotonic() + session_minutes * 60
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((bind_ip, port))
        listener.listen(1)
        while time.monotonic() < deadline:
            listener.settimeout(min(1.0, max(0.001, deadline - time.monotonic())))
            try:
                raw, peer = listener.accept()
            except socket.timeout:
                continue
            with raw:
                if peer[0] != sender_ip:
                    # Only one permitted peer; never claim IP alone is authentication.
                    continue
                raw.settimeout(CONNECTION_SECONDS)
                with ctx.wrap_socket(raw, server_side=True) as stream:
                    authenticate_server(stream, key)
                    return consume_authenticated_pcm(stream, target, deadline)
    return 0


def run_bridge(*, server_ip, port, udp_port, key_file, pin_sha256,
               session_minutes=10, isolated_lab=False):
    if not isolated_lab:
        raise ValueError("Explicit isolated-lab Windows bridge opt-in required")
    validate_options(server_ip, "127.0.0.1", port, True)
    if isinstance(udp_port, bool) or not isinstance(udp_port, int) or not 1024 <= udp_port <= 65535:
        raise ValueError("Local UDP port must be 1024..65535")
    validate_session_minutes(session_minutes)
    key = read_private_key(key_file)
    pin = validate_pin(pin_sha256)
    deadline = time.monotonic() + session_minutes * 60
    with socket.create_connection((server_ip, port), timeout=CONNECTION_SECONDS) as raw:
        with make_client_tls(raw, pin) as stream:
            authenticate_client(stream, key)
            # Scream MUST unicast to loopback. No LAN-facing UDP bind exists.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.bind(("127.0.0.1", udp_port))
                return forward_loopback_pcm(udp, stream, deadline)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("server", "bridge"))
    parser.add_argument("--isolated-lab", action="store_true",
                        help="Explicit manual single-session opt-in; never a service")
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--session-minutes", type=int, default=10)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sender-ip", help="Expected Windows sender IPv4 (server)")
    parser.add_argument("--bind-ip", help="Exact Pi interface IPv4 (server)")
    parser.add_argument("--cert-file", help="Operator-created Pi TLS certificate (server)")
    parser.add_argument("--cert-key-file", help="Private Pi TLS certificate key (server)")
    parser.add_argument("--server-ip", help="Exact Pi private IPv4 (Windows bridge)")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--pin-sha256", help="Out-of-band Pi TLS certificate DER SHA256 (bridge)")
    args = parser.parse_args(argv)
    try:
        if args.mode == "server":
            if not all((args.sender_ip, args.bind_ip, args.cert_file, args.cert_key_file)):
                raise ValueError("Server requires explicit sender/bind/certificate paths")
            count = run_server(bind_ip=args.bind_ip, sender_ip=args.sender_ip,
                               port=args.port, key_file=args.key_file,
                               cert_file=args.cert_file, private_key_file=args.cert_key_file,
                               session_minutes=args.session_minutes, isolated_lab=args.isolated_lab)
        else:
            if not all((args.server_ip, args.pin_sha256)):
                raise ValueError("Bridge requires explicit Pi IP and certificate pin")
            count = run_bridge(server_ip=args.server_ip, port=args.port,
                               udp_port=args.udp_port, key_file=args.key_file,
                               pin_sha256=args.pin_sha256,
                               session_minutes=args.session_minutes, isolated_lab=args.isolated_lab)
        print("AudioHub isolated authenticated LAN session closed; accepted PCM frames: "
              + str(count))
        return 0
    except (OSError, ssl.SSLError, ValueError, RuntimeError,
            TimeoutError, ConnectionError, PermissionError):
        # No path, address, cert, key, raw peer or stream exception in output.
        parser.exit(2, "AudioHub authenticated LAN bench stopped (check private local setup).\n")


if __name__ == "__main__":
    sys.exit(main())
