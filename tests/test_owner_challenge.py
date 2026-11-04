"""Real Ed25519 signature checks for offline owner challenge; no web service."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.owner_record_store import OwnerRecordStore, RECORD_NAME
from audiohub.owner_challenge import (
    OwnerPossessionChallenge, ProofDenied, DOMAIN, CHALLENGE_TTL_SECONDS,
    MAX_PROOF_FAILURES,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Nonces:
    def __init__(self):
        self.index = 0

    def __call__(self, length):
        self.index += 1
        return self.index.to_bytes(length, "big")


class OwnerChallengeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        folder = self.root / "protected"
        folder.mkdir(mode=0o700)
        self.store = OwnerRecordStore(folder)
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.clock = Clock()
        self.nonces = Nonces()
        self.challenge = OwnerPossessionChallenge(
            self.store, clock=self.clock, random_bytes=self.nonces,
        )

    def enroll(self):
        self.store.seal(
            self.public, trusted_physical_approval=True,
            trusted_factory_unowned=True,
        )

    def sign(self, message):
        return self.private.sign(message)

    def test_missing_record_never_issues_a_challenge(self):
        with self.assertRaises(ProofDenied):
            self.challenge.begin(self.public)
        self.assertFalse(self.challenge.verify(self.public, bytes(64)))
        self.assertFalse(self.challenge.public_status()["owner_authenticated"])

    def test_real_ed25519_signature_bound_to_stored_key(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        self.assertTrue(message.startswith(DOMAIN))
        self.assertEqual(
            message[len(DOMAIN):len(DOMAIN) + 32], hashlib.sha256(self.public).digest()
        )
        self.assertEqual(len(message), len(DOMAIN) + 64)
        self.assertTrue(self.challenge.verify(self.public, self.sign(message)))
        self.assertFalse(self.challenge.public_status()["owner_authenticated"])
        self.assertFalse(self.challenge.public_status()["network_onboarding_enabled"])

    def test_signature_is_one_use_and_cannot_be_replayed(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        signature = self.sign(message)
        self.assertTrue(self.challenge.verify(self.public, signature))
        self.assertFalse(self.challenge.verify(self.public, signature))
        self.assertFalse(self.challenge.public_status()["proof_window_open"])
        other_message = self.challenge.begin(self.public)
        self.assertNotEqual(other_message, message)
        self.assertFalse(self.challenge.verify(self.public, signature))
        self.assertTrue(self.challenge.verify(self.public, self.sign(other_message)))

    def test_wrong_key_and_signatures_cannot_authenticate(self):
        self.enroll()
        second = Ed25519PrivateKey.generate()
        wrong_key = second.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        with self.assertRaises(ProofDenied):
            self.challenge.begin(wrong_key)
        message = self.challenge.begin(self.public)
        self.assertFalse(self.challenge.verify(wrong_key, second.sign(message)))
        self.assertFalse(self.challenge.verify(self.public, second.sign(message)))
        self.assertTrue(self.challenge.verify(self.public, self.sign(message)))

    def test_wrong_domain_message_is_rejected(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        self.assertFalse(self.challenge.verify(self.public,
                                                self.sign(b"OTHER-DOMAIN\x00" + message)))
        self.assertTrue(self.challenge.verify(self.public, self.sign(message)))

    def test_challenge_expires_exactly_at_timeout(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        self.clock.now += CHALLENGE_TTL_SECONDS
        self.assertFalse(self.challenge.verify(self.public, self.sign(message)))
        new_message = self.challenge.begin(self.public)
        self.assertNotEqual(new_message, message)
        self.assertTrue(self.challenge.verify(self.public, self.sign(new_message)))

    def test_five_failed_signatures_close_window(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        for _ in range(MAX_PROOF_FAILURES):
            self.assertFalse(self.challenge.verify(self.public, bytes(64)))
        self.assertFalse(self.challenge.public_status()["proof_window_open"])
        self.assertFalse(self.challenge.verify(self.public, self.sign(message)))

    def test_malformed_signature_and_public_key_denied(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        for key, sig in (
            (None, bytes(64)), ("fake", bytes(64)),
            (self.public, None), (self.public, "a" * 64),
            (self.public, b"x"), (self.public, b"x" * 65)
        ):
            self.assertFalse(self.challenge.verify(key, sig))
        self.assertFalse(self.challenge.verify(self.public, self.sign(message)))

    def test_record_tampering_after_issue_denies_signature(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        path = self.root / "protected" / RECORD_NAME
        path.write_text('{"invalid":"owner"}')
        path.chmod(0o600)
        self.assertFalse(self.challenge.verify(self.public, self.sign(message)))

    def test_missing_crypto_backend_fails_closed(self):
        self.enroll()
        message = self.challenge.begin(self.public)
        with mock.patch("audiohub.owner_challenge._verify_ed25519",
                        side_effect=ImportError("crypto unavailable")):
            self.assertFalse(self.challenge.verify(self.public, self.sign(message)))
        self.assertFalse(self.challenge.public_status()["owner_authenticated"])

    def test_wrong_entropy_size_or_type_never_opens_window(self):
        self.enroll()
        for entropy in (lambda length: b"x",
                        lambda length: "a" * length,
                        lambda length: None):
            gate = OwnerPossessionChallenge(
                self.store, clock=self.clock, random_bytes=entropy
            )
            with self.assertRaises(ProofDenied):
                gate.begin(self.public)
            self.assertFalse(gate.public_status()["proof_window_open"])

    def test_repeated_entropy_does_not_reissue_same_challenge(self):
        self.enroll()
        gate = OwnerPossessionChallenge(
            self.store, clock=self.clock, random_bytes=lambda length: b"q" * length
        )
        first = gate.begin(self.public)
        self.clock.now += CHALLENGE_TTL_SECONDS
        with self.assertRaises(ProofDenied):
            gate.begin(self.public)
        self.assertFalse(gate.public_status()["proof_window_open"])
        self.assertFalse(gate.verify(self.public, self.sign(first)))

    def test_concurrent_begin_denies_second_pending_challenge(self):
        self.enroll()
        results = []
        start = threading.Barrier(5)
        def worker():
            start.wait()
            try:
                results.append(self.challenge.begin(self.public))
            except ProofDenied:
                results.append(None)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        start.wait()
        for t in threads:
            t.join()
        self.assertEqual(sum(value is not None for value in results), 1)

    def test_existing_pending_challenge_cannot_be_extended(self):
        self.enroll()
        old = self.challenge.begin(self.public)
        self.clock.now += CHALLENGE_TTL_SECONDS - 1
        with self.assertRaises(ProofDenied):
            self.challenge.begin(self.public)
        self.clock.now += 1
        self.assertFalse(self.challenge.verify(self.public, self.sign(old)))

    def test_corrupt_permissions_block_key_match_and_verification(self):
        self.enroll()
        self.assertTrue(self.store.matches_public_key(self.public))
        self.assertFalse(self.store.matches_public_key(b"a" * 32))
        path = self.root / "protected" / RECORD_NAME
        path.chmod(0o644)
        self.assertFalse(self.store.matches_public_key(self.public))
        with self.assertRaises(ProofDenied):
            self.challenge.begin(self.public)

    def test_public_key_match_rejects_bad_values_and_invalid_directory(self):
        self.enroll()
        for item in (None, bytearray(self.public), self.public.hex(),
                     b"short", b"x" * 33):
            self.assertFalse(self.store.matches_public_key(item))
        folder = self.root / "protected"
        folder.chmod(0o755)
        self.assertFalse(self.store.matches_public_key(self.public))

    def test_status_contains_no_public_key_or_challenge(self):
        self.enroll()
        challenge = self.challenge.begin(self.public)
        public_status = json.dumps(self.challenge.public_status())
        self.assertNotIn(self.public.hex(), public_status)
        self.assertNotIn(challenge.hex(), public_status)
        self.assertFalse(self.challenge.public_status()["release_ready"])

    def test_code_is_not_wired_to_image_or_web_runtime(self):
        source = (ROOT / "src/audiohub/owner_challenge.py").read_text()
        for forbidden in ("ThreadingHTTPServer", "dbus.SystemBus", "nmcli",
                          "subprocess.run", "socket.socket", "shell=True"):
            self.assertNotIn(forbidden, source)
        for path in ("src/audiohub/webserver.py",
                     "image/stage-audiohub/01-install/00-run.sh",
                     "image/stage-audiohub/01-install/files/systemd/audiohub-status-web.service"):
            self.assertNotIn("owner_challenge", (ROOT / path).read_text())


if __name__ == "__main__":
    unittest.main()
