# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only staged PSK rotation preflight for an isolated AudioHub lab.

This does not rotate, provision, copy, back up, remove, or install any key.
Both independent comparison codes must come from the physically trusted Pi
console. No proof of Pi ownership, Windows ACL correctness, or hardware GO.
"""
from __future__ import annotations

import getpass
import hmac
from pathlib import Path

from . import key_onboarding

CLASSIFICATION = "OFFLINE_STAGING_CHECK_ONLY"


def inspect_staged_rotation(current_path, staged_path, current_pi_code,
                            staged_pi_code):
    """Check protected local old/new files against independent Pi codes.

    No sockets or writes. Success means *only* equality of the supplied
    secret-copy check codes at the moment of reading, not installation.
    """
    old_expected = key_onboarding.validate_check_code(current_pi_code)
    new_expected = key_onboarding.validate_check_code(staged_pi_code)
    if hmac.compare_digest(old_expected, new_expected):
        raise ValueError("A new PSK must differ from the existing PSK")

    old_path = Path(current_path)
    new_path = Path(staged_path)
    if not old_path.is_absolute() or not new_path.is_absolute():
        raise ValueError("Both private PSK paths must be absolute")
    # Refuse exact same file, aliases and hard links. The underlying strict
    # local_key_code also rejects symlinks and inappropriate POSIX mode/owner.
    if old_path.samefile(new_path):
        raise ValueError("The staged and current PSKs must be distinct files")

    old_local = key_onboarding.local_key_code(old_path)
    new_local = key_onboarding.local_key_code(new_path)
    if hmac.compare_digest(old_local, new_local):
        raise ValueError("Staged key still contains the existing secret")
    if (not hmac.compare_digest(old_local, old_expected)
            or not hmac.compare_digest(new_local, new_expected)):
        raise ValueError("A local PSK copy does not match its trusted Pi code")

    # No paths, codes, secrets or device identifiers in the result. It is
    # deliberately NOT a go/no-go report for physical activation.
    return {
        "classification": CLASSIFICATION,
        "old_copy_matches_claimed_pi_code": True,
        "staged_copy_matches_claimed_pi_code": True,
        "old_and_staged_keys_distinct": True,
        "changes_applied": False,
        "network_tested": False,
        "device_owner_verified": False,
        "rotation_approved": False,
        "release_ready": False,
    }


def interactive_preflight(*, input_fn=input, secret_input_fn=None, output=print):
    """Console-only preview; use hidden prompts, not command-line secrets."""
    if secret_input_fn is None:
        secret_input_fn = getpass.getpass
    output("AudioHub private key rotation PREVIEW – OFFLINE, NO CHANGES.")
    output("Beforehand, operator must privately prepare both Pi key copies.")
    output("Never paste the raw 32-byte key or post the comparison codes.")
    current = input_fn("Absolute path of CURRENT Windows PSK: ").strip()
    staged = input_fn("Absolute path of STAGED Windows PSK: ").strip()
    current_pi = secret_input_fn("Private CURRENT code from trusted Pi console: ").strip()
    staged_pi = secret_input_fn("Private STAGED code from trusted Pi console: ").strip()
    inspect_staged_rotation(current, staged, current_pi, staged_pi)
    output("PASS: supplied Pi codes match distinct Windows old/staged copies.")
    output("NO keys changed, no Pi reached, no TLS/Edifier test, no authorization.")
    output("Keep old key recoverable; switch both ends manually only after approval.")
    output("After authorized switch, use the separately approved isolated soundcheck.")
    return 0


if __name__ == "__main__":
    raise SystemExit(interactive_preflight())
