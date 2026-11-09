# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in *local terminal* private music queue navigation for Pi4 WAV playback.

No network endpoint, daemon, key bindings, IPC socket, file writes or
change to PipeWire routing. The operator must explicitly request BOTH
--play and --interactive from a trusted terminal. Commands require Enter.
Playback always targets the existing unprivileged audiohub.music sink.
"""
from __future__ import annotations

import math
import select
import signal
import sys
import threading
import time

from . import local_music

POLL_SECONDS = 0.15
QUIT_JOIN_SECONDS = 3.0
COMMAND_HELP = ("Enter: [u] pause/resume, [s] status, [l] queue, [n] next, "
                "[p] previous, [r] replay, [1-8] jump, [q] quit, [h] help.")


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
    return value if value in ("u", "s", "l", "n", "p", "r", "q", "h",
                              "1", "2", "3", "4", "5", "6", "7", "8") else "?"


def status_message(position, count, started_at, deadline, *, clock=time.monotonic,
                   paused=False):
    now = clock()
    elapsed = max(0, int(now - started_at))
    remaining = max(0, math.ceil(deadline - now))
    return ("Music track " + str(position) + "/" + str(count)
            + " | elapsed " + str(elapsed) + " s"
            + " | session remaining " + str(remaining) + " s"
            + (" | PAUSED (owned player only)" if paused else "")
            + " | local only; audio not physically verified.")


def queue_message(report, position):
    """Anonymous user-facing snapshot of the selected local music queue.

    The displayed durations come only from prechecked WAV headers, not
    from hardware playback, and never include filenames or identities.
    """
    if (not isinstance(report, dict) or
            type(report.get("files")) is not int or
            type(position) is not int or
            not 1 <= position <= report["files"] <= local_music.MAX_FILES or
            len(report.get("tracks", ())) != report["files"]):
        raise ValueError("Invalid selected local music queue")
    chunks = []
    for number, track in enumerate(report["tracks"], 1):
        duration = track["duration_ms"]
        if type(duration) is not int or not 0 < duration <= local_music.MAX_SECONDS * 1000:
            raise ValueError("Invalid selected music duration")
        seconds = (duration + 999) // 1000
        minutes, rest = divmod(seconds, 60)
        marker = "*" if number == position else ""
        chunks.append(str(number) + marker + "=" +
                      f"{minutes:02d}:{rest:02d}")
    return ("Selected WAV queue: track " + str(position) + "/" +
            str(report["files"]) + "; durations (NOT live progress): " +
            ", ".join(chunks) + "; * = selected. No private titles.")


def run_session(paths, *, max_minutes=15, read_command=read_terminal_command,
                playback=None, clock=time.monotonic, out=print, require_tty=True):
    """Play a bounded private local queue with human-controlled navigation.

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
    position = 1
    while position <= report["files"]:
        path = paths[position - 1]
        if clock() >= deadline:
            out("Session time limit reached. No new track started.")
            break
        cancelled = threading.Event()
        finished = threading.Event()
        lock = threading.Lock()
        active = [None]
        paused = [False]  # guarded by lock; never signals unrelated processes
        failures = []

        def on_player(child):
            with lock:
                active[0] = child
                if cancelled.is_set() and child.poll() is None:
                    child.terminate()
                elif paused[0] and child.poll() is None:
                    # A local pause command can arrive before pw-cat spawns.
                    # Apply it to the newly owned child, never PipeWire itself.
                    child.send_signal(signal.SIGSTOP)

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
                was_paused = paused[0]
                paused[0] = False
                if child is not None and child.poll() is None:
                    if was_paused:
                        # A stopped POSIX process cannot run its ordinary
                        # termination handler until SIGCONT has been sent.
                        try:
                            child.send_signal(signal.SIGCONT)
                        except OSError:
                            pass  # kill fallback below, only this child
                    try:
                        child.terminate()
                    except OSError:
                        pass  # can race with natural track completion

        def toggle_pause():
            with lock:
                child = active[0]
                want_pause = not paused[0]
                if child is not None:
                    if child.poll() is not None:
                        return None
                    try:
                        child.send_signal(signal.SIGSTOP if want_pause
                                          else signal.SIGCONT)
                    except OSError:
                        # A disappearing child cannot be marked paused.
                        return None
                paused[0] = want_pause
                return want_pause

        requested = None
        try:
            while not finished.is_set():
                if clock() >= deadline:
                    requested = "timeout"
                    break
                command = read_command(POLL_SECONDS)
                if command == "s":
                    with lock:
                        is_paused = paused[0]
                    out(status_message(position, report["files"], start,
                                       deadline, clock=clock, paused=is_paused))
                elif command == "u":
                    result = toggle_pause()
                    if result is None:
                        out("Track already ended; pause/resume not applied.")
                    else:
                        out("Owned local music player PAUSED; session time limit continues."
                            if result else
                            "Owned local music player RESUMED; no settings changed.")
                elif command == "h":
                    out(COMMAND_HELP)
                elif command == "l":
                    out(queue_message(report, position))
                elif command in ("n", "p", "r", "q"):
                    requested = command
                    break
                elif command in ("1", "2", "3", "4", "5", "6", "7", "8"):
                    if int(command) > report["files"]:
                        out("Track number outside this local queue. " + COMMAND_HELP)
                    else:
                        requested = ("jump", int(command))
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
        if failures and requested not in ("n", "p", "r") and not (isinstance(requested, tuple) and requested[0] == "jump"):
            raise RuntimeError("Local music player failed; no file paths disclosed")
        if requested == "n":
            out("Track skipped. No private filename was displayed.")
            position += 1
            continue
        if requested == "p":
            position = max(1, position - 1)
            out("Playing prior selected track (or replaying track 1). No private filename.")
            continue
        if requested == "r":
            out("Replaying selected track. No private filename.")
            continue
        if isinstance(requested, tuple) and requested[0] == "jump":
            position = requested[1]
            out("Jumping to selected queue track " + str(position) + ". No filename.")
            continue
        out("Track " + str(position) + "/" + str(report["files"]) + " finished.")
        position += 1

    out("Local music session ended. Sound and hardware are NOT automatically verified.")
    return True
