# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only local Pi TLS public-certificate check, never trust-on-first-use.

The certificate bytes on a Windows computer may be attacker-supplied. They
must match a SHA-256 fingerprint independently obtained on the trusted Pi
console/offline owner channel before opening a socket. This module never
discovers, downloads, accepts or installs certificate trust remotely.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import ssl
import stat

from . import secure_lan

MAX_CERT_BYTES = 64 * 1024
CERT_BEGIN = "-----BEGIN CERTIFICATE-----"
CERT_END = "-----END CERTIFICATE-----"


def _certificate_bytes(path):
    """Read a small regular public certificate, refusing symlinked paths."""
    file = Path(path)
    if not file.is_absolute():
        raise ValueError("Use an absolute path to a local public certificate")
    for part in (file, *file.parents):
        if part.is_symlink():
            raise ValueError("Linked certificate path refused")
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(file, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_CERT_BYTES:
            raise ValueError("Public certificate must be a small regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            payload = stream.read(MAX_CERT_BYTES + 1)
        if not 0 < len(payload) <= MAX_CERT_BYTES:
            raise ValueError("Oversized or empty certificate refused")
        return payload
    finally:
        os.close(fd)


def read_public_cert_der(path):
    """Parse exactly one valid X.509 PEM or DER cert using stdlib OpenSSL.

    Never uses this certificate as an automatically trusted remote peer.
    Parsing does not validate its origin or possession of a private key.
    """
    data = _certificate_bytes(path)
    if data.startswith(b"-----BEGIN"):
        try:
            text = data.decode("ascii").strip()
        except UnicodeError as exc:
            raise ValueError("Public PEM must be ASCII") from exc
        if (not text.startswith(CERT_BEGIN) or not text.endswith(CERT_END)
                or text.count(CERT_BEGIN) != 1 or text.count(CERT_END) != 1
                or "PRIVATE KEY" in text):
            raise ValueError("Provide one public X.509 PEM certificate only")
        try:
            der = ssl.PEM_cert_to_DER_cert(text)
        except (ValueError, ssl.SSLError) as exc:
            raise ValueError("Invalid public PEM certificate") from exc
        cadata = text
    else:
        # DER has a definite X.509 sequence header. Do not accept arbitrary
        # blobs or UTF-8 error pages as certificate input.
        if not data.startswith(b"\x30"):
            raise ValueError("Expected a PEM or DER public X.509 certificate")
        der = data
        cadata = data
    try:
        parser = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        parser.load_verify_locations(cadata=cadata)
    except (ValueError, ssl.SSLError) as exc:
        raise ValueError("Invalid X.509 public certificate") from exc
    return der


def certificate_sha256(path):
    """The digest of the DER public certificate, not the PEM text."""
    return hashlib.sha256(read_public_cert_der(path)).hexdigest()


def verify_public_certificate(path, independently_verified_pin):
    """Fail closed unless the local certificate equals the OFFLINE Pi pin.

    A matching locally typed hash can itself be attacker-controlled;
    the operator must establish the expected hash on a trusted Pi console.
    """
    expected = secure_lan.validate_pin(independently_verified_pin)
    actual = certificate_sha256(path)
    if not hmac.compare_digest(actual, expected):
        raise ValueError("Local Pi certificate differs from independently verified SHA256")
    return True
