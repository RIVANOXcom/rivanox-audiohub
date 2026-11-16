# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in PC-side offline MP3/FLAC -> PCM16 WAV export for owned music.

Never runs on the Pi, changes an original, downloads codecs, or prints names.
FFmpeg must be independently installed on the trusted operator computer.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import wave

INPUT_BYTES_MAX = 512 * 1024 * 1024
OUTPUT_BYTES_MAX = 64 * 1024 * 1024
CHUNK = 16384  # Stereo PCM16 frames; no unbounded stdout collection.
FORMATS = {".flac": "flac", ".mp3": "mp3"}


def _plan(source, output):
    """Preflight with no source names, file contents or directory writes."""
    src, dst = Path(source), Path(output)
    if (not src.is_absolute() or not dst.is_absolute()
            or ".." in src.parts or ".." in dst.parts
            or src.suffix.lower() not in FORMATS or dst.suffix.lower() != ".wav"
            or src.is_symlink() or dst.is_symlink()
            or dst.exists() or not dst.parent.is_dir()
            or dst.parent.is_symlink()):
        raise ValueError("Unsupported paths, existing destination or format")
    if (str(src).startswith("\\\\") or str(dst).startswith("\\\\")
            or any(parent.is_symlink() for parent in (*src.parents, *dst.parents))):
        raise ValueError("Network paths or linked directories are not offline")
    info = src.stat(follow_symlinks=False)
    parent = dst.parent.stat(follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= INPUT_BYTES_MAX
            or info.st_nlink != 1 or not stat.S_ISDIR(parent.st_mode)):
        raise ValueError("Input must be an ordinary bounded private media file")
    return src, dst, info, FORMATS[src.suffix.lower()]


def _convert(source, output, *, ffmpeg="ffmpeg", timeout=120):
    """Create ONLY a new WAV after complete bounded conversion and validation."""
    src, dst, before, source_format = _plan(source, output)
    exe = shutil.which(ffmpeg)
    if not exe:
        raise RuntimeError("FFmpeg not installed locally; no files changed")
    argv = [exe, "-nostdin", "-hide_banner", "-loglevel", "error",
            "-protocol_whitelist", "file,pipe", "-f", source_format,
            "-i", str(src), "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le",
            "-f", "s16le", "pipe:1"]
    total = 0
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            shell=False)
    timer = threading.Timer(timeout, proc.kill)
    timer.daemon = True
    timer.start()
    try:
        # TemporaryFile is not published on disk as a named incomplete WAV.
        with tempfile.TemporaryFile(mode="w+b", dir=dst.parent) as spool:
            with wave.open(spool, "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                while True:
                    data = proc.stdout.read(CHUNK)
                    if not data:
                        break
                    total += len(data)
                    if (len(data) % 4 or total > OUTPUT_BYTES_MAX - 44):
                        raise ValueError("Audio exceeds the 64 MiB PCM16 WAV limit")
                    writer.writeframesraw(data)
            if proc.wait(timeout=5) != 0 or total == 0:
                raise ValueError("Unsupported or invalid private audio")
            current = src.stat(follow_symlinks=False)
            if ((current.st_dev, current.st_ino, current.st_size,
                 current.st_mtime_ns) !=
                (before.st_dev, before.st_ino, before.st_size,
                 before.st_mtime_ns)):
                raise ValueError("Source changed during private export")
            spool.seek(0)
            with wave.open(spool, "rb") as reader:
                if (reader.getnchannels(), reader.getsampwidth(),
                    reader.getframerate(), reader.getcomptype()) != (2, 2, 48000, "NONE"):
                    raise ValueError("Result is not supported local PCM16 WAV")
                if not 0 < reader.getnframes() <= 30 * 60 * 48000:
                    raise ValueError("Export duration outside permitted bounds")
            spool.seek(0)
            digest = hashlib.sha256()
            created = None
            try:
                # Exclusive private permissions from creation, no transient
                # world-readable output and no race-based overwrites.
                flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
                with os.fdopen(os.open(dst, flags, 0o600), "wb") as result:
                    created = os.fstat(result.fileno())
                    while chunk := spool.read(CHUNK):
                        result.write(chunk)
                        digest.update(chunk)
                    result.flush()
                    os.fsync(result.fileno())
            except BaseException:
                # Clean up ONLY the file exclusively created by this call.
                # Never delete a file that someone else replaced after creation.
                if created is not None:
                    try:
                        now = dst.stat(follow_symlinks=False)
                        if (now.st_dev, now.st_ino) == (created.st_dev, created.st_ino):
                            dst.unlink()
                    except OSError:
                        pass
                raise
            return {"sha256": digest.hexdigest(), "bytes": total + 44,
                    "duration_seconds": round(total / (48000 * 2 * 2), 2)}
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Absolute local owned .flac/.mp3 path")
    parser.add_argument("--output", required=True, help="New absolute .wav path; never overwritten")
    parser.add_argument("--convert", action="store_true", help="Require a local TTY and exact CONVERT")
    args = parser.parse_args(argv)
    try:
        _plan(args.source, args.output)
        print("PRIVATE OFFLINE AUDIO PREVIEW: compatible MP3/FLAC input and unused WAV output.")
        print("Output: PCM16, stereo, 48 kHz, at most 64 MiB; original unchanged.")
        print("No network download or files created during this preview.")
        if not args.convert:
            return 0
        if not (sys.stdin.isatty() and sys.stdout.isatty()) or (
                hasattr(os, "geteuid") and os.geteuid() == 0):
            raise PermissionError("Conversion requires an unprivileged trusted local terminal")
        print("Ensure the input is your own or licensed. Type uppercase CONVERT to write ONLY a new WAV:")
        if sys.stdin.readline(32) != "CONVERT\n":
            print("CANCELLED: no files changed.")
            return 2
        result = _convert(args.source, args.output)
        print("NEW PCM16 WAV CREATED; original unchanged; bytes: " + str(result["bytes"]))
        print("Output SHA256: " + result["sha256"] + "; check the new WAV on the trusted PC.")
        print("Not a physical Pi/Edifier sound or ownership verification.")
        return 0
    except (OSError, ValueError, RuntimeError, PermissionError, subprocess.SubprocessError):
        print("PRIVATE EXPORT REFUSED/INCOMPLETE: check input/FFmpeg/output locally. "
              "Existing media never overwritten; no network or Pi changes.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
