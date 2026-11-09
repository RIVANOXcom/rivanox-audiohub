#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build a deterministic Windows-only source portable ALPHA; no binary release.

The fixed allowlist excludes Linux-only modules, local credentials, drivers,
OS settings and runtime data. GitHub Actions uploads the result as a
time-limited, nonreleased artifact with independently reported SHA256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

SCHEMA = "rivanox-audiohub-windows-portable-alpha/1"
CLASSIFICATION = "UNVERIFIED_ALPHA_TEST_ONLY"
FILES = (
    ("scripts/START-WINDOWS-BRIDGE.py", "START-WINDOWS-BRIDGE.py"),
    ("src/audiohub/__init__.py", "audiohub/__init__.py"),
    ("src/audiohub/secure_lan.py", "audiohub/secure_lan.py"),
    ("src/audiohub/windows_bridge_setup.py", "audiohub/windows_bridge_setup.py"),
    ("src/audiohub/windows_bridge_gui.py", "audiohub/windows_bridge_gui.py"),
    ("src/audiohub/hardware_observation.py", "audiohub/hardware_observation.py"),
    ("src/audiohub/certificate_onboarding.py", "audiohub/certificate_onboarding.py"),
    ("src/audiohub/key_onboarding.py", "audiohub/key_onboarding.py"),
    ("docs/WINDOWS-PORTABLE-ALPHA.md", "README-WINDOWS-FIRST.md"),
    ("docs/SECURE-WINDOWS-LAN-LAB.md", "README-ISOLATED-LAB.md"),
    ("LICENSE", "LICENSE"),
    ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
)


def validate_source_sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("Exact 40-character lowercase Git commit SHA is required")
    return value


def _source_data(root, rel):
    root = Path(root)
    path = root
    for piece in Path(rel).parts:
        if piece in (".", "..", "") or Path(piece).is_absolute():
            raise ValueError("Unsafe package input")
        path = path / piece
        if path.is_symlink():
            raise ValueError("Source symlink refused")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= 4 * 1024 * 1024:
        raise ValueError("Missing/oversized package input: " + rel)
    # Git may check text out with CRLF on Windows. A portable source ZIP
    # must depend on the commit, not the runner's checkout line endings.
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("Binary input forbidden in portable source package")
    data = data.replace(b"\r\n", b"\n")
    if b"\r" in data:
        raise ValueError("Unexpected carriage return in text package input")
    data.decode("utf-8")
    return data


def _entry(name, payload):
    # Fixed timestamps, POSIX regular-file permission metadata and UTF-8.
    info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    # Compression versions vary between OS runners. Small source bundle uses
    # stored members for a truly byte-identical cross-platform ZIP.
    info.compress_type = zipfile.ZIP_STORED
    info.flag_bits |= 0x800
    return info, payload


def build(root, directory, sha):
    """Write once; no overwrite and no sensitive paths from operator input."""
    sha = validate_source_sha(sha)
    root = Path(root)
    directory = Path(directory)
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("Unsafe output directory")
    directory.mkdir(parents=True, exist_ok=True)
    short = sha[:12]
    folder = "AudioHub-Windows-TLS-Bridge-ALPHA-" + short
    filename = folder + ".zip"
    target = directory / filename
    sums = directory / "SHA256SUMS-WINDOWS.txt"
    if target.exists() or target.is_symlink() or sums.exists() or sums.is_symlink():
        raise FileExistsError("Refusing to replace an existing Windows package")
    content = {}
    inventory = {}
    for source, dest in FILES:
        if dest in content:
            raise ValueError("Duplicate portable archive entry")
        payload = _source_data(root, source)
        content[dest] = payload
        inventory[dest] = {
            "source_path": source,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    manifest = {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "source_sha": sha,
        "source_license": "AGPL-3.0-only",
        "platform": "Windows 10/11, separately installed Python 3.11+",
        "hardware_verified": False,
        "public_release_ready": False,
        "driver_included": False,
        "credentials_included": False,
        "offline_certificate_sha256_verification": True,
        "offline_psk_copy_comparison_available": True,
        "offline_key_code_not_authentication": True,
        "trust_on_first_use": False,
        "windows_scream_driver_required": True,
        "driverless_speaker_soundcheck_available": True,
        "speaker_channel_soundcheck": ["both", "left", "right", "sequence"],
        "local_operator_observation_json": True,
        "manual_observation_not_hardware_approval": True,
        "windows_scream_driver_required_for_soundcheck": False,
        "source_files": inventory,
    }
    content["SOURCE-MANIFEST.json"] = (
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    # Exclusive temporary file in the same directory; incomplete archives
    # must never masquerade as a finished package.
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".windows-alpha-", suffix=".tmp", delete=False
        ) as handle:
            tmp_name = Path(handle.name)
        with zipfile.ZipFile(tmp_name, "w", compression=zipfile.ZIP_STORED,
                             strict_timestamps=True) as archive:
            for dest in sorted(content):
                archive.writestr(*_entry(folder + "/" + dest, content[dest]))
        with zipfile.ZipFile(tmp_name, "r") as archive:
            if archive.testzip() is not None:
                raise ValueError("Corrupt temporary Windows package")
            names = archive.namelist()
            if len(names) != len(content) or len(set(names)) != len(content):
                raise ValueError("Incorrect Windows package entries")
        digest = hashlib.sha256(tmp_name.read_bytes()).hexdigest()
        # No implicit replacement of a previously published candidate.
        with target.open("xb") as out, tmp_name.open("rb") as incoming:
            while data := incoming.read(1024 * 1024):
                out.write(data)
        sums.write_text(digest + "  " + filename + "\n", encoding="ascii")
        return {"file": filename, "sha256": digest, "source_sha": sha,
                "files": len(content), "classification": CLASSIFICATION}
    finally:
        if tmp_name is not None:
            tmp_name.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--directory", type=Path, default=Path("dist/windows"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        result = build(args.root, args.directory, args.source_sha)
    except (OSError, ValueError) as exc:
        parser.exit(2, "Windows ALPHA packaging refused: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
