#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Export a verified rootfs package inventory into pi-gen's preview deploy dir.

This fixes the ARM64 build's missing ROOTFS-PACKAGES.json stage->deploy copy.
It is intentionally preview-only; it never publishes images, claims
third-party legal clearance or modifies a source LICENSE.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_package_inventory import verify
from scripts.rootfs_copyright_triage import analyze


FILENAME = "ROOTFS-PACKAGES.json"
RELATIVE = Path("usr/share/doc/audiohub") / FILENAME
STAGE = "stage-audiohub"


def _not_symlinked_path(path: Path, stop: Path):
    """Reject symlinks within the generated worktree, including the file."""
    cursor = path
    while True:
        if cursor.is_symlink():
            raise ValueError("Refusing symlink inside generated worktree")
        if cursor == stop:
            return
        if stop not in cursor.parents:
            raise ValueError("Path escapes pi-gen worktree")
        cursor = cursor.parent


def export(pi_gen_root: Path) -> dict:
    pi_gen_root = Path(pi_gen_root)
    work = pi_gen_root / "work"
    deploy = pi_gen_root / "deploy"
    if (pi_gen_root.is_symlink() or work.is_symlink()
            or deploy.is_symlink() or not work.is_dir()
            or not deploy.is_dir()):
        raise ValueError("Untrusted or missing pi-gen work/deploy directories")

    # pi-gen stores each generated stage rootfs in work/<build-id>/<stage>/rootfs.
    # Selecting by this narrow path prevents picking a stale intermediate
    # stage2 rootfs or unrelated host copy with matching filename.
    candidates = sorted(work.glob(f"*/{STAGE}/rootfs/{RELATIVE.as_posix()}"))
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one completed {STAGE} rootfs inventory; "
            f"found {len(candidates)}"
        )
    source = candidates[0]
    _not_symlinked_path(source, work)
    if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError("Rootfs inventory not a regular file")
    proof = verify(source)

    target = deploy / FILENAME
    if target.exists() or target.is_symlink():
        raise ValueError("Refusing to overwrite an existing preview inventory")

    # No temporary file left on success; atomic creation + content sync.
    # Called from the root-owned pi-gen post-build step before staging.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(target, flags, 0o644)
    try:
        payload = source.read_bytes()
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if verify(target) != proof:
            raise ValueError("Exported package inventory verification mismatch")
    except BaseException:
        if fd != -1:
            os.close(fd)
        target.unlink(missing_ok=True)
        raise

    document = json.loads(payload)
    missing = [pkg["name"] for pkg in document["packages"]
               if pkg["copyright_sha256"] is None]
    return {
        "schema": "rivanox-audiohub-rootfs-export-proof/1",
        "inventory_file": FILENAME,
        "inventory_sha256": proof["package_inventory_sha256"],
        "installed_packages": proof["installed_packages"],
        "copyright_files_missing": proof["copyright_files_missing"],
        "unresolved_copyright_packages": missing,
        "third_party_license_review_approved": False,
        "public_release_approved": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-gen-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = export(args.pi_gen_root)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, "Rootfs inventory export REFUSED: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
