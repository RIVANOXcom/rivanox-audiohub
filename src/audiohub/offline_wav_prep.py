# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in PC-side offline MP3/FLAC -> PCM16 WAV export for owned music.

Never runs on the Pi, changes an original, downloads codecs, or prints names.
FFmpeg must be independently installed on the trusted operator computer.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import io
import json
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



# Names are the existing deterministic Windows 19-member portable inventory:
# 18 source files plus SOURCE-MANIFEST.json. Do not infer trust from this
# self-described inventory; operators independently verify the downloaded ZIP.
PORTABLE_CONTENT_FILES = frozenset((
    "START-WINDOWS-BRIDGE.py",
    "START-OFFLINE-WAV-PREP.py",
    "OPEN-AUDIOHUB-MUSIC-PREP.cmd",
    "audiohub/__init__.py",
    "audiohub/offline_wav_prep.py",
    "audiohub/secure_lan.py",
    "audiohub/windows_bridge_setup.py",
    "audiohub/windows_bridge_gui.py",
    "audiohub/hardware_observation.py",
    "audiohub/certificate_onboarding.py",
    "audiohub/key_onboarding.py",
    "audiohub/key_rotation.py",
    "AUDIOHUB-BOOT-REPORT-VIEWER.html",
    "README-WINDOWS-FIRST.md",
    "README-OFFLINE-WAV-PREP.md",
    "README-ISOLATED-LAB.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
))


def inspect_local_portable_package(package_root=None, *, verify_files=True):
    """Report claimed source SHA and check packaged source bytes without writes.

    This is a self-consistency check, NOT a signature or trusted publisher
    verification: operators must independently verify the GitHub ZIP SHA256.
    """
    root = (Path(package_root) if package_root is not None
            else Path(__file__).absolute().parent.parent)
    if (not root.is_absolute() or ".." in root.parts
            or str(root).startswith("\\\\")
            or root.is_symlink()
            or any(parent.is_symlink() for parent in root.parents)):
        raise ValueError("Expected an ordinary extracted local package")
    before_root = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(before_root.st_mode):
        raise ValueError("Expected an ordinary package folder")

    manifest_path = root / "SOURCE-MANIFEST.json"
    if manifest_path.is_symlink():
        raise ValueError("Linked manifest is not a portable package")
    manifest_stat = manifest_path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(manifest_stat.st_mode)
            or not 0 < manifest_stat.st_size <= 65536):
        raise ValueError("Missing or invalid portable source manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid portable source manifest")
    sha = manifest.get("source_sha")
    if (not isinstance(sha, str) or len(sha) != 40
            or any(c not in "0123456789abcdef" for c in sha)
            or manifest.get("schema") != "rivanox-audiohub-windows-portable-alpha/1"
            or manifest.get("classification") != "UNVERIFIED_ALPHA_TEST_ONLY"
            or manifest.get("hardware_verified") is not False
            or manifest.get("public_release_ready") is not False):
        raise ValueError("Unsupported or unverified portable package")
    items = manifest.get("source_files")
    if not isinstance(items, dict) or set(items) != PORTABLE_CONTENT_FILES:
        raise ValueError("Incomplete or changed portable package inventory")
    if not verify_files:
        return {"source_sha": sha, "files": len(items), "checked": False}

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    for rel in sorted(PORTABLE_CONTENT_FILES):
        record = items[rel]
        if not isinstance(record, dict):
            raise ValueError("Invalid package member record")
        expected_size, expected_hash = record.get("bytes"), record.get("sha256")
        if (type(expected_size) is not int or not 0 < expected_size <= 4 * 1024 * 1024
                or not isinstance(expected_hash, str) or len(expected_hash) != 64
                or any(c not in "0123456789abcdef" for c in expected_hash)):
            raise ValueError("Invalid package member hash or size")
        target = root
        for part in rel.split("/"):
            target = target / part
            if target.is_symlink():
                raise ValueError("Linked package members are refused")
        start = target.stat(follow_symlinks=False)
        if (not stat.S_ISREG(start.st_mode)
                or start.st_size != expected_size):
            raise ValueError("Package member missing or size differs")
        with os.fdopen(os.open(target, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino, opened.st_size) !=
                    (start.st_dev, start.st_ino, start.st_size)):
                raise ValueError("Package member changed before check")
            digest = hashlib.sha256()
            total = 0
            while chunk := stream.read(CHUNK):
                total += len(chunk)
                if total > expected_size:
                    raise ValueError("Package member grew during check")
                digest.update(chunk)
            after = os.fstat(stream.fileno())
            if (total != expected_size or digest.hexdigest() != expected_hash
                    or (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns) !=
                    (opened.st_dev, opened.st_ino, opened.st_size,
                     opened.st_mtime_ns)):
                raise ValueError("Package member hash or metadata changed")
    after_root = root.stat(follow_symlinks=False)
    if (after_root.st_dev, after_root.st_ino, after_root.st_mtime_ns) != (
            before_root.st_dev, before_root.st_ino, before_root.st_mtime_ns):
        raise ValueError("Portable package folder changed during check")
    return {"source_sha": sha, "files": len(items), "checked": True}



def prepare_local_wav_audition(path, *, expected_sha256=None):
    """Prepare only the first <=3 seconds of a verified WAV in memory.

    Never invokes audio hardware or writes user/temporary files. The output
    is capped at 576 KiB of PCM16 WAV payload plus a small WAV header.
    """
    checked = verify_local_wav(path)
    if expected_sha256 is not None and checked["sha256"] != expected_sha256:
        raise ValueError("Previously verified WAV export changed")
    target = Path(path)
    before = target.stat(follow_symlinks=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(target, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or opened.st_size != checked["bytes"]
                or (opened.st_dev, opened.st_ino, opened.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_mtime_ns)):
            raise ValueError("WAV changed before PC audition")
        try:
            with wave.open(stream, "rb") as reader:
                if (reader.getnchannels(), reader.getsampwidth(),
                        reader.getframerate(), reader.getcomptype()) != (
                        2, 2, 48000, "NONE"):
                    raise ValueError("Only PCM16 stereo 48 kHz WAV can be auditioned")
                frames = min(reader.getnframes(), 3 * 48000)
                pcm = reader.readframes(frames)
                if len(pcm) != frames * 4:
                    raise ValueError("Incomplete PC audition WAV sample")
        except (wave.Error, EOFError) as exc:
            raise ValueError("Unreadable WAV audition") from exc
        after = os.fstat(stream.fileno())
        if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
                (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
            raise ValueError("WAV changed while preparing audition")
    if not pcm:
        raise ValueError("Empty WAV audition")
    # Preview-only conservative quarter amplitude (-12 dB). This cannot
    # increase the signal, and does not alter the source WAV or system mixer.
    # array('h') is native-endian: normalize LE PCM16 on big-endian hosts.
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    for i, value in enumerate(samples):
        samples[i] = value // 4
    if sys.byteorder != "little":
        samples.byteswap()
    pcm = samples.tobytes()
    memory = io.BytesIO()
    with wave.open(memory, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(48000)
        writer.writeframes(pcm)
    return {"wav_bytes": memory.getvalue(),
            "seconds": round(frames / 48000, 2),
            "source_sha256": checked["sha256"]}


def play_local_wav_audition(path, *, cancelled=None, sound_module=None,
                            expected_sha256=None):
    """Explicit, bounded PC-only audible preview via Windows winsound.

    Blocking playback belongs in a GUI worker; SND_MEMORY is synchronous
    because combining memory with SND_ASYNC is unsupported by Windows.
    """
    if cancelled is not None and cancelled.is_set():
        raise ScanCancelled("PC audio audition already stopped")
    if sys.platform != "win32" and sound_module is None:
        raise RuntimeError("WAV audible audition requires a Windows PC")
    report = prepare_local_wav_audition(path, expected_sha256=expected_sha256)
    if cancelled is not None and cancelled.is_set():
        raise ScanCancelled("PC audio audition stopped before playback")
    if sound_module is None:
        import winsound as sound_module
    sound_module.PlaySound(report["wav_bytes"],
                           sound_module.SND_MEMORY | sound_module.SND_NODEFAULT)
    if cancelled is not None and cancelled.is_set():
        raise ScanCancelled("PC audio audition stopped")
    return {"seconds": report["seconds"],
            "source_sha256": report["source_sha256"]}


def stop_local_wav_audition(*, sound_module=None):
    """Request Windows to stop a currently playing PlaySound sample."""
    if sys.platform != "win32" and sound_module is None:
        raise RuntimeError("PC audio stop requires Windows")
    if sound_module is None:
        import winsound as sound_module
    sound_module.PlaySound(None, 0)


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
    try:
        source_label = inspect_local_portable_package(verify_files=False)["source_sha"][:12]
    except (OSError, ValueError, RuntimeError, UnicodeError):
        source_label = "UNPACKAGED SOURCE"
    root.title("AudioHub WAV - " + source_label + " (unverified)")
    root.minsize(700, 710)
    root.columnconfigure(0, weight=1)
    body = ttk.Frame(root, padding=16)
    body.grid(sticky="nsew")
    body.columnconfigure(1, weight=1)
    source, output = tk.StringVar(master=root), tk.StringVar(master=root)
    status = tk.StringVar(master=root, value=(
        "Offline only: select your owned music and an UNUSED WAV destination."))
    approved = [None]
    automatic_output = [None]
    last_verified_export = [None]  # (immutable GUI path, verified SHA), never persisted
    pending_export_path = [None]
    working = [False]
    work_kind = ["convert"]
    results = queue.Queue(maxsize=1)
    scan_updates = queue.Queue(maxsize=1)
    scan_cancel = threading.Event()
    audition_cancel = threading.Event()

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

    def stop_audition():
        if working[0] and work_kind[0] == "audition":
            audition_cancel.set()
            audition_stop_button.configure(state="disabled")
            status.set("PC WAV PREVIEW STOP requested. At most 3 seconds; "
                       "no private media changed.")
            try:
                stop_local_wav_audition()
            except (OSError, RuntimeError):
                pass  # The bounded <=3s worker will finish independently.

    def invalidate(*_):
        approved[0] = None
        last_verified_export[0] = None
        convert_button.configure(state="disabled")
        audition_last_button.configure(state="disabled")
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
        package_button.configure(state="normal")
        audition_button.configure(state="normal")
        audition_last_button.configure(state=("normal" if last_verified_export[0]
                                              else "disabled"))
        audition_stop_button.configure(state="disabled")
        if work_kind[0] == "audition":
            if audition_cancel.is_set():
                status.set("PC WAV PREVIEW STOPPED; no files changed.")
                messagebox.showinfo("PC WAV preview stopped",
                                    "Stop requested. No music file was changed. "
                                    "This is not a Pi/Edifier sound test.",
                                    parent=root)
            elif ok:
                status.set("PC WAV SAMPLE FINISHED: " + str(value["seconds"])
                           + " seconds, Windows local speakers only. "
                           "No files changed.")
                messagebox.showinfo("Windows PC WAV sample finished",
                                    str(value["seconds"])
                                    + " seconds requested through the default "
                                    "Windows sound device. Not a verified "
                                    "Pi4/Edifier sound result. Original "
                                    "WAV unchanged.", parent=root)
            else:
                status.set("PC WAV PREVIEW REFUSED or playback failed. "
                           "No music file changed.")
                messagebox.showwarning("PC WAV preview not completed",
                                       "Choose a valid local PCM16 stereo 48 kHz "
                                       "WAV on a Windows PC with an available "
                                       "default sound device. Original untouched.",
                                       parent=root)
            return
        if work_kind[0] == "package":
            if ok:
                status.set("PACKAGE CONTENTS MATCH MANIFEST: ALPHA " +
                           value["source_sha"][:12] + "; " +
                           str(value["files"]) + " files checked. "
                           "Not a publisher signature.")
                messagebox.showinfo(
                    "Portable package contents checked",
                    "Reported source SHA256 identity (Git SHA1):\n"
                    + value["source_sha"] + "\n"
                    + str(value["files"]) + " source files match the included "
                    "SOURCE-MANIFEST.json. This is a self-consistency check, "
                    "NOT an authenticity proof. Compare the original ZIP "
                    "SHA256 from GitHub independently before use.",
                    parent=root)
            else:
                status.set("PACKAGE CHECK REFUSED: incomplete or changed "
                           "source files. Do not use this folder.")
                messagebox.showwarning(
                    "Portable package check failed",
                    "A missing, altered or unidentifiable package file was "
                    "detected. Stop using this folder. Re-extract an "
                    "independently SHA256-verified ZIP into a NEW empty "
                    "directory; keep the previous known-good version.",
                    parent=root)
            return
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
            last_verified_export[0] = (pending_export_path[0], value["sha256"])
            pending_export_path[0] = None
            audition_last_button.configure(state="normal")
            status.set("NEW WAV CREATED AND READ-BACK VERIFIED; original untouched. "
                       "SHA256: " + value["sha256"])
            messagebox.showinfo("New offline WAV verified",
                                "Final WAV reopened; PCM16 format and complete hash checked.\n"
                                 "Output SHA256:\n" + value["sha256"] +
                                "\nOriginal untouched. Use button 9 to hear "
                                "this exact export on the Windows PC. "
                                "NOT Pi/Edifier verified.", parent=root)
        else:
            pending_export_path[0] = None
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
        last_verified_export[0] = None
        pending_export_path[0] = chosen_output
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
        package_button.configure(state="disabled")
        audition_button.configure(state="disabled")
        audition_last_button.configure(state="disabled")
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
        package_button.configure(state="disabled")
        audition_button.configure(state="disabled")
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
        package_button.configure(state="disabled")
        audition_button.configure(state="disabled")
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
        package_button.configure(state="disabled")
        audition_button.configure(state="disabled")
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

    def check_package_in_gui():
        if working[0]:
            return
        working[0] = True
        work_kind[0] = "package"
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
        package_button.configure(state="disabled")
        audition_button.configure(state="disabled")
        status.set("Checking source files in this extracted local ALPHA "
                   "folder against its own manifest. No user media read.")
        def worker():
            try:
                result = inspect_local_portable_package()
                results.put((True, result))
            except (OSError, ValueError, RuntimeError, UnicodeError):
                results.put((False, None))
        threading.Thread(target=worker, daemon=True,
                         name="audiohub-offline-package-check").start()
        root.after(150, finish)

    def audition_wav(chosen=None, expected_sha256=None):
        if working[0]:
            return
        if sys.platform != "win32":
            status.set("Audible WAV preview requires a Windows PC. No sound played.")
            return
        if chosen is None:
            chosen = filedialog.askopenfilename(
                parent=root, title="Choose a local owned PCM16 stereo WAV to hear",
                filetypes=[("PCM16 WAV", "*.wav")])
        if not chosen:
            return
        consent = messagebox.askyesno(
            "Play Windows WAV sample?",
            "Audio will be audible through your DEFAULT WINDOWS PC sound "
            "device for at most 3 seconds. The sample is reduced by 12 dB "
            "and originals/system volume are untouched. Adjust volume "
            "before continuing. Your chosen WAV is read-only and no media "
            "is sent to Raspberry Pi, network or another device. "
            "This is NOT an Edifier/Pi sound check. Play now?",
            parent=root)
        if not consent:
            status.set("PC WAV sample cancelled before sound. No files changed.")
            return
        audition_cancel.clear()
        working[0] = True
        work_kind[0] = "audition"
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
        package_button.configure(state="disabled")
        audition_button.configure(state="disabled")
        audition_last_button.configure(state="disabled")
        audition_stop_button.configure(state="normal")
        status.set("Verifying WAV before audible sample; up to 3 seconds "
                   "via default Windows PC sound device. Stop available.")
        def worker():
            try:
                if expected_sha256 is None:
                    report = play_local_wav_audition(chosen,
                                                     cancelled=audition_cancel)
                else:
                    report = play_local_wav_audition(
                        chosen, cancelled=audition_cancel,
                        expected_sha256=expected_sha256)
                results.put((True, report))
            except (OSError, ValueError, RuntimeError, ScanCancelled, wave.Error):
                results.put((False, None))
        threading.Thread(target=worker, daemon=True,
                         name="audiohub-owned-wav-pc-audition").start()
        root.after(150, finish)

    def audition_last_export():
        if working[0]:
            return
        recent = last_verified_export[0]
        if recent is None:
            status.set("No newly verified WAV export available to hear. "
                       "Convert and verify one first.")
            return
        # No source or output picker: use only the last successfully verified
        # conversion's captured absolute path and full SHA256. The audition
        # helper must revalidate the original before ANY sound.
        audition_wav(recent[0], expected_sha256=recent[1])

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
    package_button = ttk.Button(
        controls, text="7. Show version and check package files (read-only)",
        command=check_package_in_gui)
    package_button.grid(row=6, column=0, columnspan=2, sticky="w",
                        pady=(10, 0))
    audition_button = ttk.Button(
        controls, text="8. Hear selected WAV on Windows PC",
        command=audition_wav)
    audition_button.grid(row=7, column=0, sticky="w",
                         padx=(0, 8), pady=(10, 0))
    audition_stop_button = ttk.Button(
        controls, text="Stop PC sound preview", state="disabled",
        command=stop_audition)
    audition_stop_button.grid(row=8, column=0, columnspan=2, sticky="w",
                              pady=(10, 0))
    audition_last_button = ttk.Button(
        controls, text="9. Hear last verified export",
        state="disabled", command=audition_last_export)
    audition_last_button.grid(row=7, column=1, sticky="w",
                              pady=(10, 0))
    ttk.Label(body, textvariable=status, wraplength=510, justify="left").grid(
        row=5, column=0, columnspan=3, sticky="w", pady=(4, 8))
    ttk.Label(body, text="Source label: " + source_label +
              " (SELF-REPORTED; verify package with button 7).",
              wraplength=510, justify="left").grid(
                  row=7, column=0, columnspan=3, sticky="w")
    ttk.Label(body, text="External FFmpeg required for conversion; no network, "
              "Bluetooth, Pi, SD or original file changes.", wraplength=510).grid(
        row=6, column=0, columnspan=3, sticky="w")
    def close():
        if working[0]:
            if work_kind[0] in ("folder", "compare"):
                cancel_scan()
            elif work_kind[0] == "audition":
                stop_audition()
                status.set("PC sound stop requested; the bounded preview "
                           "will finish before closing.")
            elif work_kind[0] in ("demo", "package"):
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
    parser.add_argument("--package-check", action="store_true",
                        help="Read-only source SHA and portable file self-consistency check")
    parser.add_argument("--audition-wav", metavar="OWNED_WAV",
                        help="Explicit Windows-only 3-second audible WAV sample; no file writes")
    args = parser.parse_args(argv)
    if args.audition_wav is not None:
        if (args.gui or args.demo or args.convert or args.check_local
                or args.package_check or args.source is not None
                or args.output is not None or args.verify_wav is not None
                or args.verify_folder is not None
                or args.compare_folders is not None):
            parser.error("--audition-wav is an exclusive audible Windows action")
        print("WINDOWS PC AUDIO REQUESTED: max 3 seconds through default "
              "PC speakers at reduced -12 dB sample level. "
              "Adjust volume. No files altered or sent to Pi.")
        try:
            report = play_local_wav_audition(args.audition_wav)
        except (OSError, ValueError, RuntimeError, ScanCancelled, wave.Error):
            print("LOCAL PC WAV AUDITION REFUSED: audio file unsupported, "
                  "changed, or Windows device unavailable. "
                  "No WAV file altered.", file=sys.stderr)
            return 2
        print("LOCAL PC WAV AUDITION FINISHED: " + str(report["seconds"])
              + " seconds requested; user must confirm actual audible output.")
        print("WAV SHA256: " + report["source_sha256"]
              + "; NOT a Pi4/Edifier sound acceptance.")
        return 0
    if args.package_check:
        if (args.gui or args.demo or args.convert or args.check_local
                or args.source is not None or args.output is not None
                or args.verify_wav is not None or args.verify_folder is not None
                or args.compare_folders is not None):
            parser.error("--package-check is standalone; no user media paths")
        try:
            report = inspect_local_portable_package()
        except (OSError, ValueError, RuntimeError, UnicodeError):
            print("LOCAL PORTABLE PACKAGE REFUSED: source manifest or "
                  "package contents missing, altered or unverifiable. "
                  "No user media inspected.", file=sys.stderr)
            return 2
        print("LOCAL PORTABLE PACKAGE MATCH: ALPHA source commit "
              + report["source_sha"] + "; " + str(report["files"])
              + " source files match bundled manifest.")
        print("SELF-CHECK ONLY: verify original ZIP SHA256 independently. "
              "Not signed, not a Pi/Windows human acceptance.")
        return 0
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
