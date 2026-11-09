# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in local WAV queue for the existing unprivileged music PipeWire sink.

No service, browser command API, device discovery, configuration write,
Bluetooth pairing, credentials or network access. Only the person at the
already-authorized Pi terminal can explicitly start or stop playback.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import wave

from . import discovery
from .process_capture import bounded_command_output

TARGET = "audiohub.music"
MAX_FILES = 8
MAX_WAV_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 30 * 60
STREAM_VOLUME = "0.20"  # Conservative starting point; NOT calibrated SPL.
FRAMES_PER_CHUNK = 2048


def _open_wav(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".wav":
        raise ValueError("Choose an absolute existing local .wav file")
    if path.is_symlink():
        raise ValueError("Links cannot be played")
    fd = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    stream = None
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_size < 44
                or st.st_size > MAX_WAV_BYTES or (st.st_mode & 0o002)):
            raise ValueError("WAV must be a bounded, non-world-writable regular file")
        stream = os.fdopen(fd, "rb")
        fd = None
        with wave.open(stream, "rb") as info:
            channels = info.getnchannels()
            rate = info.getframerate()
            frames = info.getnframes()
            if (channels not in (1, 2) or info.getsampwidth() != 2
                    or not 8000 <= rate <= 96000
                    or info.getcomptype() != "NONE"
                    or not 1 <= frames <= MAX_SECONDS * rate
                    or frames * channels * 2 > st.st_size):
                raise ValueError("Only bounded 16-bit PCM mono/stereo WAV is supported")
            return {"channels": channels, "rate": rate, "frames": frames,
                    "duration_ms": (frames * 1000 + rate - 1) // rate}
    except (EOFError, wave.Error, OSError) as exc:
        raise ValueError("Invalid or inaccessible WAV") from exc
    finally:
        if stream is not None:
            stream.close()
        if fd is not None:
            os.close(fd)


def inspect_playlist(paths, *, max_minutes=15):
    if (type(paths) not in (list, tuple) or not 1 <= len(paths) <= MAX_FILES
            or type(max_minutes) is not int or not 1 <= max_minutes <= 30):
        raise ValueError("Choose 1–8 WAV tracks and a 1–30 minute limit")
    entries = []
    total_ms = 0
    for path in paths:
        metadata = _open_wav(path)
        total_ms += metadata["duration_ms"]
        if total_ms > min(MAX_SECONDS, max_minutes * 60) * 1000:
            raise ValueError("Playlist exceeds the requested playback time limit")
        entries.append(metadata)
    # Only non-identifying formats and durations, never filenames or paths.
    return {"classification": "LOCAL_OPERATOR_PREVIEW_ONLY",
            "input_slot": "music", "files": len(entries),
            "total_duration_ms": total_ms, "tracks": entries,
            "playback_started": False, "audible_sound_verified": False,
            "device_owner_verified": False, "release_ready": False}


def music_sink_available(*, capture=bounded_command_output):
    result = capture(["pw-dump"], timeout=5, max_bytes=discovery.MAX_PIPEWIRE_GRAPH_BYTES)
    if result is None or result.returncode != 0:
        return False
    nodes = discovery.pipewire_nodes(result.stdout)
    return TARGET in discovery.virtual_sinks(nodes)


def _play_one(path, metadata, *, deadline, spawn, stop=None, on_player=None):
    # Reopen and inspect at playback time: never rely solely on a stale preview.
    if _open_wav(path) != metadata:
        raise ValueError("Audio file changed since the local preview")
    fd = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    stream = None
    child = None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_WAV_BYTES:
            raise ValueError("Refusing changed audio file")
        stream = os.fdopen(fd, "rb")
        fd = None
        with wave.open(stream, "rb") as reader:
            if (reader.getnchannels() != metadata["channels"]
                    or reader.getframerate() != metadata["rate"]
                    or reader.getnframes() != metadata["frames"]
                    or reader.getsampwidth() != 2 or reader.getcomptype() != "NONE"):
                raise ValueError("Audio file metadata changed")
            command = [
                "pw-cat", "--playback", "--raw", "--target=" + TARGET,
                "--rate=" + str(metadata["rate"]),
                "--channels=" + str(metadata["channels"]),
                "--format=s16", "--volume=" + STREAM_VOLUME, "-"
            ]
            child = spawn(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, shell=False,
                          start_new_session=True)
            if on_player is not None:
                on_player(child)
            sent = 0
            while sent < metadata["frames"]:
                if (time.monotonic() >= deadline
                        or (stop is not None and stop.is_set())):
                    raise InterruptedError("Operator playback stopped or timed out")
                frames = min(FRAMES_PER_CHUNK, metadata["frames"] - sent)
                data = reader.readframes(frames)
                if len(data) != frames * metadata["channels"] * 2:
                    raise ValueError("WAV data ended early")
                child.stdin.write(data)
                sent += frames
            child.stdin.close()
            # A 30-minute track cannot finish within the old fixed 10s
            # wait. Check cancel/deadline on every short interval instead,
            # including after the entire WAV was sent into the player's pipe.
            while True:
                remaining = deadline - time.monotonic()
                if (remaining <= 0 or
                        (stop is not None and stop.is_set())):
                    raise InterruptedError("Local music playback stopped or timed out")
                try:
                    result = child.wait(timeout=min(0.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if result != 0:
                raise RuntimeError("Local PipeWire playback tool was unavailable")
            return True
    except BrokenPipeError as exc:
        raise RuntimeError("Local PipeWire player closed unexpectedly") from exc
    finally:
        if child is not None:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
            if child.stdin is not None and not child.stdin.closed:
                child.stdin.close()
        if stream is not None:
            stream.close()
        if fd is not None:
            os.close(fd)


def play_playlist(paths, *, max_minutes=15, spawn=subprocess.Popen, capture=bounded_command_output,
                  stop=None, notify=print, session_deadline=None, on_player=None):
    """One explicit local playback session, never a persistent service."""
    report = inspect_playlist(paths, max_minutes=max_minutes)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PermissionError("Run as the unprivileged audiohub PipeWire user, never root")
    if not music_sink_available(capture=capture):
        raise RuntimeError("AudioHub music sink unavailable; no default-output fallback")
    deadline = time.monotonic() + min(MAX_SECONDS, max_minutes * 60)
    if session_deadline is not None:
        if type(session_deadline) not in (int, float):
            raise ValueError("Invalid session deadline")
        deadline = min(deadline, session_deadline)
    for i, (path, metadata) in enumerate(zip(paths, report["tracks"]), 1):
        if time.monotonic() >= deadline:
            raise TimeoutError("Local playlist session deadline reached")
        notify("Playing track " + str(i) + "/" + str(report["files"])
               + " privately through music input; Ctrl+C stops.")
        _play_one(path, metadata, deadline=deadline, spawn=spawn, stop=stop,
                  on_player=on_player)
    notify("Local playback finished. Audible sound was NOT automatically verified.")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", nargs="*", help="1–8 absolute local 16-bit PCM WAV files")
    parser.add_argument("--library", metavar="FOLDER",
                        help="Browse a private local WAV folder without playback")
    parser.add_argument("--tracks", metavar="1,3",
                        help="Choose 1–8 numbered library tracks (no autoplay)")
    parser.add_argument("--show-titles", action="store_true",
                        help="EXPLICITLY print sanitized track names on the local console")
    parser.add_argument("--minutes", type=int, default=15,
                        help="Maximum explicit session (1–30 minutes, default 15)")
    parser.add_argument("--play", action="store_true",
                        help="EXPLICITLY send limited local WAV audio to music input")
    parser.add_argument("--interactive", action="store_true",
                        help="With --play: use local terminal s=status, n=next, q=stop; Enter required")
    args = parser.parse_args(argv)
    try:
        if args.interactive and not args.play:
            raise ValueError("--interactive requires explicit --play")
        if args.interactive and (not sys.stdin.isatty() or not sys.stdout.isatty()):
            raise PermissionError("Interactive control requires an operator terminal")
        if args.library is not None:
            if args.wav:
                raise ValueError("Choose either direct WAV paths or a library folder")
            # The library is a local, read-only selection interface. It never
            # runs a player unless BOTH --tracks and --play are explicit.
            from . import music_library
            items, skipped = music_library.discover_library(args.library)
            print(music_library.display_library(items,
                                                 show_titles=args.show_titles))
            if skipped:
                print(str(skipped) + " unsupported or unsafe WAV entries skipped.")
            if args.tracks is None:
                if args.play:
                    raise ValueError("Pick numbered tracks before starting playback")
                return 0
            paths, preview = music_library.selected_paths(
                items, args.tracks, max_minutes=args.minutes
            )
            print("Selection: " + str(preview["files"]) + " track(s), "
                  + str(preview["total_duration_ms"] // 1000)
                  + " seconds. No network or mixer changes.")
            if not args.play:
                print("Preview only. Repeat with --play to hear selected local tracks.")
                return 0
            if args.interactive:
                from . import music_session
                music_session.run_session(paths, max_minutes=args.minutes)
            else:
                play_playlist(paths, max_minutes=args.minutes)
            return 0
        if args.tracks is not None or args.show_titles:
            raise ValueError("Numbered tracks and local titles require --library")
        preview = inspect_playlist(args.wav, max_minutes=args.minutes)
        print("Local music queue: " + str(preview["files"]) + " track(s); " +
              str(preview["total_duration_ms"] // 1000) + " seconds; no playback yet.")
        if not args.play:
            print("To play locally, repeat with --play. No source, setting or route changed.")
            return 0
        if args.interactive:
            from . import music_session
            music_session.run_session(args.wav, max_minutes=args.minutes)
        else:
            play_playlist(args.wav, max_minutes=args.minutes)
        return 0
    except KeyboardInterrupt:
        print("Local music playback stopped. No route or setting changed.")
        return 130
    except (ValueError, OSError, RuntimeError, PermissionError, TimeoutError, InterruptedError):
        print("Local player unavailable or stopped; check WAV, music sink and Pi console. "
              "No private filename or device identifier is shown.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
