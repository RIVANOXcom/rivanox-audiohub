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
MAX_DEFERRED_TRACKS = 8  # volatile only, no new player or disk storage
COMMAND_HELP = ("Enter: [u] pause/resume, [m] repeat off/track/all, [s] status, "
                "[l] queue, [e] end after current track (toggle), "
                "[k1-k8] replace NEXT, [a1-a8] append (max 8), "
                "[z] undo last pending, [k0] clear pending, "
                "[d1-d8] delete pending SLOT, [f1-f8] move SLOT to NEXT, "
                "[n] next, [p] previous, [r] replay, "
                "[1-8] jump, [q] quit now, [h] help.")


def next_repeat_mode(mode):
    """Cycle local replay policy without persistence or changing the player."""
    choices = ("off", "track", "all")
    if type(mode) is not str or mode not in choices:
        raise ValueError("Invalid local repeat mode")
    return choices[(choices.index(mode) + 1) % len(choices)]


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
    allowed = ("u", "m", "s", "l", "e", "n", "p", "r", "q", "h", "z",
               "1", "2", "3", "4", "5", "6", "7", "8",
               "k0", "k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8",
               "a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8",
               "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8",
               "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8")
    return value if value in allowed else "?"


def _validate_deferred_tracks(count, queued_next, queued_after):
    """Validate bounded anonymous numbers before status, preview or playback."""
    if (type(count) is not int or not 1 <= count <= local_music.MAX_FILES or
            type(queued_after) not in (tuple, list) or
            len(queued_after) >= MAX_DEFERRED_TRACKS or
            (queued_next is None and bool(queued_after))):
        raise ValueError("Invalid deferred local music queue")
    numbers = (() if queued_next is None else (queued_next,)) + tuple(queued_after)
    if (len(numbers) > MAX_DEFERRED_TRACKS or
            any(type(number) is not int or not 1 <= number <= count
                for number in numbers)):
        raise ValueError("Invalid anonymous deferred track")
    return numbers


def status_message(position, count, started_at, deadline, *, clock=time.monotonic,
                   paused=False, repeat_mode="off", end_after_track=False,
                   queued_next=None, queued_after=()):
    if repeat_mode not in ("off", "track", "all") or type(end_after_track) is not bool:
        raise ValueError("Unknown local repeat/end mode")
    slots = _validate_deferred_tracks(count, queued_next, queued_after)
    now = clock()
    elapsed = max(0, int(now - started_at))
    remaining = max(0, math.ceil(deadline - now))
    return ("Music track " + str(position) + "/" + str(count)
            + " | elapsed " + str(elapsed) + " s"
            + " | session remaining " + str(remaining) + " s"
            + (" | PAUSED (owned player only)" if paused else "")
            + (" | repeating " + repeat_mode if repeat_mode != "off" else "")
            + (" | END AFTER THIS TRACK" if end_after_track else "")
            + (" | QUEUED NEXT TRACK " + str(queued_next)
               if queued_next is not None else "")
            + (" | FOLLOWING TRACKS " + ", ".join(map(str, queued_after))
               if queued_after else "")
            + (" | PENDING SLOTS " +
               ", ".join(f"{i}=track {n}" for i, n in enumerate(slots, 1))
               if slots else "")
            + " | local only; audio not physically verified.")


def track_progress_message(duration_ms, elapsed_seconds, *, paused=False):
    """Readable per-track estimate from WAV header and owned-player clock.

    This is NOT a PCM cursor, loudness meter or proof of sound reaching the
    output. Pause time is excluded by the caller. No private titles/paths.
    """
    if (type(duration_ms) is not int or
            not 0 < duration_ms <= local_music.MAX_SECONDS * 1000 or
            type(elapsed_seconds) not in (int, float) or
            elapsed_seconds < 0 or
            (type(elapsed_seconds) is float and not math.isfinite(elapsed_seconds)) or
            type(paused) is not bool):
        raise ValueError("Invalid anonymous track-timing estimate")
    total = (duration_ms + 999) // 1000
    elapsed = min(total, int(elapsed_seconds) if elapsed_seconds < total else total)
    left = total - elapsed

    def mmss(seconds):
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes:02d}:{remainder:02d}"

    return ("Estimated WAV track: " + mmss(elapsed) + " elapsed / " +
            mmss(total) + " header duration; approximately " + mmss(left) +
            " remaining" + (" (PAUSED)" if paused else "") +
            ". Owned-player clock only, not measured PCM position or sound.")


def queue_message(report, position, *, repeat_mode="off",
                  end_after_track=False, queued_next=None, queued_after=()):
    """Anonymous user-facing snapshot of the selected local music queue.

    The displayed durations come only from prechecked WAV headers, not
    from hardware playback, and never include filenames or identities.
    """
    if repeat_mode not in ("off", "track", "all") or type(end_after_track) is not bool:
        raise ValueError("Unknown local repeat/end mode")
    if (not isinstance(report, dict) or
            type(report.get("files")) is not int or
            type(position) is not int or
            not 1 <= position <= report["files"] <= local_music.MAX_FILES or
            len(report.get("tracks", ())) != report["files"]):
        raise ValueError("Invalid selected local music queue")
    slots = _validate_deferred_tracks(report["files"], queued_next, queued_after)
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
            ", ".join(chunks) + "; * = selected. No private titles."
            + (" Repeat: " + repeat_mode + "." if repeat_mode != "off" else "")
            + (" End after current track ARMED." if end_after_track else "")
            + (" Queued NEXT: track " + str(queued_next) + "."
               if queued_next is not None else "")
            + (" Following: " + ", ".join("track " + str(n)
                                          for n in queued_after) + "."
               if queued_after else "")
            + (" Pending slots (1=NEXT): " +
               ", ".join(f"{i}=track {n}" for i, n in enumerate(slots, 1)) +
               "." if slots else " Pending slots: empty."))


def run_session(paths, *, max_minutes=15, read_command=read_terminal_command,
                playback=None, clock=time.monotonic, out=print, require_tty=True,
                level="normal", channel="both"):
    """Play a bounded private local queue with human-controlled navigation.

    The worker owns only the pw-cat player it starts. The main thread
    continues polling local keyboard commands and can terminate that
    child even if a pipe write blocks. No playback if there is no TTY.
    """
    if playback is None:
        playback = local_music.play_playlist
    # A strict local-only gain cap; validate even when using an injected player.
    local_music.stream_gain(level)
    report = local_music.inspect_playlist(paths, max_minutes=max_minutes)
    local_music.validate_stereo_channel(channel, report)
    if require_tty and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise PermissionError("Interactive music requires a real operator terminal")
    if hasattr(local_music.os, "geteuid") and local_music.os.geteuid() == 0:
        raise PermissionError("Interactive music must run as unprivileged user")
    if not local_music.music_sink_available():
        raise RuntimeError("AudioHub music sink unavailable; no speaker fallback")

    start = clock()
    deadline = start + max_minutes * 60
    out("Interactive music session started locally at " + level.upper() +
        " stream level, " + channel.upper() + " stereo channel selection "
        "(not calibrated speaker loudness or actual hardware verification). "
        + COMMAND_HELP)
    position = 1
    repeat_mode = "off"  # volatile, this session only; never saved
    end_after_track = False  # one current-track natural ending; never persists
    queued_next = None  # first anonymous deferred choice; no saved files
    queued_after = []  # at most 7 more choices, only during this session
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
        player_started = [None]  # monotonic time only after owned child exists
        pause_started = [None]
        pause_total = [0.0]  # current track only, not persisted
        failures = []

        def on_player(child):
            with lock:
                active[0] = child
                if player_started[0] is None:
                    player_started[0] = clock()
                if cancelled.is_set() and child.poll() is None:
                    child.terminate()
                elif paused[0] and child.poll() is None:
                    # A local pause command can arrive before pw-cat spawns.
                    # Apply it to the newly owned child, never PipeWire itself.
                    child.send_signal(signal.SIGSTOP)
                    pause_started[0] = clock()

        def worker():
            try:
                kwargs = {"max_minutes": max_minutes,
                          "stop": cancelled, "session_deadline": deadline,
                          "on_player": on_player, "notify": lambda _: None}
                if level != "normal":
                    kwargs["level"] = level
                if channel != "both":
                    kwargs["channel"] = channel
                playback([path], **kwargs)
            except InterruptedError:
                if not cancelled.is_set():
                    failures.append("interrupted")
            except (ValueError, OSError, RuntimeError, PermissionError,
                    TimeoutError, BrokenPipeError):
                # The operator's explicit navigation/quit terminates ONLY
                # the owned child. A resulting broken pipe is an expected
                # consequence, not a new spontaneous hardware failure.
                if not cancelled.is_set():
                    failures.append("playback_failed")
            except BaseException:
                if not cancelled.is_set():
                    failures.append("playback_failed")
            finally:
                finished.set()

        thread = threading.Thread(target=worker, name="audiohub-local-music",
                                  daemon=True)
        thread.start()
        out(status_message(position, report["files"], start, deadline,
                           clock=clock, repeat_mode=repeat_mode,
                           end_after_track=end_after_track,
                           queued_next=queued_next,
                           queued_after=queued_after))

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
                now = clock()
                if want_pause:
                    if player_started[0] is not None:
                        pause_started[0] = now
                elif pause_started[0] is not None:
                    pause_total[0] += max(0.0, now - pause_started[0])
                    pause_started[0] = None
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
                        observed_start = player_started[0]
                        child = active[0]
                        # A terminated player is not still progressing.
                        # Never infer audible PCM output from our clock.
                        try:
                            exited = child is not None and child.poll() is not None
                        except OSError:
                            exited = True
                        now = clock()
                        stopped_time = pause_total[0]
                        if pause_started[0] is not None:
                            stopped_time += max(0.0, now - pause_started[0])
                    out(status_message(position, report["files"], start,
                                       deadline, clock=clock, paused=is_paused,
                                       repeat_mode=repeat_mode,
                                       end_after_track=end_after_track,
                                       queued_next=queued_next,
                                       queued_after=queued_after))
                    if exited:
                        out("Owned music player has exited; track estimate "
                            "unavailable until playback completion is checked. "
                            "No hardware sound verified.")
                    elif observed_start is None:
                        out("Track estimate pending until our local player starts. "
                            "No audible hardware output verified.")
                    else:
                        seconds = max(0.0, now - observed_start - stopped_time)
                        out(track_progress_message(
                            report["tracks"][position - 1]["duration_ms"],
                            seconds, paused=is_paused))
                elif command == "u":
                    result = toggle_pause()
                    if result is None:
                        out("Player unavailable; pause/resume was NOT applied.")
                    else:
                        out("Owned local music player PAUSED; session time limit continues."
                            if result else
                            "Owned local music player RESUMED; no settings changed.")
                elif command == "h":
                    out(COMMAND_HELP)
                elif command == "e":
                    end_after_track = not end_after_track
                    if end_after_track and queued_next is not None:
                        queued_next = None
                        queued_after.clear()
                        out("Queued-next selection cleared: end-after-current "
                            "takes priority, no further WAV starts.")
                    out("END AFTER THIS TRACK ARMED: current owned player "
                        "continues to its natural finish; no next/repeat track."
                        if end_after_track else
                        "End-after-track cancelled; queue and repeat continue. "
                        "No settings saved.")
                elif command in ("k0", "k1", "k2", "k3", "k4",
                                 "k5", "k6", "k7", "k8"):
                    if command == "k0":
                        queued_next = None
                        queued_after.clear()
                        out("Queued-next selection cleared; normal queue "
                            "and repeat apply. Current WAV uninterrupted.")
                    elif int(command[1]) > report["files"]:
                        out("Next-track number outside this selected queue. "
                            "Current WAV and next selection unchanged.")
                    else:
                        queued_next = int(command[1])
                        queued_after.clear()  # kN replaces the full pending plan
                        if end_after_track:
                            end_after_track = False
                            out("End-after-this-track cancelled: another "
                                "next track was explicitly selected.")
                        out("Queued NEXT: track " + str(queued_next) +
                            " after this WAV ends naturally. Current owned "
                            "player uninterrupted; private titles hidden.")
                elif command in ("a1", "a2", "a3", "a4", "a5",
                                 "a6", "a7", "a8"):
                    number = int(command[1])
                    if number > report["files"]:
                        out("Append number outside this selected queue. "
                            "Existing plan and playing WAV unchanged.")
                    elif queued_next is not None and len(queued_after) + 1 >= MAX_DEFERRED_TRACKS:
                        out("Pending queue full (8 tracks); unchanged. "
                            "Use z to undo last or k0 to clear.")
                    else:
                        if queued_next is None:
                            queued_next = number
                        else:
                            queued_after.append(number)
                        if end_after_track:
                            end_after_track = False
                            out("End-after-this-track cancelled: a following "
                                "track was explicitly appended.")
                        out("Appended deferred track " + str(number) +
                            "; " + str(1 + len(queued_after)) +
                            " pending. Current WAV uninterrupted; "
                            "private titles hidden.")
                elif command == "z":
                    if queued_after:
                        queued_after.pop()
                        out("Undid last appended track. " +
                            str(1 + len(queued_after)) + " still pending.")
                    elif queued_next is not None:
                        queued_next = None
                        out("Undid last queued track. Pending queue empty; "
                            "normal order and repeat resume.")
                    else:
                        out("Pending queue already empty; no playback changed.")
                elif command in ("d1", "d2", "d3", "d4", "d5",
                                 "d6", "d7", "d8", "f1", "f2", "f3",
                                 "f4", "f5", "f6", "f7", "f8"):
                    # The digit is a pending SLOT (as shown by l), not a
                    # selected WAV number. Only volatile state is edited.
                    slot = int(command[1])
                    pending = list(_validate_deferred_tracks(
                        report["files"], queued_next, queued_after))
                    if slot > len(pending):
                        out("Pending slot " + str(slot) +
                            " unavailable; no change to the queue or "
                            "current owned player.")
                    else:
                        number = pending.pop(slot - 1)
                        if command[0] == "f":
                            pending.insert(0, number)
                            if slot == 1:
                                out("Pending slot 1 is already NEXT; current "
                                    "owned WAV uninterrupted.")
                            else:
                                out("Moved pending slot " + str(slot) +
                                    " to NEXT (selected track " + str(number) +
                                    "); remaining order preserved. "
                                    "Current WAV uninterrupted.")
                        else:
                            out("Removed pending slot " + str(slot) +
                                " (selected track " + str(number) +
                                "); other choices preserved. "
                                "Current WAV uninterrupted.")
                        queued_next = pending[0] if pending else None
                        queued_after = pending[1:]
                elif command == "m":
                    repeat_mode = next_repeat_mode(repeat_mode)
                    out("Local repeat mode: " + repeat_mode.upper()
                        + "; limited by the original session deadline.")
                elif command == "l":
                    out(queue_message(report, position,
                                      repeat_mode=repeat_mode,
                                      end_after_track=end_after_track,
                                      queued_next=queued_next,
                                      queued_after=queued_after))
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
        if failures:
            # Do not let a nearly simultaneous NEXT/PREVIOUS/REPLAY/JUMP
            # conceal an already failed pw-cat and start more audio.
            # Failure messages are fixed and cannot leak a private WAV path,
            # subprocess stderr, device identity or owner information.
            out("LOCAL PLAYBACK FAILED: no next, repeated or jumped track "
                "started. Check the private audiohub.music input and "
                "installed pw-cat tool before a separate manual retry. "
                "No default sound-output fallback or settings changed.")
            raise RuntimeError("Local music player failed; no file paths disclosed")
        # Explicit navigation selects another playback attempt and disarms
        # the old-track finish policy, avoiding a surprising premature end.
        if end_after_track and (requested in ("n", "p", "r") or
                                (isinstance(requested, tuple) and requested[0] == "jump")):
            end_after_track = False
            out("End-after-track cancelled by manual navigation; "
                "the new track keeps the session deadline.")
        if queued_next is not None and (requested in ("n", "p", "r") or
                                        (isinstance(requested, tuple) and
                                         requested[0] == "jump")):
            queued_next = None
            queued_after.clear()
            out("Queued-next selection cleared by immediate navigation. "
                "New track follows the operator's direct command.")
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
        if end_after_track:
            out("End-after-track completed after natural player finish. "
                "No next or repeated track started; no settings saved.")
            break
        if queued_next is not None:
            position = queued_next
            queued_next = queued_after.pop(0) if queued_after else None
            out("Playing queued NEXT track " + str(position) +
                " after natural completion; " +
                str((1 if queued_next is not None else 0) + len(queued_after)) +
                " deferred track(s) remain. Private titles hidden.")
            continue
        if repeat_mode == "track":
            out("Repeating current selected track until mode or deadline changes.")
            continue
        position += 1
        if position > report["files"] and repeat_mode == "all" and clock() < deadline:
            position = 1
            out("Repeating selected queue; no settings or private names saved.")

    out("Local music session ended. Sound and hardware are NOT automatically verified.")
    return True
