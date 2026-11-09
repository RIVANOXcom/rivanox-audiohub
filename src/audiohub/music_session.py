# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in *local terminal* next/stop/status for Pi4 WAV playback.

No network endpoint, daemon, key bindings, IPC socket, file writes or
change to PipeWire routing. The operator must explicitly request BOTH
--play and --interactive from a trusted terminal. Commands require Enter.
Playback always targets the existing unprivileged audiohub.music sink.
"""
from __future__ import annotations

import math
import select
import sys
import threading
import time

from . import local_music

POLL_SECONDS = 0.15
QUIT_JOIN_SECONDS = 3.0
COMMAND_HELP = "Enter: [s] status, [n] next track, [q] stop and exit, [h] help."


def read_terminal_command(timeout=POLL_SECONDS, *, stream=None):
    """Return None when idle, or a single sanitized local command.

    EOF, lost terminal or failed select fails closed as quit. This does
    not put the terminal in raw mode and never echoes untrusted input.
    """
    stream = sys.stdin if stream is None else stream
    try:
        ready, _, _ = select.select([stream], [], [], timeout)
        if not ready:
            return None
        line = stream.readline(64)
    except (OSError, ValueError, EOFError, TypeError):
        return "q"
    if not line:
        return "q"
    if len(line) > 16:
        return "?"
    value = line.strip().lower()
    return value if value in ("s", "n", "q", "h") else "?"


def status_message(position, count, started_at, deadline, *, clock=time.monotonic):
    now = clock()
    elapsed = max(0, int(now - started_at))
    remaining = max(0, math.ceil(deadline - now))
    return ("Music track " + str(position) + "/" + str(count)
            + " | elapsed " + str(elapsed) + " s"
            + " | session remaining " + str(remaining) + " s"
            + " | local only; audio not physically verified.")


def run_session(paths, *, max_minutes=15, read_command=read_terminal_command,
                playback=None, clock=time.monotonic, out=print, require_tty=True):
    """Play a bounded private local selection with human-controlled track skip.

    The worker owns only the pw-cat player it starts. The main thread
    continues polling local keyboard commands and can terminate that
    child even if a pipe write blocks. No playback if there is no TTY.
    """
    if playback is None:
        playback = local_music.play_playlist
    report = local_music.inspect_playlist(paths, max_minutes=max_minutes)
    if require_tty and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise PermissionError("Interactive music requires a real operator terminal")
    if hasattr(local_music.os, "geteuid") and local_music.os.geteuid() == 0:
        raise PermissionError("Interactive music must run as unprivileged user")
    if not local_music.music_sink_available():
        raise RuntimeError("AudioHub music sink unavailable; no speaker fallback")

    start = clock()
    deadline = start + max_minutes * 60
    out("Interactive music session started locally. " + COMMAND_HELP)
    for position, path in enumerate(paths, 1):
        if clock() >= deadline:
            out("Session time limit reached. No new track started.")
            break
        cancelled = threading.Event()
        finished = threading.Event()
        lock = threading.Lock()
        active = [None]
        failures = []

        def on_player(child):
            with lock:
                active[0] = child
                if cancelled.is_set() and child.poll() is None:
                    child.terminate()

        def worker():
            try:
                playback([path], max_minutes=max_minutes,
                         stop=cancelled, session_deadline=deadline,
                         on_player=on_player, notify=lambda _: None)
            except InterruptedError:
                if not cancelled.is_set():
                    failures.append("interrupted")
            except (ValueError, OSError, RuntimeError, PermissionError,
                    TimeoutError, BrokenPipeError):
                failures.append("playback_failed")
            except BaseException:
                failures.append("playback_failed")
            finally:
                finished.set()

        thread = threading.Thread(target=worker, name="audiohub-local-music",
                                  daemon=True)
        thread.start()
        out(status_message(position, report["files"], start, deadline, clock=clock))

        def stop_owned_player():
            cancelled.set()
            with lock:
                child = active[0]
                if child is not None and child.poll() is None:
                    child.terminate()

        requested = None
        try:
            while not finished.is_set():
                if clock() >= deadline:
                    requested = "timeout"
                    break
                command = read_command(POLL_SECONDS)
                if command == "s":
                    out(status_message(position, report["files"], start,
                                       deadline, clock=clock))
                elif command == "h":
                    out(COMMAND_HELP)
                elif command in ("n", "q"):
                    requested = command
                    break
                elif command is not None:
                    out("Unknown local command. " + COMMAND_HELP)
        finally:
            if requested is not None or not finished.is_set():
                stop_owned_player()
            thread.join(timeout=QUIT_JOIN_SECONDS)
            if thread.is_alive():
                # The only process we may kill is this session's own child.
                with lock:
                    child = active[0]
                    if child is not None and child.poll() is None:
                        child.kill()
                thread.join(timeout=QUIT_JOIN_SECONDS)
            if thread.is_alive():
                raise RuntimeError("Local music player did not stop cleanly")

        if requested == "q":
            out("Music session stopped by operator; no settings were saved.")
            return False
        if requested == "timeout":
            out("Music session time limit reached. Playback stopped.")
            return False
        if failures and requested != "n":
            raise RuntimeError("Local music player failed; no file paths disclosed")
        if requested == "n":
            out("Track skipped. No private filename was displayed.")
            continue
        out("Track " + str(position) + "/" + str(report["files"]) + " finished.")

    out("Local music session ended. Sound and hardware are NOT automatically verified.")
    return True
