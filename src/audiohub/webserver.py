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
import threading
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
MAX_STATUS_CLIENTS = 8
CLIENT_READ_TIMEOUT_SECONDS = 5



def _bounded_regular_bytes(path, limit, *, private_owner=None):
    """Open every path component with O_NOFOLLOW and read at most 'limit'.

    Never follow WEBROOT/asset/status symlinks outside the Pi image. This
    also refuses FIFOs/devices, unexpectedly large assets and status JSON,
    incomplete reads and non-absolute paths. The path comes from a fixed
    allowlist or the runtime's own state path, not the HTTP request.
    """
    path = Path(path)
    if (not path.is_absolute() or ".." in path.parts
            or len(path.parts) < 2 or type(limit) is not int or limit <= 0
            or (private_owner is not None and
                (type(private_owner) is not int or private_owner < 0))):
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
        if private_owner is not None:
            # Static assets are root-owned and world-readable by design.
            # Only live runtime status is a private owner-authored file.
            parent = os.fstat(directory)
            if (not stat.S_ISDIR(parent.st_mode)
                    or parent.st_uid != private_owner
                    or stat.S_IMODE(parent.st_mode) & 0o077):
                return None
        file_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory,
        )
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            return None
        if private_owner is not None and (
                info.st_uid != private_owner or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077):
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


def _unique_json_object(pairs):
    """Reject ambiguous status snapshots with repeated object member names."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate status JSON member")
        result[key] = value
    return result


def _reject_json_constant(_value):
    """RFC 8259 has no NaN or Infinity; never accept them as health data."""
    raise ValueError("non-finite status JSON number")


def read_public_status(*, path=None, now=None):
    """Read a bounded, non-symlinked runtime state file, never raw secrets."""
    body = _bounded_regular_bytes(
        STATE if path is None else path, STATUS_MAX_BYTES,
        private_owner=os.geteuid(),
    )
    if body is None:
        return public_status({}, now=now)
    try:
        decoded = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        # Deeply nested but size-bounded JSON must not crash a status handler.
        decoded = {}
    return public_status(decoded, now=now)


class BoundedStatusHTTPServer(ThreadingHTTPServer):
    """Cap untrusted status-preview requests without authenticating anyone.

    A ThreadingHTTPServer otherwise allocates one thread per accepted socket.
    The alpha UI defaults to loopback; explicit insecure LAN opt-in still
    must not permit unlimited threads or indefinitely stalled clients.
    """
    daemon_threads = True
    request_queue_size = MAX_STATUS_CLIENTS

    def __init__(self, address, handler):
        self._client_slots = threading.BoundedSemaphore(MAX_STATUS_CLIENTS)
        super().__init__(address, handler)

    def get_request(self):
        conn, addr = super().get_request()
        try:
            conn.settimeout(CLIENT_READ_TIMEOUT_SECONDS)
        except (OSError, ValueError):
            conn.close()
            raise
        return conn, addr

    def process_request(self, request, client_address):
        if not self._client_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._client_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._client_slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "AudioHub-Preview"
    sys_version = ""

    def log_message(self, format, *args):
        """Never log raw HTTP paths, query strings, or guessed peer IDs.

        BaseHTTPRequestHandler would otherwise echo an attacker-controlled
        request line to the systemd journal. This alpha service has no
        authenticated request audit trail and must not collect such values.
        """
        return None

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
        try:
            path = urlsplit(self.path).path
        except ValueError:
            # Invalid absolute request targets (such as malformed IPv6) are
            # never valid allowlisted routes and must not crash the worker.
            self.respond(404, b"Not found", "text/plain; charset=utf-8")
            return
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
    server = BoundedStatusHTTPServer((select_bind_address(), 8765), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
