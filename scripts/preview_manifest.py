#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Create a traceable, explicitly UNVERIFIED GitHub Actions image manifest.

Only run after verifying the compressed image's SHA256 and xz integrity.
This is distribution metadata, NOT hardware evidence or release approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SHA = re.compile(r"[a-f0-9]{40}\Z")
RUN = re.compile(r"[0-9]{1,20}\Z")
PIN = re.compile(r'^PIN="([a-f0-9]{40})"$', re.MULTILINE)
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.img\.xz\Z")


def manifest(directory: Path, source_sha: str, run_id: str, build_script: Path):
    """Validate exact bundle identity before creating PREVIEW-MANIFEST.json."""
    if not SHA.fullmatch(source_sha) or not RUN.fullmatch(run_id):
        raise ValueError("Invalid source commit or workflow run ID")
    match = PIN.search(build_script.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("Pinned pi-gen source commit not found")
    images = sorted(directory.glob("*.img.xz"))
    if len(images) != 1 or images[0].is_symlink() or not images[0].is_file():
        raise ValueError("Exactly one regular compressed image is required")
    image = images[0]
    if IMAGE.fullmatch(image.name) is None or image.stat().st_size == 0:
        raise ValueError("Unexpected or empty image name")
    with image.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    checksum = (directory / "SHA256SUMS.txt")
    if checksum.is_symlink() or not checksum.is_file():
        raise ValueError("Missing checksum file")
    if checksum.read_text(encoding="ascii").splitlines() != [
        digest + "  " + image.name
    ]:
        raise ValueError("Image digest does not match checksum file")
    metadata = {
        "schema": "rivanox-audiohub-preview-bundle/1",
        "image": image.name,
        "image_bytes": image.stat().st_size,
        "image_sha256": digest,
        "source_commit_sha": source_sha,
        "pi_gen_commit_sha": match.group(1),
        "github_actions_run_id": run_id,
        "hardware_verified": False,
        "release_approved": False,
        "supports_phone_wifi_setup": False,
        "scope": "Temporary development artifact only; isolated Pi4 test, not a release",
    }
    target = directory / "PREVIEW-MANIFEST.json"
    if target.exists() or target.is_symlink():
        raise ValueError("Preview manifest already exists; do not overwrite")
    target.write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--build-script", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = manifest(
            args.directory, args.source_sha, args.run_id, args.build_script
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, "Unverified image manifest rejected: " + str(exc) + "\n")
    print("Manifest verified for " + result["image"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
