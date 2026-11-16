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



def check_local_prerequisites():
    """No-write offline PC readiness; NEVER runs or installs FFmpeg."""
    import importlib.util

    python_ok = sys.version_info >= (3, 11)
    tk_available = importlib.util.find_spec("tkinter") is not None
    decoder_found = shutil.which("ffmpeg") is not None
    print("AudioHub LOCAL PC setup (check only; no music read, network or writes)")
    print("Python 3.11+: " + ("DETECTED" if python_ok else "NOT AVAILABLE"))
    print("Tk file-picker library: " + ("DETECTED" if tk_available else "NOT AVAILABLE"))
    print("External FFmpeg on PATH: " + ("DETECTED" if decoder_found else
                                        "NOT FOUND - conversion unavailable"))
    print("FFmpeg is NOT bundled. If missing, install it independently and"
          " restart the app; read-only previews still work.")
    return 0 if python_ok and tk_available else 2


def launch_gui():
    """A local, explicitly opted-in Tk file picker. Never auto-starts FFmpeg."""
    import queue
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog, ttk
    except ImportError as exc:
        raise RuntimeError("Local Python desktop support unavailable") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("No trusted local desktop session") from exc
    root.title("AudioHub - Offline WAV preparation")
    root.minsize(560, 340)
    root.columnconfigure(0, weight=1)
    body = ttk.Frame(root, padding=16)
    body.grid(sticky="nsew")
    body.columnconfigure(1, weight=1)
    source, output = tk.StringVar(master=root), tk.StringVar(master=root)
    status = tk.StringVar(master=root, value=(
        "Offline only: select your owned music and an UNUSED WAV destination."))
    approved = [None]
    working = [False]
    results = queue.Queue(maxsize=1)

    def invalidate(*_):
        approved[0] = None
        convert_button.configure(state="disabled")
        if not working[0]:
            status.set("Selection changed. Run read-only Preview again.")
    source.trace_add("write", invalidate)
    output.trace_add("write", invalidate)

    def pick_source():
        chosen = filedialog.askopenfilename(
            parent=root, title="Select local owned MP3 or FLAC",
            filetypes=[("Music", "*.flac *.mp3"), ("All files", "*.*")])
        if chosen:
            source.set(chosen)
    def pick_destination():
        chosen = filedialog.asksaveasfilename(
            parent=root, title="Choose NEW (unused) WAV filename",
            defaultextension=".wav", filetypes=[("WAV", "*.wav")])
        if chosen:
            output.set(chosen)

    ttk.Label(body, text="Owned/licensed local MP3 or FLAC").grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
    source_entry = ttk.Entry(body, textvariable=source, width=55)
    source_entry.grid(row=1, column=0, columnspan=2,
                      sticky="ew", padx=(0, 8))
    source_button = ttk.Button(body, text="Choose source", command=pick_source)
    source_button.grid(row=1, column=2, sticky="e")
    ttk.Label(body, text="New WAV in existing LOCAL folder (never overwrite)").grid(
        row=2, column=0, columnspan=3, sticky="w", pady=(14, 6))
    output_entry = ttk.Entry(body, textvariable=output, width=55)
    output_entry.grid(row=3, column=0, columnspan=2,
                      sticky="ew", padx=(0, 8))
    destination_button = ttk.Button(body, text="Choose new WAV",
                                    command=pick_destination)
    destination_button.grid(row=3, column=2, sticky="e")

    def preview():
        if working[0]:
            return
        approved[0] = None
        convert_button.configure(state="disabled")
        try:
            _plan(source.get(), output.get())
        except (OSError, ValueError, RuntimeError):
            status.set("PREVIEW REFUSED: check local owned source and UNUSED "
                       "WAV destination. No files changed.")
            return
        if shutil.which("ffmpeg") is None:
            status.set("PREVIEW VALID (no writes). External FFmpeg NOT FOUND. "
                       "Install separately on this trusted PC, restart, then "
                       "preview again. Conversion stays disabled.")
            return
        approved[0] = (source.get(), output.get())
        status.set("PREVIEW READY. Output PCM16 stereo 48 kHz, max 64 MiB. "
                   "External FFmpeg detected but NOT run. Review then CONVERT.")
        convert_button.configure(state="normal")

    def finish():
        try:
            ok, value = results.get_nowait()
        except queue.Empty:
            root.after(150, finish)
            return
        working[0] = False
        approved[0] = None
        preview_button.configure(state="normal")
        source_button.configure(state="normal")
        destination_button.configure(state="normal")
        source_entry.configure(state="normal")
        output_entry.configure(state="normal")
        convert_button.configure(state="disabled")
        if ok:
            status.set("NEW WAV created; original untouched. "
                       "SHA256: " + value["sha256"])
            messagebox.showinfo("New offline WAV created",
                                "Output SHA256:\n" + value["sha256"] +
                                "\nOriginal untouched. NOT Pi/Edifier verified.",
                                parent=root)
        else:
            status.set("EXPORT INCOMPLETE or refused. Existing files untouched.")
            messagebox.showwarning("No completed WAV",
                                   "Check local FFmpeg, input and unused output. "
                                   "Nothing was overwritten.", parent=root)

    def convert():
        if working[0] or approved[0] != (source.get(), output.get()):
            status.set("Preview these exact paths before any conversion.")
            return
        try:
            _plan(source.get(), output.get())
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                raise PermissionError("No privileged conversions")
        except (OSError, ValueError, PermissionError):
            invalidate()
            status.set("PREVIEW EXPIRED: source or target changed; no files written.")
            return
        answer = simpledialog.askstring(
            "Confirm one new WAV",
            "Use ONLY music you own or may legally use.\n"
            "External FFmpeg must be installed on THIS PC.\n"
            "Existing files are NEVER overwritten.\n"
            "Type EXACT uppercase CONVERT:", parent=root)
        if answer != "CONVERT":
            status.set("CANCELLED: no audio decoder started, no files created.")
            return
        chosen_source, chosen_output = approved[0]
        working[0] = True
        source_button.configure(state="disabled")
        destination_button.configure(state="disabled")
        source_entry.configure(state="disabled")
        output_entry.configure(state="disabled")
        preview_button.configure(state="disabled")
        convert_button.configure(state="disabled")
        status.set("Converting locally. No WAV is published until complete.")
        def worker():
            try:
                result = _convert(chosen_source, chosen_output)
                results.put((True, result))
            except (OSError, ValueError, RuntimeError, PermissionError,
                    subprocess.SubprocessError):
                results.put((False, None))
        threading.Thread(target=worker, daemon=True,
                         name="audiohub-local-wav-prep").start()
        root.after(150, finish)

    controls = ttk.Frame(body)
    controls.grid(row=4, column=0, columnspan=3, sticky="w", pady=(18, 12))
    preview_button = ttk.Button(controls, text="1. Preview (no writes)",
                                command=preview)
    preview_button.grid(row=0, column=0, padx=(0, 10))
    convert_button = ttk.Button(controls, text="2. Convert after confirmation",
                                command=convert, state="disabled")
    convert_button.grid(row=0, column=1)
    ttk.Label(body, textvariable=status, wraplength=510, justify="left").grid(
        row=5, column=0, columnspan=3, sticky="w", pady=(4, 8))
    ttk.Label(body, text="External FFmpeg required for conversion; no network, "
              "Bluetooth, Pi, SD or original file changes.", wraplength=510).grid(
        row=6, column=0, columnspan=3, sticky="w")
    def close():
        if working[0]:
            messagebox.showwarning("Conversion in progress",
                                   "Wait for the bounded local conversion to finish.",
                                   parent=root)
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Absolute local owned .flac/.mp3 path")
    parser.add_argument("--output", help="New absolute .wav path; never overwritten")
    parser.add_argument("--convert", action="store_true", help="Require a local TTY and exact CONVERT")
    parser.add_argument("--gui", action="store_true", help="Local file picker, Preview and exact CONVERT dialog")
    parser.add_argument("--check-local", action="store_true", help="No-write Python/Tk/FFmpeg readiness check")
    args = parser.parse_args(argv)
    if args.check_local:
        if args.gui or args.source is not None or args.output is not None or args.convert:
            parser.error("--check-local cannot be combined with music paths or conversion")
        return check_local_prerequisites()
    if args.gui:
        if args.source is not None or args.output is not None or args.convert:
            parser.error("--gui cannot be combined with --source, --output or --convert")
        try:
            return launch_gui()
        except (OSError, RuntimeError):
            print("Local desktop GUI is unavailable; nothing was changed.", file=sys.stderr)
            return 2
    if args.source is None or args.output is None:
        parser.error("Both --source and --output are required in terminal mode")
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
