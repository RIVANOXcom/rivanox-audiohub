# SPDX-License-Identifier: AGPL-3.0-only
"""Minimal read-only local health page for unverified AudioHub images.

No device-management APIs are exposed here. No authentication secrets, Bluetooth
device addresses or audio source identifiers are returned. Never add mutation
handlers without first completing the secure device-ownership design.
"""
from __future__ import annotations

import json
import os
import stat
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .runtime import STATE
from .status_bind import select_bind_address

WEBROOT = Path(os.environ.get("AUDIOHUB_WEBROOT", "/opt/audiohub/web"))
ALLOWED = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    **{"/locales/" + code + ".json": ("locales/" + code + ".json", "application/json; charset=utf-8")
       for code in ("en", "de", "es", "fr", "it")},
}
PUBLIC_FIELDS = frozenset({"fresh", "usb_connected", "active_routes", "bluetooth_sources", "virtual_channel_count"})


def _small_nonnegative(value, max_value):
    # Ensure booleans, unexpected strings and negative values cannot escape.
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return min(max(value, 0), max_value)


def public_status(status, *, now=None):
    """Return only explicitly approved health fields, never device identifiers."""
    now = int(time.time() if now is None else now)
    if not isinstance(status, dict):
        status = {}
    updated = status.get("updated_at")
    fresh = (
        isinstance(updated, int) and not isinstance(updated, bool)
        and 0 <= now - updated <= 30
    )
    if not fresh:
        return {"fresh": False, "usb_connected": False,
                "active_routes": 0, "bluetooth_sources": 0,
                "virtual_channel_count": 0}
    channels = status.get("virtual_channels")
    if not isinstance(channels, list):
        channels = []
    valid_channels = {"music", "laptop", "tablet"}
    return {
        "fresh": True,
        "usb_connected": status.get("usb_output") is True,
        "active_routes": _small_nonnegative(status.get("active_routes"), 3),
        "bluetooth_sources": _small_nonnegative(status.get("bluetooth_source_count"), 2),
        # Read JSON is untrusted: reject list/dict values before set().
        "virtual_channel_count": len(set(
            ch for ch in channels if isinstance(ch, str) and ch in valid_channels
        )),
    }


STATIC_MAX_BYTES = 512 * 1024
STATUS_MAX_BYTES = 32 * 1024


def _bounded_regular_bytes(path, limit):
    """Open every path component with O_NOFOLLOW and read at most 'limit'.

    Never follow WEBROOT/asset/status symlinks outside the Pi image. This
    also refuses FIFOs/devices, unexpectedly large assets and status JSON,
    incomplete reads and non-absolute paths. The path comes from a fixed
    allowlist or the runtime's own state path, not the HTTP request.
    """
    path = Path(path)
    if (not path.is_absolute() or ".." in path.parts
            or len(path.parts) < 2 or type(limit) is not int or limit <= 0):
        return None
    directory = None
    file_fd = None
    try:
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for component in path.parts[1:-1]:
            next_directory = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=directory,
            )
            os.close(directory)
            directory = next_directory
        file_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory,
        )
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            return None
        chunks = []
        remaining = info.st_size
        while remaining:
            part = os.read(file_fd, min(remaining, 65536))
            if not part:
                return None
            chunks.append(part)
            remaining -= len(part)
        # Fail closed if content grew between stat and the bounded read.
        if os.read(file_fd, 1):
            return None
        return b"".join(chunks)
    except (OSError, ValueError):
        return None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory is not None:
            os.close(directory)


def read_public_status(*, path=None, now=None):
    """Read a bounded, non-symlinked runtime state file, never raw secrets."""
    body = _bounded_regular_bytes(STATE if path is None else path, STATUS_MAX_BYTES)
    if body is None:
        return public_status({}, now=now)
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError):
        decoded = {}
    return public_status(decoded, now=now)


class Handler(BaseHTTPRequestHandler):
    server_version = "AudioHub-Preview"
    sys_version = ""

    def respond(self, code, content, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                         "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            body = json.dumps(read_public_status(), separators=(",", ":")).encode()
            self.respond(200, body, "application/json; charset=utf-8")
            return
        if path not in ALLOWED:
            self.respond(404, b"Not found", "text/plain; charset=utf-8")
            return
        filename, content_type = ALLOWED[path]
        content = _bounded_regular_bytes(WEBROOT / filename, STATIC_MAX_BYTES)
        if content is None:
            self.respond(503, b"Static resources unavailable", "text/plain; charset=utf-8")
            return
        self.respond(200, content, content_type)

    def do_POST(self):
        self.respond(405, b"Read-only preview", "text/plain; charset=utf-8")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


def main():
    # No owner-claim mechanism exists yet: keep unauthenticated alpha status
    # local to the Pi unless an engineer explicitly opts into a specific
    # private IPv4 interface for an isolated manual development test.
    server = ThreadingHTTPServer((select_bind_address(), 8765), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
