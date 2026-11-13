# SPDX-License-Identifier: AGPL-3.0-only
"""Manually confirmed, offline, non-overwriting Pi4 WAV backup/restore.

No mounts, file deletions of user content, network services, ownership or
mode changes, privileged escalation, or in-place OS updates. The operator
provides a *pre-existing* private absolute directory on separately managed
storage. A temporary file created by this operation is removed if the
operation fails; source files and pre-existing destination files are never
modified or deleted.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import stat
import sys

from . import local_music, music_library

DEFAULT_MUSIC_DIR = "/home/audiohub/PrivateMusic"
MAX_TRANSFER_BYTES = 512 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
COPY_BUFFER = 8


def _private_dir(path):
    """Open every path component without following symlinks; require 0700."""
    if type(path) is not str or not path.startswith("/") or "\x00" in path:
        raise ValueError("An absolute private directory is required")
    parts = Path(path).parts
    if ".." in parts or len(path) > 1024:
        raise ValueError("Use a real absolute directory without parent traversal")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise PermissionError("Both music directories must be owner-only (0700)")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _source_list(path, fd):
    items, skipped = music_library.discover_library(path)
    if skipped:
        raise ValueError("Unsupported or unsafe WAV entries; check source first")
    plan = []
    size = 0
    for name, _ in items:
        st = os.stat(name.name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_nlink != 1 or st.st_mode & 0o002
                or not 44 <= st.st_size <= local_music.MAX_WAV_BYTES):
            raise ValueError("Music source has unsafe permissions or file links")
        plan.append((name.name, st.st_dev, st.st_ino, st.st_size))
        size += st.st_size
        if size > MAX_TRANSFER_BYTES:
            raise ValueError("Library exceeds bounded 512 MiB manual transfer")
    return plan, size


def _check_available(fd, bytes_needed):
    fs = os.fstatvfs(fd)
    if fs.f_bavail * fs.f_frsize < bytes_needed + 1024 * 1024:
        raise OSError("Insufficient free space on private destination")


def _verify_temp(fd, temp_name, expected_size, expected_sha):
    file_fd = os.open(temp_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        st = os.fstat(file_fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_size != expected_size
                or st.st_mode & 0o077 or st.st_nlink != 1):
            raise OSError("Temporary backup verification failed")
        digest = hashlib.sha256()
        while True:
            block = os.read(file_fd, CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
        if digest.digest() != expected_sha:
            raise OSError("Backup data checksum mismatch")
    finally:
        os.close(file_fd)


def _copy_exclusive(source_fd, target_fd, item):
    """Publish a fully verified WAV exclusively, never replace a prior file."""
    name, dev, ino, size = item
    input_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=source_fd)
    tmp = None
    try:
        st = os.fstat(input_fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_dev != dev or
                st.st_ino != ino or st.st_size != size or
                st.st_nlink != 1 or st.st_mode & 0o002 or
                st.st_uid != os.getuid()):
            raise ValueError("WAV source changed after the private preview")
        tmp = ".audiohub-transfer-" + secrets.token_hex(12) + ".part"
        output_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=target_fd)
        digest = hashlib.sha256()
        copied = 0
        try:
            while copied < size:
                block = os.read(input_fd, min(CHUNK_SIZE, size - copied))
                if not block:
                    raise OSError("Source file changed while copying")
                digest.update(block)
                pos = 0
                while pos < len(block):
                    written = os.write(output_fd, block[pos:])
                    if written <= 0:
                        raise OSError("Destination write failed")
                    pos += written
                copied += len(block)
            if os.read(input_fd, 1):
                raise OSError("Source file grew while copying")
            os.fsync(output_fd)
        finally:
            os.close(output_fd)
        _verify_temp(target_fd, tmp, size, digest.digest())
        # Hardlink creation with a *new* final name is atomic and exclusive:
        # if a competing operator created the destination, fail, never replace.
        os.link(tmp, name, src_dir_fd=target_fd, dst_dir_fd=target_fd,
                follow_symlinks=False)
        os.fsync(target_fd)
        return digest.hexdigest()
    finally:
        os.close(input_fd)
        if tmp is not None:
            try:
                os.unlink(tmp, dir_fd=target_fd)
            except FileNotFoundError:
                pass


def transfer(direction, external, *, music_dir=DEFAULT_MUSIC_DIR,
             confirm=None, out=print, require_terminal=True):
    """Copy privately selected WAVs to/from independent storage on request.

    A canceled confirmation performs zero writes. Existing destination
    names, symlinks, directories and all source contents are never touched.
    A failed multi-file transfer may leave already completed *new* files,
    which are not deleted automatically and must be inspected by operator.
    """
    if direction not in ("backup", "restore"):
        raise ValueError("Choose backup or restore")
    if os.geteuid() == 0:
        raise PermissionError("Private WAV transfers cannot run as root")
    if require_terminal and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise PermissionError("Manual WAV transfer requires a trusted local terminal")
    if confirm is None:
        def confirm():
            try:
                reply = sys.stdin.readline(COPY_BUFFER)
                return reply == "COPY\n"
            except (OSError, UnicodeError, EOFError, ValueError):
                return False

    source = music_dir if direction == "backup" else external
    target = external if direction == "backup" else music_dir
    source_fd = _private_dir(source)
    try:
        target_fd = _private_dir(target)
        try:
            a, b = os.fstat(source_fd), os.fstat(target_fd)
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
                raise ValueError("Source and destination must be different")
            plan, size = _source_list(source, source_fd)
            for filename, *_ in plan:
                try:
                    os.stat(filename, dir_fd=target_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise FileExistsError("A destination WAV already exists; no file overwritten")
            _check_available(target_fd, size)
            out("Private WAV " + direction + " preview: " + str(len(plan)) +
                " supported tracks, " + str(size) +
                " bytes. Source preserved. Nothing written yet.")
            out("Type exact uppercase COPY then Enter to create new copies."
                " Anything else cancels without writing.")
            if confirm() is not True:
                out("Transfer cancelled; no WAV files created.")
                return False
            count = 0
            combined = hashlib.sha256()
            for item in plan:
                digest = _copy_exclusive(source_fd, target_fd, item)
                combined.update(item[0].encode("utf-8", errors="surrogateescape"))
                combined.update(b"\0" + digest.encode("ascii") + b"\n")
                count += 1
            out("Transfer complete: " + str(count) + " new WAV copies; " +
                str(size) + " bytes. Source left unchanged.")
            out("Private transfer fingerprint (order and content): " +
                combined.hexdigest() + ". Keep for operator comparison.")
            return True
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--help"] or args == ["-h"]:
        print("AudioHub offline WAV transfer; no automatic SD migration.")
        print("Usage: audiohub-music-transfer backup /absolute/private/external-folder")
        print("       audiohub-music-transfer restore /absolute/private/external-folder")
        print("Source and target directories must exist, be owned by you and private 0700.")
        print("Only up to 40 playable WAVs / 512 MiB, no other file types, no overwrites.")
        print("This copies only after exact COPY at a local unprivileged terminal.")
        print("Keep your old SD, external media and independent backup intact.")
        return 0
    if len(args) != 2 or args[0] not in ("backup", "restore"):
        print("Choose backup or restore and one absolute private folder. Use --help.")
        return 2
    try:
        return 0 if transfer(args[0], args[1]) else 1
    except (OSError, ValueError, PermissionError):
        print("Safe offline WAV transfer refused or incomplete; previous source untouched.")
        print("If a copy failed, some NEW destination files may exist; inspect privately.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
