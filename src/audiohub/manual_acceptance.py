# SPDX-License-Identifier: AGPL-3.0-only
"""Interactive OFFLINE hardware observation checklist, not a product signoff.

Run on the Pi's local user console after connecting the real USB Edifier.
It never plays audio, pairs devices, writes files, or opens a network socket.
The operator's free text is NOT retained; output has no identifiers.
"""
from __future__ import annotations

import json

from .hardware_preflight import probe

SCHEMA = "rivanox-audiohub-manual-hardware-observation/1"
GATES = (
    ("speaker_audible", "Did you personally hear audio from Edifier USB speakers?"),
    ("three_simultaneous_sources", "Did all three independent inputs play together?"),
    ("per_channel_isolation", "Did per-input mute/EQ affect only the selected input?"),
    ("usb_unplug_failsafe", "Did removing USB audio stop all active sound routes?"),
    ("mix_clipping", "Did the mixed output avoid obvious clipping at test volume?"),
    ("endurance_24h", "Did a separate uninterrupted 24-hour endurance test pass?"),
)
CHOICES = {"y": "observed", "yes": "observed",
           "n": "failed", "no": "failed",
           "s": "not_tested", "skip": "not_tested", "": "not_tested"}
MAX_INPUT_ATTEMPTS = 3


def _answer(prompt, message):
    """Accept only fixed yes/no/skip tokens; never copy arbitrary input."""
    for _ in range(MAX_INPUT_ATTEMPTS):
        try:
            entered = prompt(message + " [yes/no/skip]: ")
        except (EOFError, KeyboardInterrupt):
            return "not_tested"
        if type(entered) is not str:
            return "not_tested"
        normalized = entered.strip().lower()
        if normalized in CHOICES:
            return CHOICES[normalized]
    return "not_tested"


def _consistent_read_only_preflight(report):
    """Only a complete, internally consistent topology summary can prompt.

    A caller-provided ready flag alone is never evidence of USB or PipeWire
    readiness. Even a valid summary is NOT evidence of audible hardware.
    """
    if type(report) is not dict or type(report.get("schema_version")) is not int:
        return False
    checks = report.get("checks")
    if type(checks) is not dict:
        return False
    sinks = checks.get("virtual_sink_unique")
    gates = report.get("hardware_gates")
    if type(sinks) is not dict or type(gates) is not dict:
        return False
    return (
        report["schema_version"] == 1
        and report.get("assessment") == "topology_only_not_hardware_acceptance"
        and report.get("topology_preflight") == "ready_for_manual_test"
        and report.get("release_ready") is False
        and checks.get("pipewire_inspection_succeeded") is True
        and checks.get("edifier_usb_sink_unique") is True
        and set(sinks) == {"music", "laptop", "tablet"}
        and all(sinks[channel] is True for channel in ("music", "laptop", "tablet"))
        and all(gates.get(gate) == "unverified" for gate in (
            "speaker_audible", "three_simultaneous_sources",
            "per_channel_isolation", "mix_clipping",
            "wifi_owner_security", "endurance_24h",
        ))
    )


def observe(preflight, *, ask=input):
    """No automatic audio assertion is possible from PipeWire metadata."""
    ready = _consistent_read_only_preflight(preflight)
    observations = {
        gate: _answer(ask, question) if ready else "not_tested"
        for gate, question in GATES
    }
    return {
        "schema": SCHEMA,
        "classification": "UNVERIFIED_ALPHA_OPERATOR_OBSERVATION_ONLY",
        "preflight": "ready_for_manual_test" if ready else "incomplete",
        "operator_observations": observations,
        "all_questions_answered_observed": all(
            value == "observed" for value in observations.values()
        ) if ready else False,
        "hardware_accepted": False,
        "ownership_authenticated": False,
        "wifi_owner_security": "unverified",
        "legal_redistribution_approved": False,
        "model_c_license_effective": False,
        "release_ready": False,
        "persisted": False,
    }


def main(*, check=probe, ask=input, output=print):
    try:
        topology = check()
    except (OSError, ValueError, TypeError):
        topology = {}
    result = observe(topology, ask=ask)
    output(json.dumps(result, sort_keys=True, separators=(",", ":")))
    # Code 0 means an operator report was produced, NOT hardware acceptance.
    # A nonzero code indicates the PipeWire prerequisites were not present.
    return 0 if result["preflight"] == "ready_for_manual_test" else 2


if __name__ == "__main__":
    raise SystemExit(main())
