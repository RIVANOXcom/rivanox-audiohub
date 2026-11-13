# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded local music-folder picker for the unprivileged Pi4 WAV player.

Only the authorized local operator can select a readable private directory.
No media bytes leave this module, no UI or network listener is created, and
file names are hidden unless the operator explicitly opts into local display.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import unicodedata

from . import local_music

MAX_SCANNED = 256
MAX_DISPLAYED = 40
MAX_NAME_CHARS = 48


def _private_directory(path):
    if type(path) is not str and not isinstance(path, Path):
        raise ValueError("Provide an absolute local music folder")
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts or p.is_symlink():
        raise ValueError("Provide an absolute real music folder, not a link")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(p, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise PermissionError("Music folder must not be group/world writable")
        # Refuse a raced replacement at the requested final directory path.
        now = os.lstat(p)
        if (not stat.S_ISDIR(now.st_mode) or now.st_ino != info.st_ino
                or now.st_dev != info.st_dev):
            raise ValueError("Music folder changed while opening")
        return fd, p
    except BaseException:
        os.close(fd)
        raise


def discover_library(path):
    """Return at most 40 valid numbered WAV entries, no recursion or writes.

    A directory with over 256 entries is refused rather than partially
    enumerated, so an operator never mistakes an incomplete listing for
    the full library. Invalid/linked WAVs are ignored and counted, not
    printed with their private names.
    """
    fd, folder = _private_directory(path)
    items = []
    excluded = 0
    examined = 0
    try:
        with os.scandir(fd) as entries:
            for entry in entries:
                examined += 1
                if examined > MAX_SCANNED:
                    raise ValueError("Too many folder entries; select a smaller folder")
                if not entry.name.lower().endswith(".wav") or entry.name.startswith("."):
                    continue
                if not entry.is_file(follow_symlinks=False):
                    excluded += 1
                    continue
                filename = folder / entry.name
                try:
                    meta = local_music._open_wav(filename)
                except (OSError, ValueError):
                    excluded += 1
                    continue
                items.append((filename, meta))
                if len(items) > MAX_DISPLAYED:
                    raise ValueError("More than 40 playable WAVs; select a smaller folder")
    except (OSError, UnicodeError) as exc:
        raise ValueError("Cannot inspect this local music folder") from exc
    finally:
        os.close(fd)
    items.sort(key=lambda record: (record[0].name.casefold(), record[0].name))
    if not items:
        raise ValueError("No supported local WAV tracks in folder")
    return items, excluded


def parse_track_numbers(selection, available):
    """Require an explicit, bounded, unique 1-based comma-separated choice."""
    if (type(selection) is not str or not 1 <= len(selection) <= 64
            or type(available) is not int or not 1 <= available <= MAX_DISPLAYED):
        raise ValueError("Select 1–8 displayed track numbers")
    values = selection.split(",")
    if not 1 <= len(values) <= local_music.MAX_FILES:
        raise ValueError("Choose 1–8 track numbers")
    result = []
    for raw in values:
        number = raw.strip()
        if (not number or not number.isascii() or not number.isdecimal()
                or len(number) > 2 or number.startswith("0")):
            raise ValueError("Use numbers from the local WAV list, e.g. 1,3")
        index = int(number) - 1
        if index < 0 or index >= available or index in result:
            raise ValueError("Track choice out of range or duplicated")
        result.append(index)
    return result


def _safe_local_title(stem):
    """Sanitize terminal control, bidi, unprintable and escape sequences."""
    name = unicodedata.normalize("NFC", stem)
    safe = []
    for char in name[:MAX_NAME_CHARS]:
        group = unicodedata.category(char)[0]
        if group in ("L", "N") or char in " .,_()-+":
            safe.append(char)
        else:
            safe.append("_")
    value = "".join(safe).strip(" ._")
    if not value:
        value = "untitled"
    if len(name) > MAX_NAME_CHARS:
        value += "…"
    return value


def display_library(items, *, show_titles=False, guided=False):
    """Non-persistent terminal view. Private titles need explicit local opt-in."""
    if type(show_titles) is not bool or type(guided) is not bool:
        raise ValueError("Invalid library display option")
    lines = ["Local music library: " + str(len(items))
             + " valid WAV track(s). No playback started."]
    for n, (path, info) in enumerate(items, 1):
        seconds = (info["duration_ms"] + 999) // 1000
        minutes, rest = divmod(seconds, 60)
        channels = "stereo" if info["channels"] == 2 else "mono"
        label = ("Track " + str(n) + " · "
                 + f"{minutes:02d}:{rest:02d}"
                 + " · " + channels + " · " + str(info["rate"]) + " Hz")
        if show_titles:
            label += " · " + _safe_local_title(path.stem)
        lines.append(label)
    lines.append("Names hidden unless --show-titles is explicitly selected."
                 if not show_titles else
                 "Titles are visible only in THIS local terminal; do not share a transcript.")
    lines.append("Next: choose numbers, ALL (up to 8), or SHUFFLE (time-bounded)."
                 " Review the anonymous order before exact PLAY; no autoplay."
                 if guided else
                 "Choose up to 8 displayed numbers using --tracks 1,3; "
                 "then add --play only when ready.")
    return "\n".join(lines)


def selected_paths(items, selection, *, max_minutes):
    indices = parse_track_numbers(selection, len(items))
    paths = [items[i][0] for i in indices]
    report = local_music.inspect_playlist(paths, max_minutes=max_minutes)
    return paths, report



def guided_choice(items, reply, *, max_minutes, shuffle=None):
    """Resolve manual, ALL or SHUFFLE selection without starting audio.

    SHUFFLE samples a fresh private order from the *already listed* WAVs
    and greedily fits up to eight into the existing total session time.
    The resulting choices are returned as display numbers as well as
    paths, so the operator can review or change before confirming PLAY.
    """
    if type(reply) is not str or not 1 <= len(reply) <= 64:
        raise ValueError("Choose displayed track numbers or ALL/SHUFFLE")
    if type(max_minutes) is not int or not 1 <= max_minutes <= 30:
        raise ValueError("Select a bounded music session")
    if reply == "ALL":
        if len(items) > local_music.MAX_FILES:
            raise ValueError("ALL is limited to eight WAVs; choose numbers")
        indices = list(range(len(items)))
    elif reply == "SHUFFLE":
        import secrets
        indices = list(range(len(items)))
        if shuffle is None:
            secrets.SystemRandom().shuffle(indices)
        else:
            shuffle(indices)
        chosen = []
        duration = 0
        limit_ms = min(local_music.MAX_SECONDS, max_minutes * 60) * 1000
        for index in indices:
            track_ms = items[index][1]["duration_ms"]
            if (type(track_ms) is int and track_ms > 0 and
                    duration + track_ms <= limit_ms):
                chosen.append(index)
                duration += track_ms
            if len(chosen) == local_music.MAX_FILES:
                break
        if not chosen:
            raise ValueError("No WAV tracks fit the chosen session time")
        indices = chosen
    else:
        indices = parse_track_numbers(reply, len(items))
    if not indices:
        raise ValueError("No selected tracks")
    # selected_paths revalidates every input WAV for the actual
    # recording format and maximum play time before any confirmation.
    numbers = ",".join(str(index + 1) for index in indices)
    paths, preview = selected_paths(items, numbers, max_minutes=max_minutes)
    return paths, preview, numbers



def _terminal_line():
    """Read one bounded operator response; never log or echo its contents."""
    try:
        value = __import__("sys").stdin.readline(65)
    except (OSError, UnicodeError, ValueError, EOFError):
        return None
    if not value or len(value) > 64 or not value.endswith("\n"):
        return None
    return value[:-1].rstrip("\r")


def guided_session(folder, *, max_minutes=15, show_titles=False,
                   read_line=None, out=None, runner=None, level="normal"):
    """One-command guided local picker with bounded revision and PLAY gate.

    ALL selects a small album; SHUFFLE prepares a short anonymous queue;
    CHANGE returns to selection at most twice. Nothing starts until the
    operator reviews the numbered order and enters exact uppercase PLAY.
    """
    import sys
    # No unbounded pw-cat volume flag may be passed by the launcher or CLI.
    local_music.stream_gain(level)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PermissionError("Guided music requires a local operator terminal")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("Guided music requires an unprivileged user")
    if read_line is None:
        read_line = _terminal_line
    if out is None:
        out = print
    if runner is None:
        from . import music_session
        runner = music_session.run_session

    entries, skipped = discover_library(folder)
    out(display_library(entries, show_titles=show_titles, guided=True))
    if skipped:
        out(str(skipped) + " unsafe or unsupported WAV entries skipped.")
    out("GUIDED LOCAL MODE: Nothing is playing. No playlist is stored.")
    changes = 0
    while True:
        selected = None
        for attempt in range(3):
            out("Enter 1-8 distinct numbers (2,1), ALL (up to 8), or SHUFFLE."
                " SHUFFLE chooses up to 8 within session time."
                " Enter alone cancels; no audio starts yet:")
            reply = read_line()
            if reply is None or reply == "":
                out("Music selection cancelled. No playback started.")
                return False
            try:
                selected, details, numbers = guided_choice(
                    entries, reply, max_minutes=max_minutes)
                break
            except (ValueError, OSError, TypeError, IndexError):
                out("Invalid selection or duration. No playback started.")
        if selected is None:
            out("Selection limit reached. No playback started.")
            return False

        out("Selected library track numbers: " + numbers
            + " (private filenames hidden).")
        out("Selected " + str(details["files"]) + " WAV track(s), total "
            + str(details["total_duration_ms"] // 1000)
            + " s. Stream level " + level.upper() +
            " (not calibrated speaker loudness). Verify a low physical speaker volume.")
        out("Type exact uppercase PLAY then Enter to play; CHANGE to reselect."
            " Anything else cancels; no automatic playback:")
        answer = read_line()
        if answer == "CHANGE":
            changes += 1
            if changes > 2:
                out("Change limit reached. No playback started.")
                return False
            out("Selection cleared. Choose again; no playback started.")
            continue
        if type(answer) is not str or answer != "PLAY":
            out("Music session cancelled. No playback started.")
            return False
        out("Explicit PLAY confirmed. To stop, press q + Enter or Ctrl+C.")
        if level == "normal":
            return runner(selected, max_minutes=max_minutes)
        return runner(selected, max_minutes=max_minutes, level=level)
