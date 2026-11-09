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


def display_library(items, *, show_titles=False):
    """Non-persistent terminal view. Private titles need explicit local opt-in."""
    if type(show_titles) is not bool:
        raise ValueError("Invalid title display option")
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
    lines.append("Choose up to 8 displayed numbers using --tracks 1,3; "
                 "then add --play only when ready.")
    return "\n".join(lines)


def selected_paths(items, selection, *, max_minutes):
    indices = parse_track_numbers(selection, len(items))
    paths = [items[i][0] for i in indices]
    report = local_music.inspect_playlist(paths, max_minutes=max_minutes)
    return paths, report
