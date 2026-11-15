#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline verification of a temporary image bundle; NEVER approves a Release.

A successful integrity check does not certify Pi4 boot, security, compliance,
copyright ownership, hardware sound, or authorization to distribute an image.
Keep the official publish-image.yml job blocked until separate human gates pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_package_inventory import verify as verify_package_inventory
from scripts.verify_package_inventory import MAX_SIZE as MAX_INVENTORY_BYTES

PREVIEW_SCHEMA = "rivanox-audiohub-preview-bundle/2"
REPORT_SCHEMA = "rivanox-audiohub-release-preflight/1"
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*-UNVERIFIED\.img\.xz\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
MAX_META_BYTES = 8192
MAX_IMAGE_BYTES = 16 * 1024**3
MAX_UNCOMPRESSED_BYTES = 64 * 1024**3
MAX_ZIP_BYTES = MAX_IMAGE_BYTES + MAX_INVENTORY_BYTES + 64 * 1024**2
MISSING_GATES = (
    "physical_pi4_edifier_boot_audio_and_recovery",
    "headless_physical_ownership_and_authenticated_phone_setup",
    "three_input_peak_and_transport_security_acceptance",
    "third_party_license_sbom_and_redistribution_review",
    "operator_approval_and_release_asset_review",
)


def _regular(path: Path, *, max_bytes=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Bundle must contain only regular files, not links")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size <= 0:
        raise ValueError("Empty, linked or nonregular artifact rejected")
    if max_bytes is not None and st.st_size > max_bytes:
        raise ValueError("Oversized release preflight input rejected")
    return st.st_size


def inspect(directory: Path, *, expected_source_sha=None, verify_xz=True):
    """Verify *temporary* Pi alpha bundle integrity with immutable no-GO result.

    A reviewer must independently assess the hardware/legal gates. No argument
    or manifest flag can change the result into public release authorization.
    """
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Bundle directory is missing or is a symbolic link")
    children = tuple(directory.iterdir())
    images = [p for p in children if p.name.endswith(".img.xz")]
    if len(images) != 1 or IMAGE.fullmatch(images[0].name) is None:
        raise ValueError("Exactly one UNVERIFIED Pi image required")
    image = images[0]
    required = {image.name, "SHA256SUMS.txt", "PREVIEW-MANIFEST.json", "ROOTFS-PACKAGES.json"}
    if {p.name for p in children} != required or len(children) != 4:
        raise ValueError("Unexpected, missing or extra files in preview ZIP")
    _regular(image, max_bytes=MAX_IMAGE_BYTES)
    checksum_file = directory / "SHA256SUMS.txt"
    manifest_file = directory / "PREVIEW-MANIFEST.json"
    _regular(checksum_file, max_bytes=MAX_META_BYTES)
    _regular(manifest_file, max_bytes=MAX_META_BYTES)
    inventory_proof = verify_package_inventory(directory / "ROOTFS-PACKAGES.json")
    if expected_source_sha is not None and (
        type(expected_source_sha) is not str or SHA40.fullmatch(expected_source_sha) is None
    ):
        raise ValueError("Invalid expected source commit")
    try:
        meta = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Malformed preview provenance") from exc
    if type(meta) is not dict or meta.get("schema") != PREVIEW_SCHEMA:
        raise ValueError("Wrong provenance format")
    if meta.get("package_inventory") != {"file": "ROOTFS-PACKAGES.json", **inventory_proof}:
        raise ValueError("Installed package inventory provenance mismatch")
    if meta.get("image") != image.name or (
        type(meta.get("image_bytes")) is not int
        or meta["image_bytes"] != image.stat().st_size
    ):
        raise ValueError("Image identity/size mismatch")
    digest = meta.get("image_sha256")
    source_sha = meta.get("source_commit_sha")
    pin = meta.get("pi_gen_commit_sha")
    run_id = meta.get("github_actions_run_id")
    if (type(digest) is not str or SHA64.fullmatch(digest) is None
            or type(source_sha) is not str or SHA40.fullmatch(source_sha) is None
            or type(pin) is not str or SHA40.fullmatch(pin) is None
            or type(run_id) is not str or re.fullmatch(r"[0-9]{1,20}", run_id) is None):
        raise ValueError("Invalid artifact provenance IDs")
    if expected_source_sha is not None and source_sha != expected_source_sha:
        raise ValueError("Source revision mismatch")
    if (meta.get("hardware_verified") is not False
            or meta.get("release_approved") is not False
            or meta.get("supports_phone_wifi_setup") is not False
            or "not a release" not in str(meta.get("scope", "")).lower()):
        raise ValueError("Preview may not claim hardware or release approval")
    # ASCII exact line: no additional hashes, untracked files or names.
    try:
        expected = checksum_file.read_text(encoding="ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid checksum encoding") from exc
    if expected != f"{digest}  {image.name}\n":
        raise ValueError("Checksum line disagrees with signed-off preview metadata")
    checksum = hashlib.sha256()
    with image.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    if checksum.hexdigest() != digest:
        raise ValueError("Image checksum differs from manifest and SHA256SUMS")
    if verify_xz:
        try:
            size = 0
            with lzma.open(image, "rb") as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_UNCOMPRESSED_BYTES:
                        raise ValueError("Decompressed image too large")
            if size == 0:
                raise ValueError("Empty decompressed image")
        except (lzma.LZMAError, EOFError, OSError) as exc:
            raise ValueError("XZ decompression/integrity test failed") from exc
    # Immutable NO-GO output. No source-side option can "approve" publication.
    return {
        "schema": REPORT_SCHEMA,
        "bundle_integrity": "passed",
        "classification": "UNVERIFIED_ALPHA_TEST_ONLY",
        "public_release_ready": False,
        "hardware_verified": False,
        "source_sha": source_sha,
        "pi_gen_sha": pin,
        "actions_run_id": run_id,
        "image_sha256": digest,
        "image": image.name,
        "package_inventory_sha256": inventory_proof["package_inventory_sha256"],
        "installed_packages": inventory_proof["installed_packages"],
        "copyright_files_missing": inventory_proof["copyright_files_missing"],
        "missing_human_gates": list(MISSING_GATES),
    }


def inspect_zip(archive: Path, *, expected_zip_sha256, expected_source_sha=None,
                verify_xz=True):
    """One-command offline operator inspection of the *downloaded* ZIP.

    Unlike CI's already-unpacked preview, an operator must prove that the
    downloaded ZIP's bytes match the pinned GitHub-provider digest before
    extracting anything. Extract only four allowlisted flat, bounded files
    into a short-lived private temporary directory; NEVER flash an SD.
    """
    if type(expected_zip_sha256) is not str or SHA64.fullmatch(expected_zip_sha256) is None:
        raise ValueError("Expected exact 64-character ZIP SHA256 is required")
    if (type(expected_source_sha) is not str or
            SHA40.fullmatch(expected_source_sha) is None):
        raise ValueError("Expected exact 40-character source SHA is required")
    archive = Path(archive)
    _regular(archive, max_bytes=MAX_ZIP_BYTES)
    outer = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            outer.update(block)
    if outer.hexdigest() != expected_zip_sha256:
        raise ValueError("Downloaded ZIP SHA256 mismatch; do NOT extract/flash")

    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if len(members) != 4:
                raise ValueError("Operator ZIP must contain exactly four files")
            names = [item.filename for item in members]
            images = [n for n in names if IMAGE.fullmatch(n)]
            if (len(images) != 1 or len(set(names)) != 4 or
                    set(names) != {
                        images[0], "SHA256SUMS.txt", "PREVIEW-MANIFEST.json",
                        "ROOTFS-PACKAGES.json",
                    }):
                raise ValueError("Unsafe, duplicate or unexpected ZIP members")
            bounds = {
                images[0]: MAX_IMAGE_BYTES,
                "SHA256SUMS.txt": MAX_META_BYTES,
                "PREVIEW-MANIFEST.json": MAX_META_BYTES,
                "ROOTFS-PACKAGES.json": MAX_INVENTORY_BYTES,
            }
            for item in members:
                # Accept standard Unix regular or Windows ZIP entries, not
                # symlinks, devices, directories, encrypted or nested files.
                mode = (item.external_attr >> 16) & 0o170000
                if (item.is_dir() or mode not in (0, stat.S_IFREG) or
                        item.flag_bits & 1 or
                        item.compress_type not in (
                            zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or
                        not 0 < item.file_size <= bounds[item.filename] or
                        item.compress_size <= 0):
                    raise ValueError("Unsafe ZIP member type, size or encryption")
            with tempfile.TemporaryDirectory(prefix="audiohub-test-zip-") as temp:
                directory = Path(temp)
                for item in members:
                    limit = bounds[item.filename]
                    written = 0
                    # No ZipFile.extract(): no untrusted path joins or attrs.
                    with zf.open(item) as source, (
                            directory / item.filename).open("xb") as dest:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            written += len(chunk)
                            if written > limit:
                                raise ValueError("ZIP member exceeded size bound")
                            dest.write(chunk)
                    if written != item.file_size:
                        raise ValueError("ZIP member extracted size mismatch")
                result = inspect(
                    directory, expected_source_sha=expected_source_sha,
                    verify_xz=verify_xz)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
        raise ValueError("Corrupted or unsupported operator ZIP") from exc
    # No other filesystem changes, release auth or runtime settings.
    return {**result, "download_zip_sha256": expected_zip_sha256,
            "verified_zip_entries": 4}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--directory", type=Path,
                         help="Already extracted four-file preview bundle (CI)")
    choices.add_argument("--zip", type=Path,
                         help="Downloaded GitHub Actions TEST ZIP, offline/read-only")
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-zip-sha256",
                        help="Required in --zip mode; exact provider ZIP digest")
    args = parser.parse_args(argv)
    try:
        if args.zip is not None:
            result = inspect_zip(
                args.zip, expected_zip_sha256=args.expected_zip_sha256,
                expected_source_sha=args.expected_source_sha)
        else:
            if args.expected_zip_sha256 is not None:
                raise ValueError("ZIP SHA256 is only valid in --zip mode")
            result = inspect(args.directory, expected_source_sha=args.expected_source_sha)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, "AudioHub preview preflight REFUSED: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
