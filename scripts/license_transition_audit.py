#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed review-only guard for the prospective Model C transition.

Never interpret a future commercial policy draft as effective rights or
as authorizing commercial enforcement against existing AGPL copies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

STATE = "docs/licensing/TRANSITION-STATE.json"
CURRENT = "AGPL-3.0-only"
TARGET = "LicenseRef-RIVANOX-Community-1.0"
SCHEMA = "rivanox-audiohub-license-transition/1"
REQUIRED_FALSE = (
    "rights_holder_identified_and_verified",
    "rights_chain_verified",
    "third_party_license_clearance",
    "legal_counsel_approved",
    "owner_approved_effective_switch",
    "hardware_and_release_approved",
    "license_switch_effective",
    "public_release_authorized",
)
EXPECTED_KEYS = {
    "schema", "decision_date", "project", "decision", "stage",
    "current_effective_source_license", "proposed_future_source_license",
    "proposed_document", "current_license_path",
    "historical_agpl_rights_preserved", "effective_release_tag",
    *REQUIRED_FALSE,
}


def inspect(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source checkout missing or symlinked")
    state_file = root / STATE
    if state_file.is_symlink() or not state_file.is_file():
        raise ValueError("Transition state unavailable")
    if not 0 < state_file.stat().st_size <= 8192:
        raise ValueError("Transition state unexpectedly large")
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid licensing transition state") from exc
    if type(state) is not dict or set(state) != EXPECTED_KEYS:
        raise ValueError("License transition state has unexpected keys")
    if (state["schema"] != SCHEMA
            or state["current_effective_source_license"] != CURRENT
            or state["proposed_future_source_license"] != TARGET
            or state["stage"] != "draft_legal_review"
            or state["decision"] != "model-c-source-available-free-private-commercial-permission-required"
            or state["decision_date"] != "2026-11-05"
            or state["project"] != "PJ2611-0001:R001"
            or state["proposed_document"] != "LICENSE-C-DRAFT.md"
            or state["current_license_path"] != "LICENSE"
            or state["effective_release_tag"] is not None
            or state["historical_agpl_rights_preserved"] is not True):
        raise ValueError("Inconsistent historical license or future draft status")
    if any(state[k] is not False for k in REQUIRED_FALSE):
        raise ValueError("Model C approval falsely recorded or license switch attempted")
    existing = root / "LICENSE"
    proposal = root / "LICENSE-C-DRAFT.md"
    readme = root / "README.md"
    policy = root / "docs/COMMERCIAL-LICENSING.md"
    source_checks = root / ".github/workflows/source-checks.yml"
    publisher = root / ".github/workflows/publish-image.yml"
    for filename in (existing, proposal, readme, policy, source_checks, publisher):
        if filename.is_symlink() or not filename.is_file():
            raise ValueError("Licensing document or safety workflow missing")
    license_text = existing.read_text(encoding="utf-8")
    if not license_text.startswith("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007"):
        raise ValueError("Existing AGPL LICENSE unexpectedly replaced")
    if not 33000 <= len(license_text) <= 35000:
        raise ValueError("Existing AGPL LICENSE unexpectedly altered")
    draft = proposal.read_text(encoding="utf-8")
    required_proposal = (
        "NOT EFFECTIVE", "legal",
        "non-commercial", "prior written", "AGPL", "third-party",
        "not", "commercial", "private", "human",
    )
    if not all(x.lower() in draft.lower() for x in required_proposal):
        raise ValueError("Model C proposal missing essential consumer or historical safeguards")
    if ("model c" not in readme.read_text(encoding="utf-8").lower()
            or "AGPL-3.0-only" not in policy.read_text(encoding="utf-8")
            or "NOT EFFECTIVE" not in policy.read_text(encoding="utf-8")):
        raise ValueError("User-facing licensing transition disclosures missing")
    if "scripts/license_transition_audit.py" not in source_checks.read_text(encoding="utf-8"):
        raise ValueError("GitHub source CI does not enforce licensing review state")
    publish = publisher.read_text(encoding="utf-8")
    if "exit 1" not in publish or "contents: write" in publish:
        raise ValueError("Public image release was enabled before approval")
    return {
        "schema": SCHEMA,
        "current_effective_license": CURRENT,
        "planned_license": TARGET,
        "model_c_business_direction": "accepted",
        "legal_review_complete": False,
        "commercial_license_active": False,
        "public_release_authorized": False,
        "historical_agpl_preserved": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        report = inspect(args.root)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, "Model C licensing review REFUSED: " + str(exc) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
