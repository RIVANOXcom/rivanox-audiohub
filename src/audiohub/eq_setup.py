# SPDX-License-Identifier: AGPL-3.0-only
"""Safely install the three unprivileged PipeWire EQ filters.

This startup utility must not follow a user-controlled symlink when
replacing the local EQ configuration. No network or elevated rights.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat

from .mixer import defaults, pipewire_filter_config

MAX_EQ_CONFIG_BYTES = 64 * 1024
EQ_FILE = "90-audiohub-eq.conf"


def _safe_eq_parent_fd(target):
    """Create and open the final user-private directory without symlinks."""
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError("Unsafe PipeWire EQ path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for component in target.parent.parts[1:]:
            try:
                nextfd = os.open(component, flags, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    # Another local instance may create the directory first.
                    # Reopen with O_NOFOLLOW; a raced symlink is still denied.
                    pass
                nextfd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = nextfd
        st = os.fstat(fd)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077):
            raise PermissionError("PipeWire EQ directory must be private")
        result, fd = fd, None
        return result
    finally:
        if fd is not None:
            os.close(fd)


def main():
    payload = pipewire_filter_config(defaults()).encode("utf-8")
    if not 0 < len(payload) <= MAX_EQ_CONFIG_BYTES:
        raise ValueError("PipeWire EQ configuration exceeds storage bound")
    target = Path.home() / ".config" / "pipewire" / "pipewire.conf.d" / EQ_FILE
    dirfd = _safe_eq_parent_fd(target)
    temp = "." + target.name + "." + secrets.token_hex(12) + ".tmp"
    created = False
    try:
        try:
            prior = os.stat(target.name, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError:
            prior = None
        # Do not overwrite a symlink, FIFO, hardlink or another user's file.
        if prior is not None and (
                not stat.S_ISREG(prior.st_mode) or prior.st_uid != os.geteuid()
                or prior.st_nlink != 1 or stat.S_IMODE(prior.st_mode) & 0o077):
            raise PermissionError("Unsafe existing PipeWire EQ configuration")
        out = os.open(
            temp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=dirfd,
        )
        created = True
        try:
            os.fchmod(out, 0o600)
            position = 0
            while position < len(payload):
                written = os.write(out, payload[position:])
                if written <= 0:
                    raise OSError("Incomplete PipeWire EQ configuration write")
                position += written
            os.fsync(out)
        finally:
            os.close(out)
        os.replace(temp, target.name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        created = False
        os.fsync(dirfd)
    finally:
        try:
            if created:
                try:
                    os.unlink(temp, dir_fd=dirfd)
                except OSError:
                    # Preserve the original write error even if cleanup fails.
                    pass
        finally:
            os.close(dirfd)


if __name__ == "__main__":
    main()
