# SPDX-License-Identifier: AGPL-3.0-only
"""Unintegrated, fail-closed durable owner record prototype (AH-005).

A record is NOT proof of owner identity. This primitive never authorizes
onboarding or supplies a trusted factory-state/physical-presence check.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

RECORD_NAME = "owner-claim.json"
MAX_RECORD_BYTES = 512
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class OwnerStoreError(Exception):
    """An operation was denied without granting owner privileges."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate owner record field")
        result[key] = value
    return result


class OwnerRecordStore:
    """Immutable single-record persistence with restricted Linux directory FDs.

    The directory must already exist, be owned by the current process UID,
    and deny group/other access. Never create it from untrusted HTTP input.
    """

    def __init__(self, directory):
        self.directory = Path(directory)
        if not self.directory.is_absolute():
            raise ValueError("Owner record directory must be absolute")

    def _open_directory(self):
        fd = os.open(
            self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            os.close(fd)
            raise OwnerStoreError("Protected owner directory unavailable")
        return fd

    @staticmethod
    def _read_record(directory_fd):
        """Return (structural condition, verified-format fingerprint or None)."""
        try:
            fd = os.open(
                RECORD_NAME,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return "missing_untrusted", None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or info.st_size > MAX_RECORD_BYTES):
                return "invalid", None
            raw = os.read(fd, MAX_RECORD_BYTES + 1)
            if len(raw) > MAX_RECORD_BYTES:
                return "invalid", None
            try:
                record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            except (UnicodeError, ValueError, TypeError):
                return "invalid", None
            if (type(record) is not dict or set(record) != {
                "schema_version", "state", "owner_key_sha256"
            } or type(record["schema_version"]) is not int
                    or record["schema_version"] != 1
                    or record["state"] != "claimed"
                    or type(record["owner_key_sha256"]) is not str
                    or not _DIGEST.fullmatch(record["owner_key_sha256"])):
                return "invalid", None
            return "record_present_unverified", record["owner_key_sha256"]
        finally:
            os.close(fd)

    def _inspect_record(self):
        """Read through protected directory and file handles, deny on any error."""
        try:
            fd = self._open_directory()
        except (OSError, OwnerStoreError):
            return "invalid", None
        try:
            return self._read_record(fd)
        except (OSError, ValueError):
            return "invalid", None
        finally:
            os.close(fd)

    def inspect(self):
        """Structural result only; presence never authenticates the owner."""
        condition, _ = self._inspect_record()
        return {
            "record_condition": condition,
            "durable_owner_verified": False,
            "network_onboarding_enabled": False,
            "release_ready": False,
        }

    def matches_public_key(self, public_key):
        """Compare a candidate Ed25519 key fingerprint with a protected record.

        This does NOT verify a signature or authorize a request. The caller
        must independently verify proof of private-key possession.
        """
        if type(public_key) is not bytes or len(public_key) != 32:
            return False
        condition, fingerprint = self._inspect_record()
        if condition != "record_present_unverified" or fingerprint is None:
            return False
        candidate = hashlib.sha256(public_key).hexdigest()
        return hmac.compare_digest(fingerprint, candidate)

    def seal(self, public_key, *, trusted_physical_approval=False,
             trusted_factory_unowned=False):
        """Permanently write a *public-key fingerprint*, not a session token.

        Both booleans MUST come from a future separately verified privileged
        adapter. They are NOT evidence of a real hardware event. An existing
        record is never overwritten, including invalid records. No factory
        reset and no automatic re-enrollment are implemented here.
        """
        if (trusted_physical_approval is not True
                or trusted_factory_unowned is not True
                or type(public_key) is not bytes or len(public_key) != 32):
            raise OwnerStoreError("Trusted enrollment prerequisites missing")
        data = {
            "schema_version": 1,
            "state": "claimed",
            "owner_key_sha256": hashlib.sha256(public_key).hexdigest(),
        }
        payload = (json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n").encode()
        with_fd = None
        try:
            with_fd = self._open_directory()
            # O_EXCL enforces no overwrite, even if another process races us.
            fd = os.open(
                RECORD_NAME,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600, dir_fd=with_fd,
            )
            try:
                os.fchmod(fd, 0o600)
                cursor = 0
                while cursor < len(payload):
                    count = os.write(fd, payload[cursor:])
                    if count <= 0:
                        raise OSError("Owner record write failed")
                    cursor += count
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(with_fd)
        except (OSError, OwnerStoreError) as exc:
            # A partial file after interrupted write remains invalid/claimed:
            # never delete or silently reopen factory enrollment.
            raise OwnerStoreError("Owner record not securely committed") from exc
        finally:
            if with_fd is not None:
                os.close(with_fd)
        return self.inspect()
