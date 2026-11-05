#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed per-file source provenance ledger gate, NOT legal clearance.

Checks every checked-in source/build/test file has a pending rights review.
This does not detect copied third-party code and it cannot prove ownership
of AI-assisted output or the legality of a future proprietary relicense.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCHEMA = "rivanox-audiohub-source-rights-ledger/1"
LEDGER = Path("docs/licensing/SOURCE-RIGHTS-LEDGER.json")
SOURCE_ROOTS = ("src", "web", "image", "scripts", "tests", ".github/workflows")
EXTRA_FILES = ("build-image.sh",)
REQUIRED_FALSE = (
    "rights_holder_confirmed",
    "human_authorship_and_assignments_checked",
    "third_party_similarity_review_completed",
    "all_sources_eligible_for_model_c",
    "commercial_relicense_approved",
)
FILE_KEYS = {"path", "origin_status", "rightsholder_verified",
             "third_party_origin_checked", "model_c_eligible"}


def _safe_file(root: Path, rel: str):
    path = Path(rel)
    if (path.is_absolute() or ".." in path.parts or not path.parts
            or str(path) != rel):
        raise ValueError("Ledger file path unsafe")
    candidate = root
    for piece in path.parts:
        candidate = candidate / piece
        if candidate.is_symlink():
            raise ValueError("Source tree symlink not allowed")
    if not candidate.is_file():
        raise ValueError("Source path missing: " + rel)
    return candidate


def source_paths(root: Path) -> list[str]:
    found = []
    for folder in SOURCE_ROOTS:
        base = root / folder
        if base.is_symlink() or not base.is_dir():
            raise ValueError("Source directory missing or linked: " + folder)
        for path in base.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError("Source tree symlink not allowed")
            if path.is_file():
                found.append(rel)
    for rel in EXTRA_FILES:
        _safe_file(root, rel)
        found.append(rel)
    return sorted(found)


def audit(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid source root")
    path = _safe_file(root, LEDGER.as_posix())
    if not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError("Invalid source rights ledger size")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if (type(doc) is not dict
            or set(doc) != {"schema", "effective_legacy_license",
                           "future_licensing_intent", "review_flags", "files"}
            or doc["schema"] != SCHEMA
            or doc["effective_legacy_license"] != "AGPL-3.0-only"
            or doc["future_licensing_intent"] != "Model C: noncommercial personal free, commercial separately licensed, NOT EFFECTIVE"):
        raise ValueError("Source rights ledger format or license policy invalid")
    flags = doc["review_flags"]
    if (type(flags) is not dict or set(flags) != set(REQUIRED_FALSE)
            or any(flags[k] is not False for k in REQUIRED_FALSE)):
        raise ValueError("Unverified owner and third-party legal approvals MUST remain false")
    entries = doc["files"]
    if type(entries) is not list:
        raise ValueError("Source rights file inventory missing")
    paths = []
    for entry in entries:
        if (type(entry) is not dict or set(entry) != FILE_KEYS
                or type(entry["path"]) is not str
                or entry["origin_status"] != "pending-human-review"
                or entry["rightsholder_verified"] is not False
                or entry["third_party_origin_checked"] is not False
                or entry["model_c_eligible"] is not False):
            raise ValueError("Unapproved source rights assertion or malformed entry")
        paths.append(entry["path"])
    expected = source_paths(root)
    if paths != expected:
        missing = sorted(set(expected) - set(paths))
        extra = sorted(set(paths) - set(expected))
        raise ValueError(
            "Source rights ledger does not cover exact source tree "
            f"(missing={missing[:6]}, extra={extra[:6]})"
        )
    license_file = _safe_file(root, "LICENSE")
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in license_file.read_text(encoding="utf-8"):
        raise ValueError("Historical AGPL license unexpectedly missing")
    return {
        "schema": SCHEMA,
        "files_covered": len(paths),
        "all_source_ownership_approved": False,
        "all_third_party_code_cleared": False,
        "model_c_license_effective": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        result = audit(args.root)
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        parser.exit(2, "Source-rights review REFUSED: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
