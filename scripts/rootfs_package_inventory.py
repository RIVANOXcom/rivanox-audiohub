#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Inventory the actual dpkg-installed packages in a Pi image rootfs.

This is a reproducible compliance *input*, not a completed SBOM, legal
clearance, a firmware audit, or an authorization to distribute the image.
Never export package postinst scripts, environment or device credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SCHEMA = "rivanox-audiohub-rootfs-package-inventory/1"
PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]*\Z")
VERSION = re.compile(r"[0-9][a-zA-Z0-9.+:~\-]*\Z")
ARCH = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
MAX_PACKAGE_COUNT = 30000
MAX_STATUS_BYTES = 32 * 1024 * 1024
MAX_COPYRIGHT_BYTES = 4 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024


def _paragraphs(contents: str):
    for block in re.split(r"\n\s*\n", contents):
        if not block.strip():
            continue
        fields = {}
        for line in block.splitlines():
            if not line or line[0].isspace():
                continue  # Description and other folded fields are ignored.
            key, sep, value = line.partition(":")
            if not sep or key in fields:
                raise ValueError("Malformed or repeated dpkg status field")
            fields[key] = value.strip()
        if fields:
            yield fields


def _copyright_hash(root: Path, name: str):
    directory = root / "usr/share/doc" / name
    file = directory / "copyright"
    # Do not follow arbitrary links out of an image onto the CI host.
    if directory.is_symlink() or file.is_symlink() or not file.is_file():
        return None
    size = file.stat().st_size
    if size <= 0 or size > MAX_COPYRIGHT_BYTES:
        return None
    checksum = hashlib.sha256()
    with file.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            checksum.update(block)
    return checksum.hexdigest()


def inventory(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Rootfs must be a real directory")
    status = root / "var/lib/dpkg/status"
    if status.is_symlink() or not status.is_file():
        raise ValueError("dpkg status missing or unsafe")
    if not 0 < status.stat().st_size <= MAX_STATUS_BYTES:
        raise ValueError("Unexpected dpkg status file size")
    try:
        contents = status.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ValueError("Invalid dpkg status encoding") from exc
    entries = []
    names = set()
    available = 0
    for item in _paragraphs(contents):
        if item.get("Status") != "install ok installed":
            continue
        name = item.get("Package", "")
        version = item.get("Version", "")
        arch = item.get("Architecture", "")
        if (not PACKAGE.fullmatch(name) or not VERSION.fullmatch(version)
                or not ARCH.fullmatch(arch)):
            raise ValueError("Unsafe or malformed installed-package metadata")
        key = (name, arch)
        if key in names:
            raise ValueError("Duplicate installed package/architecture")
        names.add(key)
        license_hash = _copyright_hash(root, name)
        available += license_hash is not None
        entries.append({
            "name": name,
            "version": version,
            "architecture": arch,
            "copyright_sha256": license_hash,
        })
        if len(entries) > MAX_PACKAGE_COUNT:
            raise ValueError("Too many installed packages")
    if not entries:
        raise ValueError("No installed dpkg packages")
    entries.sort(key=lambda p: (p["name"], p["architecture"]))
    return {
        "schema": SCHEMA,
        "scope": "Installed dpkg packages and copyright file hashes, NOT full SBOM or legal approval",
        "legal_review_approved": False,
        "summary": {
            "installed_packages": len(entries),
            "copyright_files_available": available,
            "copyright_files_missing": len(entries) - available,
        },
        "packages": entries,
    }


def write_inventory(root: Path, output: Path) -> dict:
    result = inventory(root)
    payload = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("Package inventory report too large")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise ValueError("Unsafe inventory output destination")
    tmp = output.with_name(output.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise ValueError("Stale inventory temporary file")
    try:
        with tmp.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = write_inventory(args.rootfs, args.output)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, "Rootfs package inventory REFUSED: " + str(exc) + "\n")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
