# SPDX-License-Identifier: AGPL-3.0-only
"""Optional offline equality check for two copies of a 32-byte lab PSK.

The check code is a truncated, domain-separated HMAC of the secret, NOT
authentication, a replacement secret, or proof of physical Pi ownership.
Never publish the code: it can aid guesses if the underlying PSK is weak.
No sockets, writes, automatic key creation, transfer, or rotation.
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from . import secure_lan

CHECK_DOMAIN = b"RIVANOX-AUDIOHUB-OFFLINE-PSK-CHECK-v1"
CHECK_CODE_HEX = 32


def code_from_key_bytes(key):
    """Derive a 128-bit comparison code from a full-entropy private PSK."""
    key = secure_lan.validate_key_bytes(key)
    return hmac.new(key, CHECK_DOMAIN, hashlib.sha256).hexdigest()[:CHECK_CODE_HEX]


def validate_check_code(expected):
    if (not isinstance(expected, str) or len(expected) != CHECK_CODE_HEX
            or any(ch not in "0123456789abcdef" for ch in expected)):
        raise ValueError("Pi offline key code must be 32 lowercase hex digits")
    return expected


def verify_key_bytes(key, independently_verified_code):
    expected = validate_check_code(independently_verified_code)
    if not hmac.compare_digest(code_from_key_bytes(key), expected):
        raise ValueError("Local 32-byte key differs from the trusted Pi key code")
    return True


def local_key_code(path):
    """Read existing private key under the bridge's normal strict rules."""
    file = Path(path)
    if not file.is_absolute():
        raise ValueError("Use an absolute path to a private key")
    for part in (file, *file.parents):
        if part.is_symlink():
            raise ValueError("Linked private key paths refused")
    return code_from_key_bytes(secure_lan.read_private_key(file))


def verify_local_key_code(path, independently_verified_code):
    expected = validate_check_code(independently_verified_code)
    if not hmac.compare_digest(local_key_code(path), expected):
        raise ValueError("Local 32-byte key differs from the trusted Pi key code")
    return True
