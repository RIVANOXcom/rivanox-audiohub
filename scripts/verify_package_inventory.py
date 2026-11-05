#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Verify a strictly allowlisted public rootfs package inventory file.

This rejects arbitrary keys, device data and unreviewed "license approved"
claims. Availability of copyright files is NOT proof of redistribution rights.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

SCHEMA = "rivanox-audiohub-rootfs-package-inventory/1"
SCOPE = "Installed dpkg packages and copyright file hashes, NOT full SBOM or legal approval"
PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]*\Z")
VERSION = re.compile(r"[0-9][a-zA-Z0-9.+:~\-]*\Z")
ARCH = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
MAX_SIZE = 8 * 1024 * 1024
MAX_COUNT = 30000


def verify(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Package inventory missing or is a link")
    size = path.stat().st_size
    if not 0 < size <= MAX_SIZE:
        raise ValueError("Unexpected package inventory size")
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid package inventory JSON") from exc
    if (type(data) is not dict
            or set(data) != {"schema", "scope", "legal_review_approved", "summary", "packages"}
            or data.get("schema") != SCHEMA
            or data.get("scope") != SCOPE
            or data.get("legal_review_approved") is not False):
        raise ValueError("Unrecognized package inventory or forged legal approval")
    packages = data["packages"]
    summary = data["summary"]
    if (type(packages) is not list or not 0 < len(packages) <= MAX_COUNT
            or type(summary) is not dict
            or set(summary) != {"installed_packages", "copyright_files_available", "copyright_files_missing"}):
        raise ValueError("Malformed package inventory summary")
    known = set()
    available = 0
    prev = None
    for item in packages:
        if type(item) is not dict or set(item) != {
            "name", "version", "architecture", "copyright_sha256"
        }:
            raise ValueError("Unexpected or secret-bearing inventory fields")
        name, version, arch, digest = (
            item["name"], item["version"], item["architecture"], item["copyright_sha256"]
        )
        if (type(name) is not str or not PACKAGE.fullmatch(name)
                or type(version) is not str or not VERSION.fullmatch(version)
                or type(arch) is not str or not ARCH.fullmatch(arch)
                or (digest is not None
                    and (type(digest) is not str or not DIGEST.fullmatch(digest)))):
            raise ValueError("Invalid inventory package identity")
        key = (name, arch)
        if key in known or (prev is not None and key <= prev):
            raise ValueError("Duplicate or unsorted inventory package")
        known.add(key)
        prev = key
        available += digest is not None
    if (type(summary["installed_packages"]) is not int
            or type(summary["copyright_files_available"]) is not int
            or type(summary["copyright_files_missing"]) is not int
            or summary != {
                "installed_packages": len(packages),
                "copyright_files_available": available,
                "copyright_files_missing": len(packages) - available,
            }):
        raise ValueError("Inventory summary/count mismatch")
    return {
        "package_inventory_sha256": hashlib.sha256(raw).hexdigest(),
        "installed_packages": len(packages),
        "copyright_files_missing": len(packages) - available,
    }
