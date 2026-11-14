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


def _source_list(path, fd, *, allow_empty=False):
    # Only the combined preset/SD-data migration may explicitly accept an
    # empty, otherwise validated private WAV source. The normal WAV transfer
    # still refuses to certify an empty source.
    if type(allow_empty) is not bool:
        raise ValueError("Invalid empty music-source policy")
    items, skipped = (music_library.discover_library(path, allow_empty=True)
                      if allow_empty else music_library.discover_library(path))
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


def _file_digest(fd, size):
    """Hash exactly one bounded regular file without accepting mid-read growth."""
    digest = hashlib.sha256()
    remaining = size
    while remaining:
        block = os.read(fd, min(CHUNK_SIZE, remaining))
        if not block:
            raise OSError("A WAV changed during verification")
        digest.update(block)
        remaining -= len(block)
    if os.read(fd, 1):
        raise OSError("A WAV grew during verification")
    return digest.hexdigest()


def _matching_destination(source_fd, target_fd, item):
    """Return matching SHA256, None for absence; refuse unsafe/conflicting files.

    No destination is modified. Both ends are opened beneath already verified
    private directory descriptors and must remain the same file through hashing.
    """
    name, dev, ino, size = item
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        dst = os.open(name, flags, dir_fd=target_fd)
    except FileNotFoundError:
        return None
    try:
        src = os.open(name, flags, dir_fd=source_fd)
        try:
            a, b = os.fstat(src), os.fstat(dst)
            if (not stat.S_ISREG(a.st_mode) or not stat.S_ISREG(b.st_mode)
                    or (a.st_dev, a.st_ino, a.st_size) != (dev, ino, size)
                    or b.st_size != size or a.st_uid != os.getuid()
                    or b.st_uid != os.getuid()
                    or a.st_nlink != 1 or b.st_nlink != 1
                    or a.st_mode & 0o002 or b.st_mode & 0o077
                    or (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)):
                raise ValueError("Existing destination WAV is unsafe or conflicting")
            source_hash = _file_digest(src, size)
            target_hash = _file_digest(dst, size)
            a2, b2 = os.fstat(src), os.fstat(dst)
            for before, after in ((a, a2), (b, b2)):
                if (before.st_dev, before.st_ino, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns):
                    raise OSError("A WAV changed during verification")
            if source_hash != target_hash:
                raise ValueError("Existing destination WAV differs; no overwrite")
            return source_hash
        finally:
            os.close(src)
    finally:
        os.close(dst)


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
            # Re-read the bounded source after the copy: refuse if an operator
            # edited its bytes concurrently while retaining size and inode.
            os.lseek(input_fd, 0, os.SEEK_SET)
            source_digest = hashlib.sha256()
            check_size = 0
            while check_size < size:
                check = os.read(input_fd, min(CHUNK_SIZE, size - check_size))
                if not check:
                    raise OSError("Source file changed while copying")
                source_digest.update(check)
                check_size += len(check)
            if source_digest.digest() != digest.digest():
                raise OSError("Source WAV changed while copying")
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
             confirm=None, out=print, require_terminal=True,
             resume=False, verify=False):
    """Manual WAV copy, optional safe resume, or read-only source-set check.

    Resume preflights EVERY colliding destination, hashing both files before
    any new copy. Differences, hardlinks, symlinks and unsafe owners refuse
    the whole operation. A failed multi-file copy may leave completed new
    files; a subsequent explicitly requested resume can skip exact matches.
    Verification checks each source WAV has an identical, safe destination
    WAV. It does not assert destination contains no extra files.
    """
    if direction not in ("backup", "restore"):
        raise ValueError("Choose backup or restore")
    if type(resume) is not bool or type(verify) is not bool or (resume and verify):
        raise ValueError("Choose normal copy, resume or read-only verification")
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
            if (resume or verify) and not plan:
                raise ValueError("No supported WAVs to resume or verify")
            matched = {}
            pending = []
            for item in plan:
                name = item[0]
                if resume or verify:
                    match = _matching_destination(source_fd, target_fd, item)
                    if match is not None:
                        matched[name] = match
                        continue
                    if verify:
                        raise FileNotFoundError("A destination WAV is missing")
                else:
                    try:
                        os.stat(name, dir_fd=target_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise FileExistsError(
                            "A destination WAV already exists; no file overwritten")
                pending.append(item)

            if not verify:
                bytes_new = sum(item[3] for item in pending)
                if pending:
                    _check_available(target_fd, bytes_new)
                out("Private WAV " + direction + " preview: " + str(len(plan)) +
                    " supported tracks, " + str(size) + " bytes; " +
                    str(len(matched)) + " verified existing, " +
                    str(len(pending)) + " new. Source preserved. Nothing written yet.")
                if pending:
                    out("Type exact uppercase COPY then Enter to create new copies."
                        " Anything else cancels without writing.")
                    if confirm() is not True:
                        out("Transfer cancelled; no WAV files created.")
                        return False
            else:
                bytes_new = 0

            combined = hashlib.sha256()
            for item in plan:
                digest = matched.get(item[0])
                if digest is None:
                    digest = _copy_exclusive(source_fd, target_fd, item)
                combined.update(item[0].encode("utf-8", errors="surrogateescape"))
                combined.update(b"\0" + digest.encode("ascii") + b"\n")

            # Detect a pre-existing file replaced during a long copy, as well
            # as a new file changed after publication. Refuse a false success.
            if resume or verify:
                for item in plan:
                    again = _matching_destination(source_fd, target_fd, item)
                    if again is None or (
                            item[0] in matched and again != matched[item[0]]):
                        raise OSError("A WAV disappeared or changed during transfer")
                # Every new and previously existing copy has been rechecked.
            if verify:
                out("Verification complete: " + str(len(plan)) +
                    " source WAVs match destination; no files written.")
            else:
                out("Transfer complete: " + str(len(pending)) +
                    " new WAV copies; " + str(bytes_new) +
                    " bytes. Source left unchanged.")
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
        print("Usage: audiohub-music-transfer backup /absolute/private/external-folder [--resume]")
        print("       audiohub-music-transfer restore /absolute/private/external-folder [--resume]")
        print("       audiohub-music-transfer verify-backup /absolute/private/external-folder")
        print("       audiohub-music-transfer verify-restore /absolute/private/external-folder")
        print("       audiohub-music-transfer backup-old ABSOLUTE_OLD_SD_MUSIC_DIR ABSOLUTE_PRIVATE_ARCHIVE [--resume]")
        print("       audiohub-music-transfer verify-backup-old ABSOLUTE_OLD_SD_MUSIC_DIR ABSOLUTE_PRIVATE_ARCHIVE")
        print("Source and target directories must exist, be owned by you and private 0700.")
        print("Only up to 40 playable WAVs / 512 MiB, no other file types, no overwrites.")
        print("Default copy refuses collisions. --resume skips only identical safe WAVs.")
        print("backup-old reads a separately mounted read-only old SD; it never mounts or edits it.")
        print("The old SD does not need an installed AudioHub transfer utility.")
        print("verify-backup/verify-restore read and compare, never write or request COPY.")
        print("New copies require exact COPY at a trusted local unprivileged terminal.")
        print("Keep your old SD, external media and independent backup intact.")
        return 0
    old_backup = (len(args) in (3, 4) and args[0] == "backup-old"
                  and (len(args) == 3 or args[3] == "--resume"))
    old_verify = (len(args) == 3 and args[0] == "verify-backup-old")
    standard = (
        len(args) in (2, 3)
        and args[0] in ("backup", "restore", "verify-backup", "verify-restore")
        and (len(args) == 2 or
             (args[2] == "--resume" and
              args[0] in ("backup", "restore")))
    )
    if not (standard or old_backup or old_verify):
        print("Choose a supported WAV copy or read-only verification action.")
        print("backup-old takes OLD_MUSIC_DIR and PRIVATE_ARCHIVE, optional --resume.")
        print("verify-backup-old takes OLD_MUSIC_DIR and PRIVATE_ARCHIVE (no --resume).")
        return 2
    try:
        if old_backup or old_verify:
            # The old SD need not contain this launcher or any executable:
            # the *new* SD performs all access through the same bounded,
            # no-symlink, private directory-descriptor transfer engine.
            # The first explicit path is always READ ONLY; the archive is
            # written exclusively only for backup-old with exact COPY.
            return 0 if transfer(
                "backup", args[2], music_dir=args[1],
                resume=len(args) == 4, verify=old_verify
            ) else 1
        is_verify = args[0].startswith("verify-")
        direction = args[0].removeprefix("verify-")
        return 0 if transfer(direction, args[1],
                             resume=len(args) == 3,
                             verify=is_verify) else 1
    except (OSError, ValueError, PermissionError):
        print("Safe offline WAV transfer refused or incomplete; previous source untouched.")
        print("If a copy failed, some NEW destination files may exist; inspect privately.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
