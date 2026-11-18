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


def suggest_unused_wav(source):
    """Suggest a nearby new WAV name, without creating/reserving a file.

    Only a convenience hint. Preview and conversion MUST revalidate it, and
    the final writer still uses O_EXCL to avoid overwriting a racing creator.
    """
    src = Path(source)
    if not src.is_absolute() or src.suffix.lower() not in FORMATS:
        raise ValueError("Select an owned local MP3/FLAC first")
    for number in range(1, 101):
        suffix = "-AudioHub" if number == 1 else f"-AudioHub-{number}"
        name = src.stem + suffix + ".wav"
        # Keep enough room for filesystem encoding differences; users can
        # choose a shorter filename manually if the original is very long.
        if len(name.encode("utf-8")) > 240:
            raise ValueError("Choose a shorter unused WAV name manually")
        candidate = src.with_name(name)
        if candidate.exists() or candidate.is_symlink():
            continue
        _plan(src, candidate)  # No writes; refuse linked/network/unsafe paths.
        return candidate
    raise ValueError("No unused local WAV name in the bounded search")


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
                # Check the published destination, not only its temporary
                # spool and write-time hash. No user filenames are logged.
                expected_sha256 = digest.hexdigest()
                verified = verify_local_wav(dst)
                if (verified["sha256"] != expected_sha256
                        or verified["bytes"] != total + 44):
                    raise ValueError("Final WAV failed private read-back verification")
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
            return {"sha256": expected_sha256, "bytes": verified["bytes"],
                    "duration_seconds": verified["duration_seconds"]}
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()




class ScanCancelled(RuntimeError):
    """The operator stopped a read-only WAV inspection (never a file write)."""


def _abort_if_requested(cancel):
    if cancel is not None and cancel.is_set():
        raise ScanCancelled("Private read-only WAV check cancelled")


def verify_local_wav(path, *, cancel=None):
    """Inspect a finished PCM16 stereo 48-kHz WAV without FFmpeg or writes."""
    _abort_if_requested(cancel)
    target = Path(path)
    if (not target.is_absolute() or ".." in target.parts
            or target.suffix.lower() != ".wav"
            or str(target).startswith("\\\\") or target.is_symlink()
            or any(part.is_symlink() for part in target.parents)):
        raise ValueError("Expected an ordinary local WAV path")
    before = target.stat(follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 44 <= before.st_size <= OUTPUT_BYTES_MAX):
        raise ValueError("Expected an ordinary bounded local WAV file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(target, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if ((opened.st_dev, opened.st_ino, opened.st_size) !=
                (before.st_dev, before.st_ino, before.st_size)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1):
            raise ValueError("WAV changed before inspection")
        try:
            with wave.open(stream, "rb") as reader:
                if (reader.getnchannels(), reader.getsampwidth(),
                    reader.getframerate(), reader.getcomptype()) != (2, 2, 48000, "NONE"):
                    raise ValueError("Expected PCM16 stereo 48 kHz WAV")
                frames = reader.getnframes()
                if not 0 < frames <= 30 * 60 * 48000 or frames * 4 > before.st_size - 44:
                    raise ValueError("Invalid or truncated WAV")
                count = 0
                while count < frames * 4:
                    _abort_if_requested(cancel)
                    data = reader.readframes(min(4096, frames - count // 4))
                    if not data or len(data) % 4:
                        raise ValueError("Truncated WAV data")
                    count += len(data)
                if count != frames * 4:
                    raise ValueError("Incorrect WAV data length")
        except (wave.Error, EOFError) as exc:
            raise ValueError("Unreadable WAV format") from exc
        stream.seek(0)
        digest = hashlib.sha256()
        total = 0
        while data := stream.read(CHUNK):
            _abort_if_requested(cancel)
            total += len(data)
            if total > OUTPUT_BYTES_MAX:
                raise ValueError("Oversized WAV")
            digest.update(data)
        _abort_if_requested(cancel)
        after = os.fstat(stream.fileno())
        if total != before.st_size or (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
            raise ValueError("WAV changed during inspection")
    return {"sha256": digest.hexdigest(), "bytes": total,
            "duration_seconds": round(frames / 48000, 2)}


def verify_local_wav_folder(path, *, cancel=None, progress=None):
    """Read-only, bounded check of the direct WAV files in one local folder.

    The collection digest represents ordered audio contents, not filenames.
    It is not a playlist export or physical speaker/SD verification.
    """
    _abort_if_requested(cancel)
    folder = Path(path)
    if (not folder.is_absolute() or ".." in folder.parts
            or str(folder).startswith("\\\\") or folder.is_symlink()
            or any(parent.is_symlink() for parent in folder.parents)):
        raise ValueError("Expected an ordinary local WAV folder")
    before = folder.stat(follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("Expected an ordinary local folder")
    targets = []
    seen_names = set()
    with os.scandir(folder) as listing:
        for count, entry in enumerate(listing):
            _abort_if_requested(cancel)
            if count >= 256:
                raise ValueError("Folder has more than 256 direct entries")
            if entry.name.lower().endswith(".wav"):
                folded = entry.name.casefold()
                if (folded in seen_names or entry.is_symlink()
                        or not entry.is_file(follow_symlinks=False)):
                    raise ValueError("Ambiguous or unsafe WAV folder entry")
                seen_names.add(folded)
                targets.append(folder / entry.name)
                if len(targets) > 40:
                    raise ValueError("At most 40 direct WAV tracks per check")
    if not targets:
        raise ValueError("No direct WAV tracks found in selected folder")
    digest = hashlib.sha256(b"AudioHub private WAV collection v1\n")
    total = 0
    content_items = []
    for index, target in enumerate(sorted(targets, key=lambda p: p.name.casefold()), 1):
        _abort_if_requested(cancel)
        if cancel is None:
            details = verify_local_wav(target)
        else:
            details = verify_local_wav(target, cancel=cancel)
        _abort_if_requested(cancel)
        if progress is not None:
            progress(index, len(targets))
        _abort_if_requested(cancel)
        # Separate canonical copy identity from the historic ordered
        # collection digest; preserve old folder-check output unchanged.
        content_items.append((details["bytes"], bytes.fromhex(details["sha256"])))
        total += details["bytes"]
        # Include ordered audio hashes and byte counts without leaking names.
        digest.update(index.to_bytes(2, "big"))
        digest.update(bytes.fromhex(details["sha256"]))
        digest.update(details["bytes"].to_bytes(8, "big"))
    _abort_if_requested(cancel)
    after = folder.stat(follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_mtime_ns):
        raise ValueError("WAV folder changed during inspection")
    # Include multiplicity (duplicate tracks count) but NOT local filenames or
    # path ordering. This gives reliable checks after manually renaming files.
    copy_digest = hashlib.sha256(b"AudioHub private WAV copy multiset v1\n")
    copy_digest.update(len(content_items).to_bytes(2, "big"))
    for size, file_sha in sorted(content_items):
        copy_digest.update(size.to_bytes(8, "big"))
        copy_digest.update(file_sha)
    return {"files": len(targets), "bytes": total,
            "collection_sha256": digest.hexdigest(),
            "copy_content_sha256": copy_digest.hexdigest()}



def compare_local_wav_folders(source_folder, copied_folder, *, cancel=None,
                              progress=None):
    """Verify two existing local WAV folders without reading private filenames aloud.

    Match means identical complete PCM16 WAV file contents, including duplicate
    counts, independent of filenames and order; NOT ownership, timestamps, rights,
    or proof of SD/Pi hardware playback. Both sides are fully and independently
    validated using the same bounded no-write folder verifier.
    """
    _abort_if_requested(cancel)
    if os.path.samefile(source_folder, copied_folder):
        raise ValueError("Select two different local WAV folders")
    if cancel is None and progress is None:
        left = verify_local_wav_folder(source_folder)
        right = verify_local_wav_folder(copied_folder)
    else:
        left = verify_local_wav_folder(
            source_folder, cancel=cancel,
            progress=(None if progress is None else
                      lambda done, total: progress("original", done, total)))
        _abort_if_requested(cancel)
        right = verify_local_wav_folder(
            copied_folder, cancel=cancel,
            progress=(None if progress is None else
                      lambda done, total: progress("copy", done, total)))
    _abort_if_requested(cancel)
    return {
        "matched": (left["files"] == right["files"]
                    and left["bytes"] == right["bytes"]
                    and left["copy_content_sha256"] == right["copy_content_sha256"]),
        "source": left, "copy": right,
    }


def run_offline_wav_demo():
    """Demonstrate real local WAV validation without any operator media.

    ONLY generated, bounded, very short synthetic audio is written under one
    fresh private OS temporary folder; the temporary folder is removed on
    exit. Never scans personal music folders, executes codecs or uses Pi/network.
    """
    base = Path(tempfile.gettempdir())
    if (not base.is_absolute() or str(base).startswith("\\\\")
            or base.is_symlink()
            or any(parent.is_symlink() for parent in base.parents)):
        raise ValueError("An ordinary local temp folder is required")

    def make_synthetic_wav(target, pcm):
        # The target is an exclusive file inside OUR newly created temp folder.
        with target.open("xb") as stream:
            with wave.open(stream, "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(2)
                writer.setframerate(48000)
                writer.writeframes(pcm)

    silence = b"\x00\x00\x00\x00" * 480  # 10 ms of two-channel PCM16
    signal = b"\x01\x00\xff\xff" * 480
    with tempfile.TemporaryDirectory(
            prefix="audiohub-synthetic-demo-", dir=base) as temporary:
        root = Path(temporary)
        source, copy, changed = (
            root / "original", root / "copy", root / "different")
        for folder in (source, copy, changed):
            folder.mkdir(mode=0o700)
        first = source / "a-original.wav"
        second = source / "z-original.wav"
        make_synthetic_wav(first, silence)
        make_synthetic_wav(second, signal)
        originals_before = tuple(
            hashlib.sha256(path.read_bytes()).digest()
            for path in (first, second))

        # Identical bytes, but completely different, reverse-sorted filenames.
        make_synthetic_wav(copy / "a-renamed.wav", signal)
        make_synthetic_wav(copy / "z-renamed.wav", silence)
        matching = compare_local_wav_folders(source, copy)
        if not matching["matched"] or matching["source"]["files"] != 2:
            raise ValueError("Synthetic renamed WAV copy mismatch")

        # Same number of tracks, but one missing, replaced by a duplicate:
        # a successful demo MUST detect this as different audio content.
        make_synthetic_wav(changed / "a-duplicate.wav", silence)
        make_synthetic_wav(changed / "z-duplicate.wav", silence)
        altered = compare_local_wav_folders(source, changed)
        if altered["matched"] or altered["copy"]["files"] != 2:
            raise ValueError("Synthetic missing-track difference not found")

        # Exercise real cooperative cancellation in the read-only comparator.
        cancel = threading.Event()
        def stop_after_one(phase, done, total):
            if phase == "original" and done == 1 and total == 2:
                cancel.set()
        try:
            compare_local_wav_folders(
                source, copy, cancel=cancel, progress=stop_after_one)
        except ScanCancelled:
            if not cancel.is_set():
                raise ValueError("Synthetic scan stopped unexpectedly")
        else:
            raise ValueError("Synthetic scan cancellation was not honored")
        originals_after = tuple(
            hashlib.sha256(path.read_bytes()).digest()
            for path in (first, second))
        if originals_before != originals_after:
            raise ValueError("Synthetic demo altered an original")
    # TemporaryDirectory cleans ONLY the synthetic demo folder it created.
    return {"tracks": 2, "match": True, "difference": True,
            "cancel": True, "private_media_used": False}


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
    root.minsize(640, 545)
    root.columnconfigure(0, weight=1)
    body = ttk.Frame(root, padding=16)
    body.grid(sticky="nsew")
    body.columnconfigure(1, weight=1)
    source, output = tk.StringVar(master=root), tk.StringVar(master=root)
    status = tk.StringVar(master=root, value=(
        "Offline only: select your owned music and an UNUSED WAV destination."))
    approved = [None]
    automatic_output = [None]
    working = [False]
    work_kind = ["convert"]
    results = queue.Queue(maxsize=1)
    scan_updates = queue.Queue(maxsize=1)
    scan_cancel = threading.Event()

    def scan_progress(phase, done, total):
        """Worker thread can publish only anonymous counts; no Tk calls."""
        note = (phase, done, total)
        try:
            scan_updates.put_nowait(note)
        except queue.Full:
            try:
                scan_updates.get_nowait()
            except queue.Empty:
                pass
            try:
                scan_updates.put_nowait(note)
            except queue.Full:
                pass

    def cancel_scan():
        if working[0] and work_kind[0] in ("folder", "compare"):
            scan_cancel.set()
            cancel_button.configure(state="disabled")
            status.set("STOP REQUESTED: finishing current read chunk. "
                       "No audio has been changed.")

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
            old_output = output.get()
            source.set(chosen)
            if not old_output or old_output == automatic_output[0]:
                try:
                    candidate = suggest_unused_wav(chosen)
                except (OSError, ValueError, UnicodeError):
                    automatic_output[0] = None
                    output.set("")
                    status.set("Choose an UNUSED WAV name in an existing local folder; "
                               "then Preview. No files created.")
                else:
                    automatic_output[0] = str(candidate)
                    output.set(str(candidate))
                    status.set("Unused local WAV name SUGGESTED (not reserved). "
                               "Review or change it, then Preview before Convert.")
            else:
                # The operator explicitly chose/typed a destination. Do not
                # silently replace it when selecting a different source.
                status.set("Source selected; your manual WAV destination kept. "
                           "Review both paths, then Preview again.")
    def pick_destination():
        chosen = filedialog.asksaveasfilename(
            parent=root, title="Choose NEW (unused) WAV filename",
            defaultextension=".wav", filetypes=[("WAV", "*.wav")])
        if chosen:
            automatic_output[0] = None
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

    def verify_wav():
        if working[0]:
            return
        try:
            details = verify_local_wav(output.get())
        except (OSError, ValueError, RuntimeError):
            status.set("WAV CHECK REFUSED: select an existing local PCM16 "
                       "stereo 48 kHz WAV. No files changed.")
            messagebox.showwarning("WAV not verified",
                                   "File missing, unsafe, incomplete or in "
                                   "another format. No files changed.",
                                   parent=root)
            return
        status.set("READ-ONLY WAV VERIFIED. SHA256: " + details["sha256"])
        messagebox.showinfo("WAV format verified",
                            "PCM16 stereo 48 kHz; duration "
                            + str(details["duration_seconds"]) + " s.\n"
                            + "SHA256:\n" + details["sha256"]
                            + "\nNOT an audible Pi/Edifier test.", parent=root)

    def finish():
        try:
            ok, value = results.get_nowait()
        except queue.Empty:
            if working[0] and work_kind[0] in ("folder", "compare"):
                try:
                    phase, done, total = scan_updates.get_nowait()
                except queue.Empty:
                    pass
                else:
                    if not scan_cancel.is_set():
                        status.set("READ-ONLY " + phase.upper() + " FOLDER: "
                                   + str(done) + "/" + str(total)
                                   + " WAVs inspected. No writes.")
            root.after(150, finish)
            return
        if scan_cancel.is_set() and work_kind[0] in ("folder", "compare"):
            ok, value = False, "cancelled"
        working[0] = False
        approved[0] = None
        cancel_button.configure(state="disabled")
        preview_button.configure(state="normal")
        source_button.configure(state="normal")
        destination_button.configure(state="normal")
        source_entry.configure(state="normal")
        output_entry.configure(state="normal")
        convert_button.configure(state="disabled")
        verify_button.configure(state="normal")
        verify_folder_button.configure(state="normal")
        compare_button.configure(state="normal")
        demo_button.configure(state="normal")
        if work_kind[0] == "demo":
            if ok:
                status.set("SYNTHETIC OFFLINE DEMO PASS: 2 WAV tracks; "
                           "match, difference and Stop verified. "
                           "No personal music opened.")
                messagebox.showinfo(
                    "Local synthetic WAV demo passed",
                    "Two short synthetic WAVs were compared in renamed order; "
                    "a missing track and a requested Stop were detected. "
                    "Temporary demo files cleaned automatically.\n"
                    "No real music, FFmpeg, network, Pi or sound tested.",
                    parent=root)
            else:
                status.set("SYNTHETIC OFFLINE DEMO FAILED: no real music opened. "
                           "Do not treat this package as verified.")
                messagebox.showwarning(
                    "Synthetic demo failed",
                    "The local temporary WAV demonstration did not pass. "
                    "No personal music was selected. No Pi/hardware was tested.",
                    parent=root)
            return
        if value == "cancelled" and work_kind[0] in ("folder", "compare"):
            status.set("STOPPED: read-only scan cancelled. No WAVs changed.")
            messagebox.showinfo("WAV check stopped",
                                "Read-only scan stopped; no audio changed. "
                                "No verification result was issued.", parent=root)
            return
        if work_kind[0] == "compare":
            if ok:
                left, right = value["source"], value["copy"]
                if value["matched"]:
                    status.set("READ-ONLY WAV COPY MATCH: " + str(left["files"])
                               + " files, order-independent. SHA256: "
                               + left["copy_content_sha256"])
                    messagebox.showinfo(
                        "WAV copy contents match",
                        str(left["files"]) + " WAVs match regardless of file names/order.\n"
                        + "Copy-content SHA256:\n" + left["copy_content_sha256"]
                        + "\nNo writes. Names and Pi sound NOT verified.", parent=root)
                else:
                    status.set("WAV COPY DIFFERS: source " + str(left["files"])
                               + ", copy " + str(right["files"])
                               + " WAVs; content or duplicates differ. No writes.")
                    messagebox.showwarning(
                        "WAV copy differs",
                        "Original WAV count: " + str(left["files"])
                        + "; copy WAV count: " + str(right["files"])
                        + ". File contents/multiplicity differ. No writes. "
                        "Check your copy manually; filenames stay private.", parent=root)
            else:
                status.set("WAV COPY CHECK REFUSED: select two different safe local "
                           "folders with 1-40 PCM16 stereo 48 kHz WAVs. No writes.")
                messagebox.showwarning(
                    "WAV copy not verified",
                    "One folder is empty, unsafe, modified or incompatible. "
                    "No files changed.", parent=root)
            return
        if work_kind[0] == "folder":
            if ok:
                status.set("READ-ONLY FOLDER VERIFIED: "
                           + str(value["files"]) + " WAV tracks. Collection SHA256: "
                           + value["collection_sha256"])
                messagebox.showinfo("Private WAV folder checked",
                                    str(value["files"]) + " compatible WAV files.\n"
                                    + "Collection content SHA256:\n"
                                    + value["collection_sha256"]
                                    + "\nNo files changed. NOT a Pi sound test.",
                                    parent=root)
            else:
                status.set("FOLDER CHECK REFUSED: empty, unsafe, changed, too large "
                           "or incompatible WAV. No files changed.")
                messagebox.showwarning("WAV folder not verified",
                                       "Use a local folder with 1-40 compatible "
                                       "direct WAV files. No files changed.",
                                       parent=root)
            return
        if ok:
            status.set("NEW WAV CREATED AND READ-BACK VERIFIED; original untouched. "
                       "SHA256: " + value["sha256"])
            messagebox.showinfo("New offline WAV verified",
                                "Final WAV reopened; PCM16 format and complete hash checked.\n"
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
        work_kind[0] = "convert"
        working[0] = True
        source_button.configure(state="disabled")
        destination_button.configure(state="disabled")
        source_entry.configure(state="disabled")
        output_entry.configure(state="disabled")
        preview_button.configure(state="disabled")
        convert_button.configure(state="disabled")
        verify_button.configure(state="disabled")
        verify_folder_button.configure(state="disabled")
        compare_button.configure(state="disabled")
        demo_button.configure(state="disabled")
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


    def verify_folder():
        if working[0]:
            return
        chosen = filedialog.askdirectory(
            parent=root, title="Select local folder of owned PCM16 WAVs")
        if not chosen:
            return
        working[0] = True
        work_kind[0] = "folder"
        scan_cancel.clear()
        cancel_button.configure(state="normal")
        source_button.configure(state="disabled")
        destination_button.configure(state="disabled")
        source_entry.configure(state="disabled")
        output_entry.configure(state="disabled")
        preview_button.configure(state="disabled")
        convert_button.configure(state="disabled")
        verify_button.configure(state="disabled")
        verify_folder_button.configure(state="disabled")
        compare_button.configure(state="disabled")
        demo_button.configure(state="disabled")
        status.set("Checking up to 40 WAV files without writing or playing audio.")
        def worker():
            try:
                result = verify_local_wav_folder(
                    chosen, cancel=scan_cancel,
                    progress=lambda done, total:
                        scan_progress("selected", done, total))
                _abort_if_requested(scan_cancel)
                results.put((True, result))
            except ScanCancelled:
                results.put((False, "cancelled"))
            except (OSError, ValueError, RuntimeError):
                results.put((False, None))
        threading.Thread(target=worker, daemon=True,
                         name="audiohub-private-wav-folder-check").start()
        root.after(150, finish)


    def compare_folders():
        if working[0]:
            return
        first = filedialog.askdirectory(
            parent=root, title="Choose original local WAV folder")
        if not first:
            return
        second = filedialog.askdirectory(
            parent=root, title="Choose manually copied local WAV folder")
        if not second:
            status.set("WAV COPY CHECK CANCELLED: no files changed.")
            return
        working[0] = True
        work_kind[0] = "compare"
        scan_cancel.clear()
        cancel_button.configure(state="normal")
        source_button.configure(state="disabled")
        destination_button.configure(state="disabled")
        source_entry.configure(state="disabled")
        output_entry.configure(state="disabled")
        preview_button.configure(state="disabled")
        convert_button.configure(state="disabled")
        verify_button.configure(state="disabled")
        verify_folder_button.configure(state="disabled")
        compare_button.configure(state="disabled")
        demo_button.configure(state="disabled")
        status.set("Comparing two existing WAV folders locally. No writes or transfers.")
        def worker():
            try:
                result = compare_local_wav_folders(
                    first, second, cancel=scan_cancel, progress=scan_progress)
                _abort_if_requested(scan_cancel)
                results.put((True, result))
            except ScanCancelled:
                results.put((False, "cancelled"))
            except (OSError, ValueError, RuntimeError):
                results.put((False, None))
        threading.Thread(target=worker, daemon=True,
                         name="audiohub-local-wav-copy-compare").start()
        root.after(150, finish)


    def demo_synthetic():
        if working[0]:
            return
        working[0] = True
        work_kind[0] = "demo"
        approved[0] = None
        source_button.configure(state="disabled")
        destination_button.configure(state="disabled")
        source_entry.configure(state="disabled")
        output_entry.configure(state="disabled")
        preview_button.configure(state="disabled")
        convert_button.configure(state="disabled")
        verify_button.configure(state="disabled")
        verify_folder_button.configure(state="disabled")
        compare_button.configure(state="disabled")
        demo_button.configure(state="disabled")
        status.set("Running a disposable local synthetic WAV demo. "
                   "No real music files, FFmpeg, network or Pi.")
        def worker():
            try:
                report = run_offline_wav_demo()
                results.put((True, report))
            except (OSError, ValueError, RuntimeError, wave.Error):
                results.put((False, None))
        threading.Thread(target=worker, daemon=True,
                         name="audiohub-synthetic-offline-demo").start()
        root.after(150, finish)

    controls = ttk.Frame(body)
    controls.grid(row=4, column=0, columnspan=3, sticky="w", pady=(18, 12))
    preview_button = ttk.Button(controls, text="1. Preview (no writes)",
                                command=preview)
    preview_button.grid(row=0, column=0, padx=(0, 10))
    convert_button = ttk.Button(controls, text="2. Convert after confirmation",
                                command=convert, state="disabled")
    convert_button.grid(row=0, column=1)
    verify_button = ttk.Button(controls, text="3. Verify WAV (read-only)",
                               command=verify_wav)
    verify_button.grid(row=1, column=0, columnspan=2, sticky="w",
                       pady=(10, 0))
    verify_folder_button = ttk.Button(controls, text="4. Check WAV folder (read-only)",
                                      command=verify_folder)
    verify_folder_button.grid(row=2, column=0, columnspan=2, sticky="w",
                              pady=(10, 0))
    compare_button = ttk.Button(controls, text="5. Compare WAV copy (read-only)",
                                command=compare_folders)
    compare_button.grid(row=3, column=0, columnspan=2, sticky="w",
                        pady=(10, 0))
    cancel_button = ttk.Button(
        controls, text="Stop read-only check", state="disabled",
        command=cancel_scan)
    cancel_button.grid(row=4, column=0, columnspan=2, sticky="w",
                       pady=(10, 0))
    demo_button = ttk.Button(
        controls, text="6. Run offline demo (synthetic; no music needed)",
        command=demo_synthetic)
    demo_button.grid(row=5, column=0, columnspan=2, sticky="w",
                     pady=(10, 0))
    ttk.Label(body, textvariable=status, wraplength=510, justify="left").grid(
        row=5, column=0, columnspan=3, sticky="w", pady=(4, 8))
    ttk.Label(body, text="External FFmpeg required for conversion; no network, "
              "Bluetooth, Pi, SD or original file changes.", wraplength=510).grid(
        row=6, column=0, columnspan=3, sticky="w")
    def close():
        if working[0]:
            if work_kind[0] in ("folder", "compare"):
                cancel_scan()
            elif work_kind[0] == "demo":
                messagebox.showinfo(
                    "Synthetic demo in progress",
                    "The short disposable synthetic demo is still running.",
                    parent=root)
            else:
                messagebox.showwarning(
                    "Conversion in progress",
                    "Wait for the bounded local operation to finish.",
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
    parser.add_argument("--verify-wav", help="Read-only check existing local PCM16 stereo 48 kHz WAV")
    parser.add_argument("--verify-folder", help="Read-only check 1-40 local PCM16 stereo WAVs in a folder")
    parser.add_argument("--compare-folders", nargs=2, metavar=("ORIGINAL", "COPY"),
                        help="Read-only compare WAV folder contents, independent of names/order")
    parser.add_argument("--demo", action="store_true",
                        help="Local synthetic WAV check; temporary files only, no private music/FFmpeg/Pi")
    args = parser.parse_args(argv)
    if args.demo:
        if (args.gui or args.check_local or args.convert
                or args.source is not None or args.output is not None
                or args.verify_wav is not None or args.verify_folder is not None
                or args.compare_folders is not None):
            parser.error("--demo is standalone and never reads supplied music paths")
        try:
            report = run_offline_wav_demo()
        except (OSError, ValueError, RuntimeError, wave.Error):
            print("SYNTHETIC WAV DEMO FAILED: local temporary check refused. "
                  "No personal music or Pi accessed.", file=sys.stderr)
            return 2
        print("SYNTHETIC WAV DEMO PASS: " + str(report["tracks"])
              + " disposable WAVs; renamed copy MATCH, changed content "
              "DIFFERS and requested Stop confirmed.")
        print("Demo temporary files removed; no user music, FFmpeg, network, "
              "Pi or audible hardware validated.")
        return 0
    if args.compare_folders is not None:
        if (args.gui or args.check_local or args.convert or args.source is not None
                or args.output is not None or args.verify_wav is not None
                or args.verify_folder is not None):
            parser.error("--compare-folders is a standalone read-only check")
        try:
            report = compare_local_wav_folders(*args.compare_folders)
        except (OSError, ValueError, RuntimeError):
            print("LOCAL WAV COPY REFUSED: two different safe local folders with "
                  "compatible WAVs required. No files changed.", file=sys.stderr)
            return 2
        if report["matched"]:
            print("LOCAL WAV COPY MATCH: " + str(report["source"]["files"])
                  + " PCM16 stereo 48 kHz WAVs regardless of names/order; no writes.")
            print("Copy-content SHA256: "
                  + report["source"]["copy_content_sha256"])
            print("Names, rights, later transfers and Pi audio NOT verified.")
            return 0
        print("LOCAL WAV COPY DIFFERS: contents or duplicate counts differ. "
              "No files changed.")
        print("Original WAV count: " + str(report["source"]["files"]))
        print("Copy WAV count: " + str(report["copy"]["files"]))
        print("Original copy-content SHA256: "
              + report["source"]["copy_content_sha256"])
        print("Copy copy-content SHA256: "
              + report["copy"]["copy_content_sha256"])
        print("No filename disclosure. Inspect and recopy manually.")
        return 1
    if args.verify_folder is not None:
        if (args.gui or args.check_local or args.convert
                or args.source is not None or args.output is not None
                or args.verify_wav is not None
                or args.compare_folders is not None):
            parser.error("--verify-folder is a standalone read-only check")
        try:
            report = verify_local_wav_folder(args.verify_folder)
        except (OSError, ValueError, RuntimeError):
            print("LOCAL WAV FOLDER REFUSED: empty, unsafe, changed, too large "
                  "or incompatible tracks. No files changed.", file=sys.stderr)
            return 2
        print("LOCAL WAV FOLDER VERIFIED: " + str(report["files"])
              + " PCM16 stereo 48 kHz files; no writes.")
        print("Total WAV bytes: " + str(report["bytes"]))
        print("Collection content SHA256: " + report["collection_sha256"])
        print("No filename disclosure. NOT a Pi/Edifier audio test.")
        return 0
    if args.verify_wav is not None:
        if (args.gui or args.check_local or args.convert or
                args.source is not None or args.output is not None
                or args.compare_folders is not None):
            parser.error("--verify-wav is a standalone read-only check")
        try:
            verified = verify_local_wav(args.verify_wav)
        except (OSError, ValueError, RuntimeError):
            print("LOCAL WAV REFUSED: missing, unsafe, unsupported or truncated. "
                  "No files changed.", file=sys.stderr)
            return 2
        print("LOCAL WAV VERIFIED: PCM16 stereo 48 kHz; no writes.")
        print("Duration seconds: " + str(verified["duration_seconds"]))
        print("WAV SHA256: " + verified["sha256"])
        print("NOT a Pi/Edifier speaker or owner verification.")
        return 0
    if args.check_local:
        if (args.gui or args.source is not None or args.output is not None
                or args.convert or args.compare_folders is not None):
            parser.error("--check-local cannot be combined with music paths or conversion")
        return check_local_prerequisites()
    if args.gui:
        if (args.source is not None or args.output is not None or args.convert
                or args.compare_folders is not None):
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
        print("NEW PCM16 WAV CREATED AND READ-BACK VERIFIED; original unchanged; bytes: " + str(result["bytes"]))
        print("Output SHA256: " + result["sha256"] + "; check the new WAV on the trusted PC.")
        print("Not a physical Pi/Edifier sound or ownership verification.")
        return 0
    except (OSError, ValueError, RuntimeError, PermissionError, subprocess.SubprocessError):
        print("PRIVATE EXPORT REFUSED/INCOMPLETE: check input/FFmpeg/output locally. "
              "Existing media never overwritten; no network or Pi changes.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
