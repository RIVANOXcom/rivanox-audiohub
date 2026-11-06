# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded, no-shell capture of local PipeWire command output.

Untrusted pw-dump metadata must never exhaust a Pi's RAM, disk, or console.
A nonzero exit retains its exit code; oversize, invalid UTF-8 and timeouts
fail closed. No stdout/stderr identifiers are logged or persisted.
"""
from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time

MAX_COMMAND_STDOUT_BYTES = 4 * 1024 * 1024
READ_CHUNK_BYTES = 65536


def bounded_command_output(argv, *, timeout=8, max_bytes=MAX_COMMAND_STDOUT_BYTES):
    """Return CompletedProcess with capped UTF-8 stdout, or None on failure.

    stdout is drained incrementally with selectors; using communicate() or
    capture_output=True would buffer all producer output before checking the
    limit. stderr is suppressed to avoid leaking device identifiers.
    """
    if (type(argv) not in (tuple, list) or not argv
            or any(type(arg) is not str or not arg or "\x00" in arg for arg in argv)
            or type(timeout) not in (int, float) or not 0 < timeout <= 60
            or type(max_bytes) is not int or not 0 < max_bytes <= MAX_COMMAND_STDOUT_BYTES):
        return None
    deadline = time.monotonic() + timeout
    child = None
    success = False
    try:
        child = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, start_new_session=True,
        )
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                events = selector.select(remaining)
                if not events:
                    return None
                for key, _ in events:
                    chunk = os.read(
                        key.fd, min(READ_CHUNK_BYTES, max_bytes + 1 - len(output))
                    )
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > max_bytes:
                        return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        returncode = child.wait(timeout=remaining)
        try:
            decoded = output.decode("utf-8")
        except UnicodeDecodeError:
            return None
        result = subprocess.CompletedProcess(("<audiohub-local-command>",), returncode, decoded, "")
        success = True
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    finally:
        if child is not None:
            if not success:
                # Own process group also handles descendants retaining stdout.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    try:
                        child.kill()
                    except ProcessLookupError:
                        pass
            if child.stdout is not None:
                child.stdout.close()
            try:
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
