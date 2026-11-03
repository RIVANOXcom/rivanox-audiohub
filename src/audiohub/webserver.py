# SPDX-License-Identifier: AGPL-3.0-only
"""Minimal read-only local health page for unverified AudioHub images.

No device-management APIs are exposed here. No authentication secrets, Bluetooth
device addresses or audio source identifiers are returned. Never add mutation
handlers without first completing the secure device-ownership design.
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .runtime import STATE, read_json

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
    return {
        "fresh": True,
        "usb_connected": status.get("usb_output") is True,
        "active_routes": _small_nonnegative(status.get("active_routes"), 3),
        "bluetooth_sources": _small_nonnegative(status.get("bluetooth_source_count"), 2),
        "virtual_channel_count": len(set(ch for ch in channels if ch in ("music", "laptop", "tablet"))),
    }


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
            body = json.dumps(public_status(read_json(STATE, {})), separators=(",", ":")).encode()
            self.respond(200, body, "application/json; charset=utf-8")
            return
        if path not in ALLOWED:
            self.respond(404, b"Not found", "text/plain; charset=utf-8")
            return
        filename, content_type = ALLOWED[path]
        try:
            content = (WEBROOT / filename).read_bytes()
        except OSError:
            self.respond(503, b"Static resources not installed", "text/plain; charset=utf-8")
            return
        self.respond(200, content, content_type)

    def do_POST(self):
        self.respond(405, b"Read-only preview", "text/plain; charset=utf-8")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


def main():
    # Local LAN prototype, deliberately unauthenticated read-only API only.
    # No WAN / port-forwarding deployment is supported.
    server = ThreadingHTTPServer(("0.0.0.0", 8765), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
