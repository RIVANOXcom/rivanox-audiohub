# SPDX-License-Identifier: AGPL-3.0-only
"""Interactive Windows bridge launcher: private local setup, no remote API.

Never embeds credentials, opens a port without an explicit final consent,
writes a configuration file, or elevates permissions. Standalone on Windows:
Python 3.11+ stdlib and the separately installed Scream driver are required.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import ssl
import sys

from . import secure_lan


def check_python_tls():
    """Fail before prompts or network access on an unsupported interpreter."""
    if sys.version_info < (3, 11) or not getattr(ssl, "HAS_TLSv1_3", False):
        raise RuntimeError("Python 3.11+ with TLS 1.3 is required")
    return True


def _read_minutes(raw):
    raw = raw.strip() or "10"
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError("Use a whole number of minutes")
    return secure_lan.validate_session_minutes(int(raw))


def validate_local_setup(server_ip, pin_sha256, key_path, minutes):
    """Read-only configuration validation; never dial or open a UDP port."""
    secure_lan.validate_options(server_ip, "127.0.0.1",
                                secure_lan.DEFAULT_PORT, True)
    secure_lan.validate_pin(pin_sha256)
    secure_lan.validate_session_minutes(minutes)
    key = Path(key_path)
    if not key.is_absolute():
        raise ValueError("The private key must have an absolute file path")
    secure_lan.read_private_key(key)
    return str(key)


def interactive_bridge(*, input_fn=input, output=print, execute=None,
                       check_only=False, test_tone=False, test_channel="both"):
    """One understandable, deliberately manual session with an explicit gate.

    The private key is read from disk and never printed or sent in the
    command line. The fingerprint is not secret but must be checked offline.
    No settings are saved; a repeat session requires new consent.
    """
    check_python_tls()
    if not isinstance(test_tone, bool):
        raise ValueError("Invalid explicit test mode")
    secure_lan.validate_tone_channel(test_channel)
    if test_channel != "both" and not test_tone:
        raise ValueError("Channel selection requires --test-tone")
    if execute is None:
        execute = secure_lan.run_bridge
    output("RIVANOX AudioHub - isolated Windows audio experiment")
    output("Requires external Python 3.11+ and a private Pi test bench.")
    output("Quiet 5-second speaker test: NO Windows Scream driver required."
           if test_tone else "Scream streaming: external Windows driver with loopback unicast required.")
    # Driver is only required for real Windows program audio, NOT for speaker soundcheck.
    # This choice never changes Pi routing or enables a receiver service.
    # Keep manual confirmation for either mode.
    output("a separately authorized Pi, and a physically isolated test LAN.")
    output("No installer, driver, keys or certificates are included.")
    ip = input_fn("Isolated Pi IPv4 (e.g. 192.168.10.30): ").strip()
    pin = input_fn("Verified Pi TLS certificate SHA256 (64 lowercase hex): ").strip()
    key_file = input_fn("Absolute path to private 32-byte shared key file: ").strip()
    minutes = _read_minutes(input_fn("Session minutes [10, maximum 30]: "))
    validate_local_setup(ip, pin, key_file, minutes)
    output("Local configuration checks passed. Windows key-file ACLs")
    output("and the external Scream driver are NOT verified by this check.")
    if test_tone:
        output("QUIET TONE: keep speaker volume LOW. Human sound check required.")
        output("Stereo channel test: " + test_channel + ". Five seconds maximum.")
    else:
        output("Windows Scream must unicast only to 127.0.0.1:4010.")
    if check_only:
        output("CHECK ONLY: no TCP/UDP listener opened and no audio transmitted.")
        return 0
    output("The session stops automatically; a new launch requires consent.")
    confirmation = input_fn('Type ISOLATED to start the manual test: ').strip()
    if confirmation != "ISOLATED":
        output("Cancelled; no network connection opened.")
        return 1
    params = dict(
        server_ip=ip, port=secure_lan.DEFAULT_PORT,
        udp_port=secure_lan.DEFAULT_UDP_PORT, key_file=key_file,
        pin_sha256=pin, session_minutes=minutes, isolated_lab=True,
    )
    if test_tone:
        params["test_tone"] = True
        if test_channel != "both":
            params["test_channel"] = test_channel
    frames = execute(**params)
    output("Isolated session closed. Accepted local PCM frames: " + str(frames))
    output("A frame count is not proof of sound from the Pi USB speaker.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true",
                        help="Check Python TLS 1.3 support, without any credentials or ports")
    parser.add_argument("--check-only", action="store_true",
                        help="Validate operator-provided local setup without opening sockets")
    parser.add_argument("--test-tone", action="store_true",
                        help="Send a quiet five-second Pi speaker soundcheck without Scream")
    parser.add_argument("--test-channel", choices=secure_lan.TONE_CHANNELS, default="both",
                        help="Both, left only, right only, or left-then-right (requires --test-tone)")
    parser.add_argument("--gui", action="store_true",
                        help="Open optional local graphical lab controls; no automatic connection")
    args = parser.parse_args(argv)
    try:
        if args.gui:
            # Tk is optional and imported ONLY when the operator requests GUI.
            from .windows_bridge_gui import launch
            return launch()
        if args.self_check:
            check_python_tls()
            print("Python TLS 1.3 supported. No keys, driver, network,")
            print("audio or Windows hardware have been verified.")
            return 0
        return interactive_bridge(check_only=args.check_only, test_tone=args.test_tone,
                                  test_channel=args.test_channel)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; no automatic retry.", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError, ConnectionError,
            TimeoutError, PermissionError, ssl.SSLError):
        # Never print exception strings containing private file paths, IPs,
        # peer state or OS internals. Check the local setup offline instead.
        print("AudioHub manual test stopped. Review private setup and")
        print("isolated-lab instructions; no automatic retry.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
