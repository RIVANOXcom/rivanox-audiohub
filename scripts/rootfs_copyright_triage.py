#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only Debian copyright-path triage and alias-policy evidence.

This does not grant redistribution permission or attest license compliance.
Only canonical package names, fixed reason codes and aggregate counts leave
the real pi-gen rootfs. Never print package copyright text, package scripts,
maintainer addresses, device identifiers or arbitrary symlink destinations.
"""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import stat

from scripts.rootfs_package_inventory import (
    PACKAGE, VERSION, ARCH, MAX_STATUS_BYTES, _paragraphs, _copyright_hash,
)
from scripts.verify_package_inventory import verify

REASONS = {
    "doc_directory_missing",
    "doc_directory_not_directory",
    "unsafe_doc_directory_link",
    "doc_alias_target_missing",
    "doc_alias_target_not_directory",
    "doc_alias_target_link",
    "copyright_file_missing",
    "copyright_file_symlink",
    "copyright_file_not_regular",
    "copyright_file_unreadable",
    "copyright_hash_unresolved",
    "unsafe_documentation_tree",
}
ALIAS_METADATA = (
    "same_source_and_direct_dependency_declared",
    "source_mismatch",
    "direct_dependency_not_verified",
    "source_metadata_unavailable",
)


def _source_package(item: dict) -> str | None:
    """Resolve Source (version) to a package identity, never return free text."""
    name = item.get("Package")
    source = item.get("Source", name)
    if not isinstance(source, str):
        return None
    source = source.split(" (", 1)[0]
    return source if PACKAGE.fullmatch(source) is not None else None


def _depends_on(item: dict, target: str) -> bool:
    """Detect explicit direct Depends, not alternative-package installation."""
    depends = item.get("Depends", "")
    if not isinstance(depends, str):
        return False
    # A dependency may be followed by :any / :native / a version clause.
    pattern = r"(?<![a-z0-9+.-])" + re.escape(target) + r"(?=[:\s,(|]|$)"
    return re.search(pattern, depends) is not None


def _metadata(status: Path) -> dict[tuple[str, str], dict]:
    if status.is_symlink() or not status.is_file():
        raise ValueError("Rootfs dpkg status is unsafe")
    if not 0 < status.stat().st_size <= MAX_STATUS_BYTES:
        raise ValueError("Rootfs dpkg status size invalid")
    data = {}
    for item in _paragraphs(status.read_text(encoding="utf-8")):
        if item.get("Status") != "install ok installed":
            continue
        name = item.get("Package", "")
        arch = item.get("Architecture", "")
        version = item.get("Version", "")
        if (not PACKAGE.fullmatch(name) or not ARCH.fullmatch(arch)
                or not VERSION.fullmatch(version)):
            raise ValueError("Invalid rootfs dpkg package identity")
        key = (name, arch)
        if key in data:
            raise ValueError("Duplicate package/architecture in rootfs status")
        data[key] = item
    return data


def _lstat(path: Path):
    try:
        return path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _reason_for_undocumented(docs: Path, name: str) -> str:
    directory = docs / name
    st = _lstat(directory)
    if st is None:
        return "doc_directory_missing"
    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(directory)
        if target == name or PACKAGE.fullmatch(target) is None:
            return "unsafe_doc_directory_link"
        target_stat = _lstat(docs / target)
        if target_stat is None:
            return "doc_alias_target_missing"
        if stat.S_ISLNK(target_stat.st_mode):
            return "doc_alias_target_link"
        if not stat.S_ISDIR(target_stat.st_mode):
            return "doc_alias_target_not_directory"
        directory = docs / target
    elif not stat.S_ISDIR(st.st_mode):
        return "doc_directory_not_directory"
    file = directory / "copyright"
    st = _lstat(file)
    if st is None:
        return "copyright_file_missing"
    if stat.S_ISLNK(st.st_mode):
        return "copyright_file_symlink"
    if not stat.S_ISREG(st.st_mode):
        return "copyright_file_not_regular"
    try:
        if st.st_size <= 0 or st.st_size > 4 * 1024 * 1024:
            return "copyright_file_unreadable"
    except (OSError, ValueError):
        return "copyright_file_unreadable"
    return "copyright_hash_unresolved"


def analyze(rootfs: Path, inventory_path: Path) -> dict:
    rootfs = Path(rootfs)
    inventory_path = Path(inventory_path)
    if rootfs.is_symlink() or not rootfs.is_dir():
        raise ValueError("Rootfs is not a real directory")
    # The exporter has already strictly verified the exact JSON. Re-check
    # it here to ensure aliases can never be reported from forged metadata.
    proof = verify(inventory_path)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    status = _metadata(rootfs / "var/lib/dpkg/status")
    recorded = {(p["name"], p["architecture"]) for p in inventory["packages"]}
    if recorded != set(status):
        raise ValueError("Inventory differs from installed dpkg package identities")
    for item in inventory["packages"]:
        key = (item["name"], item["architecture"])
        if item["version"] != status[key]["Version"]:
            raise ValueError("Inventory package version differs from real rootfs")
    docs = rootfs / "usr/share/doc"
    valid_tree = not any((rootfs / p).is_symlink() for p in (
        "usr", "usr/share", "usr/share/doc"
    ))
    unresolved = []
    alias_info = []
    for item in inventory["packages"]:
        name = item["name"]
        arch = item["architecture"]
        source_record = status[(name, arch)]
        # Ensure package hash was computed from these actual rootfs bytes,
        # not merely a syntactically valid but stale or forged digest.
        if _copyright_hash(rootfs, name) != item["copyright_sha256"]:
            raise ValueError("Inventory copyright hash differs from real rootfs")
        if not valid_tree:
            if item["copyright_sha256"] is None:
                unresolved.append({"package": name, "reason": "unsafe_documentation_tree"})
            continue
        if item["copyright_sha256"] is None:
            reason = _reason_for_undocumented(docs, name)
            if reason not in REASONS:
                raise ValueError("Unrecognized copyright issue code")
            unresolved.append({"package": name, "reason": reason})
            continue
        directory = docs / name
        st = _lstat(directory)
        if st is None or not stat.S_ISLNK(st.st_mode):
            continue
        target = os.readlink(directory)
        if PACKAGE.fullmatch(target) is None:
            raise ValueError("Unsafe alias reported as verified copyright")
        # Prefer exact architecture; Architecture: all is also valid
        # for Debian shared documentation. Never silently select a
        # different-architecture installed source package.
        target_record = status.get((target, arch)) or status.get((target, "all"))
        if target_record is None:
            relationship = "source_metadata_unavailable"
        else:
            source_a = _source_package(source_record)
            source_b = _source_package(target_record)
            if source_a is None or source_b is None:
                relationship = "source_metadata_unavailable"
            elif source_a != source_b:
                relationship = "source_mismatch"
            elif not _depends_on(source_record, target):
                relationship = "direct_dependency_not_verified"
            else:
                relationship = "same_source_and_direct_dependency_declared"
        alias_info.append({"package": name, "shared_with": target,
                           "metadata_check": relationship})
    if len(unresolved) != proof["copyright_files_missing"]:
        raise ValueError("Unresolved copyright tally differs from inventory")
    counts = Counter(x["reason"] for x in unresolved)
    alias_counts = Counter(x["metadata_check"] for x in alias_info)
    return {
        "schema": "rivanox-audiohub-rootfs-copyright-triage/1",
        "inventory_sha256": proof["package_inventory_sha256"],
        "installed_packages": proof["installed_packages"],
        "dpkg_name_version_architecture_reconciled": True,
        "architecture_counts": dict(sorted(Counter(
            item["architecture"] for item in inventory["packages"]
        ).items())),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "unresolved_reason_counts": {k: counts[k] for k in sorted(counts)},
        "documented_directory_aliases": alias_info,
        "alias_relationship_counts": {k: alias_counts[k] for k in ALIAS_METADATA},
        "all_third_party_licenses_checked": False,
        "all_aliases_proven_policy_compliant": False,
        "commercial_redistribution_approved": False,
        "official_release_approved": False,
    }
