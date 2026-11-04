"""Source-only security regression tests for the offline owner claim policy.

These mocks do NOT attest any physical button, owner identity, device secret
storage, or authenticated phone network setup.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.owner_claim_policy import (
    ClaimDenied, OwnerClaimPolicy, CLAIM_TTL_SECONDS, MAX_ATTEMPTS,
    SESSION_TTL_SECONDS,
)


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class Entropy:
    def __init__(self):
        self.next_value = 1

    def __call__(self, size):
        value = self.next_value
        self.next_value += 1
        return bytes([value]) * size


class OwnerClaimTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.entropy = Entropy()
        self.gate = OwnerClaimPolicy(
            trusted_factory_unowned=True, clock=self.clock,
            random_bytes=self.entropy,
        )

    def test_factory_state_unknown_denies_all_claims(self):
        gate = OwnerClaimPolicy(clock=self.clock, random_bytes=self.entropy)
        with self.assertRaises(ClaimDenied):
            gate.arm_physical(trusted_physical_event=True)
        with self.assertRaises(ClaimDenied):
            gate.claim("0" * 64)
        self.assertFalse(gate.authorize_session("0" * 64))
        self.assertFalse(gate.status()["durable_owner_verified"])

    def test_explicit_physical_event_required(self):
        for flag in (None, False, 0, 1, "true", object()):
            with self.subTest(flag=str(flag)[:16]), self.assertRaises(ClaimDenied):
                self.gate.arm_physical(trusted_physical_event=flag)
        self.assertFalse(self.gate.status()["claim_window_open"])

    def test_claim_issues_one_time_proof_and_short_session(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        self.assertEqual(len(proof), 64)
        self.assertTrue(self.gate.status()["claim_window_open"])
        session = self.gate.claim(proof)
        self.assertNotEqual(session, proof)
        self.assertEqual(len(session), 64)
        self.assertFalse(self.gate.authorize_session(proof))
        self.assertTrue(self.gate.authorize_session(session))
        self.assertFalse(self.gate.status()["durable_owner_verified"])
        self.assertFalse(self.gate.status()["network_onboarding_enabled"])

    def test_replay_and_rearm_after_claim_rejected(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        self.gate.claim(proof)
        with self.assertRaises(ClaimDenied):
            self.gate.claim(proof)
        with self.assertRaises(ClaimDenied):
            self.gate.arm_physical(trusted_physical_event=True)

    def test_claim_requires_new_physical_event_after_expiry(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        self.clock.value += CLAIM_TTL_SECONDS
        with self.assertRaises(ClaimDenied):
            self.gate.claim(proof)
        self.assertFalse(self.gate.status()["claim_window_open"])
        with self.assertRaises(ClaimDenied):
            self.gate.claim(proof)
        new_proof = self.gate.arm_physical(trusted_physical_event=True)
        self.assertNotEqual(proof, new_proof)
        self.assertTrue(self.gate.status()["claim_window_open"])

    def test_exactly_five_bad_attempts_close_window(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        for _ in range(MAX_ATTEMPTS):
            with self.assertRaisesRegex(ClaimDenied, "not permitted"):
                self.gate.claim("a" * 64)
        self.assertFalse(self.gate.status()["claim_window_open"])
        with self.assertRaises(ClaimDenied):
            self.gate.claim(proof)
        self.assertFalse(self.gate.status()["volatile_claim_completed"])

    def test_malformed_codes_count_as_denied_attempts(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        for bad in (None, b"0" * 64, "f", "F" * 64, "z" * 64):
            with self.subTest(bad=str(bad)[:15]), self.assertRaises(ClaimDenied):
                self.gate.claim(bad)
        with self.assertRaises(ClaimDenied):
            self.gate.claim(proof)

    def test_new_attempt_cannot_extend_existing_claim_window(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        self.clock.value += CLAIM_TTL_SECONDS - 1
        with self.assertRaisesRegex(ClaimDenied, "pending"):
            self.gate.arm_physical(trusted_physical_event=True)
        self.clock.value += 2
        with self.assertRaises(ClaimDenied):
            self.gate.claim(proof)

    def test_session_expiration_and_revocation(self):
        token = self.gate.claim(self.gate.arm_physical(trusted_physical_event=True))
        self.clock.value += SESSION_TTL_SECONDS - 1
        self.assertTrue(self.gate.authorize_session(token))
        self.clock.value += 1
        self.assertFalse(self.gate.authorize_session(token))
        self.assertFalse(self.gate.status()["session_active"])
        self.gate.revoke_session()
        self.assertFalse(self.gate.authorize_session(token))
        with self.assertRaises(ClaimDenied):
            self.gate.arm_physical(trusted_physical_event=True)

    def test_wrong_session_or_malformed_secret_never_authorizes(self):
        token = self.gate.claim(self.gate.arm_physical(trusted_physical_event=True))
        for candidate in (None, True, "A" * 64, bytes.fromhex(token),
                          "f", "x" * 64, token[:-1] + "9"):
            with self.subTest(candidate=str(candidate)[:12]):
                self.assertFalse(self.gate.authorize_session(candidate))

    def test_public_status_has_no_secret_and_never_approves_release(self):
        proof = self.gate.arm_physical(trusted_physical_event=True)
        status = self.gate.status()
        rendered = json.dumps(status)
        self.assertNotIn(proof, rendered)
        self.assertFalse(status["durable_owner_verified"])
        self.assertFalse(status["release_ready"])
        token = self.gate.claim(proof)
        self.assertNotIn(token, json.dumps(self.gate.status()))
        self.assertFalse(self.gate.status()["network_onboarding_enabled"])

    def test_bad_random_source_fails_closed_before_arming(self):
        broken = OwnerClaimPolicy(trusted_factory_unowned=True,
                                  clock=self.clock, random_bytes=lambda n: b"x")
        with self.assertRaises(RuntimeError):
            broken.arm_physical(trusted_physical_event=True)
        self.assertFalse(broken.status()["claim_window_open"])

    def test_bad_random_source_during_claim_does_not_issue_session(self):
        calls = [bytes([1]) * 32, b"x"]
        broken = OwnerClaimPolicy(trusted_factory_unowned=True,
                                  clock=self.clock, random_bytes=lambda n: calls.pop(0))
        proof = broken.arm_physical(trusted_physical_event=True)
        with self.assertRaises(RuntimeError):
            broken.claim(proof)
        self.assertFalse(broken.status()["volatile_claim_completed"])
        self.assertFalse(broken.authorize_session(proof))

    def test_repeating_entropy_cannot_reuse_claim_proof_as_session(self):
        repeated = OwnerClaimPolicy(
            trusted_factory_unowned=True, clock=self.clock,
            random_bytes=lambda n: b"r" * n,
        )
        proof = repeated.arm_physical(trusted_physical_event=True)
        with self.assertRaisesRegex(RuntimeError, "entropy"):
            repeated.claim(proof)
        self.assertFalse(repeated.status()["volatile_claim_completed"])
        self.assertFalse(repeated.authorize_session(proof))
        self.assertFalse(repeated.status()["network_onboarding_enabled"])

    def test_owner_model_is_not_wired_into_network_or_automatic_services(self):
        web = (ROOT / "src/audiohub/webserver.py").read_text()
        pairing = (ROOT / "src/audiohub/pairing.py").read_text()
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text()
        service = (ROOT / "image/stage-audiohub/01-install/files/systemd"
                   / "audiohub-status-web.service").read_text()
        for text in (web, pairing, installer, service):
            self.assertNotIn("owner_claim_policy", text)
            self.assertNotIn("arm_physical", text)
            self.assertNotIn("AUDIOHUB_UNSAFE_STATUS_LAN=YES", text)
        self.assertIn("NoNewPrivileges=yes", service)


if __name__ == "__main__":
    unittest.main()
