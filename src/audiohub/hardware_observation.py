# SPDX-License-Identifier: AGPL-3.0-only
"""Offline, privacy-minimal operator observations for isolated Pi4 speaker tests.

This module DOES NOT assess a microphone, physical sound, driver or product.
It can save what a human explicitly reports after a manual lab test. Never
put addresses, filenames, fingerprints, keys or workstation IDs in reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat

REPORT_SCHEMA = "rivanox-audiohub-manual-speaker-observation/1"
REPORT_TYPE = "UNVERIFIED_HUMAN_OBSERVATION"
OBSERVATIONS = (
    "not_checked",
    "heard_expected",
    "heard_opposite",
    "silent",
    "distorted",
    "uncertain",
)
OUTCOMES = ("completed", "stopped", "connection_failed")
CHANNELS = ("both", "left", "right", "sequence")
MAX_FRAMES = 360000
MAX_REPORT_BYTES = 4096


def package_source_sha(package_root=None):
    """Best-effort provenance only from the extracted portable source manifest.

    A local manifest is not a digital signature and does not prove origin.
    Missing, linked, oversized or malformed files are treated as unverified.
    """
    root = (Path(package_root) if package_root is not None
            else Path(__file__).resolve().parents[1])
    manifest = root / "SOURCE-MANIFEST.json"
    try:
        if manifest.is_symlink() or not manifest.is_file():
            return None
        if manifest.stat().st_size > 128 * 1024:
            return None
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        sha = payload.get("source_sha")
        if (payload.get("classification") == "UNVERIFIED_ALPHA_TEST_ONLY"
                and isinstance(sha, str)
                and re.fullmatch(r"[0-9a-f]{40}", sha)):
            return sha
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
    return None


def build_observation(*, channel, outcome, frames, left, right,
                      listened, source_sha=None, recorded_utc=None):
    """Build a strict, compact statement. Never set a hardware pass/GO bit."""
    if channel not in CHANNELS or not isinstance(channel, str):
        raise ValueError("Unsupported speaker test channel")
    if outcome not in OUTCOMES or not isinstance(outcome, str):
        raise ValueError("Unsupported test session outcome")
    if any(not isinstance(v, str) or v not in OBSERVATIONS for v in (left, right)):
        raise ValueError("Select an explicit observation for each speaker")
    if not isinstance(listened, bool):
        raise ValueError("Physical listening confirmation must be explicit")
    if not listened and (left != "not_checked" or right != "not_checked"):
        raise ValueError("Do not report heard sound without listening")
    if isinstance(frames, bool) or not isinstance(frames, int) or not 0 <= frames <= MAX_FRAMES:
        raise ValueError("Invalid local PCM frame count")
    if source_sha is not None and (
        not isinstance(source_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", source_sha)
    ):
        raise ValueError("Invalid source version")
    if recorded_utc is None:
        recorded_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    elif not isinstance(recorded_utc, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", recorded_utc
    ):
        raise ValueError("Invalid UTC timestamp")
    return {
        "schema": REPORT_SCHEMA,
        "classification": REPORT_TYPE,
        "recorded_utc": recorded_utc,
        "source_commit_from_local_manifest_unverified": source_sha,
        "scenario": "isolated_windows_pi4_edifier_low_volume_manual_stereo_check",
        "test_channel": channel,
        "session_outcome": outcome,
        "client_pcm_frames_sent_not_sound_proof": frames,
        "operator_physically_listened": listened,
        "left_speaker_observation": left,
        "right_speaker_observation": right,
        "hardware_verified": False,
        "release_ready": False,
        "review_required": True,
        "contains_credentials_or_device_identifiers": False,
    }


def save_observation(path, report):
    """Create a new offline JSON file; never overwrite an existing file.

    No upload, network action, automatic evidence submission or personal data.
    The operator chooses the destination. POSIX creates mode 0600; Windows
    ACL enforcement remains the local Windows account/operator responsibility.
    """
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        raise ValueError("Unrecognised manual report")
    if report.get("hardware_verified") is not False or report.get("release_ready") is not False:
        raise ValueError("Hardware/release claims are never accepted")
    if set(report) != set(build_observation(
        channel="both", outcome="connection_failed", frames=0,
        left="not_checked", right="not_checked", listened=False,
        source_sha=None, recorded_utc="2026-01-01T00:00:00+00:00",
    )):
        raise ValueError("Unexpected report fields")
    # Revalidate every field so callers cannot inject local addresses,
    # paths, keys or free text into an exported JSON by modifying a dict.
    check = build_observation(
        channel=report["test_channel"], outcome=report["session_outcome"],
        frames=report["client_pcm_frames_sent_not_sound_proof"],
        left=report["left_speaker_observation"],
        right=report["right_speaker_observation"],
        listened=report["operator_physically_listened"],
        source_sha=report["source_commit_from_local_manifest_unverified"],
        recorded_utc=report["recorded_utc"],
    )
    if check != report:
        raise ValueError("Unexpected manual report metadata")
    payload = (json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2)
               + "\n").encode("ascii")
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("Manual report exceeds limit")
    p = Path(path)
    if p.is_symlink():
        raise ValueError("Linked export destination forbidden")
    flags = (os.O_CREAT | os.O_EXCL | os.O_WRONLY
             | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(p, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            fd = None
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
    finally:
        if fd is not None:
            os.close(fd)
    # Return a simple fact only: GUI should not expose or log the local path.
    return len(payload)
