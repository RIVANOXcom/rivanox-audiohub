# SPDX-License-Identifier: AGPL-3.0-only
"""Offline Ed25519 owner-key possession challenge, NOT a deployed login.

A separate trusted physical/OOB enrollment flow MUST establish the key
fingerprint in a protected OwnerRecordStore before this can succeed.
No network, session issuance, service or pairing integration is present.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

DOMAIN = b"RIVANOX-AUDIOHUB-OWNER-POSSESSION-V1\x00"
NONCE_BYTES = 32
CHALLENGE_TTL_SECONDS = 60
MAX_PROOF_FAILURES = 5


class ProofDenied(Exception):
    """Generic denial. Never reveal a registered key or secret nonce."""


def _verify_ed25519(public_key, signature, message):
    """Use a maintained crypto library. Never implement signature math here."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True


class OwnerPossessionChallenge:
    """Exactly one outstanding bound challenge per in-memory verifier instance.

    This primitive deliberately returns only True/False for a proof. It does
    NOT issue an authenticated web session or authorize configuration writes.
    """

    def __init__(self, store, *, clock=None, random_bytes=None):
        self._store = store
        self._clock = time.monotonic if clock is None else clock
        self._random_bytes = secrets.token_bytes if random_bytes is None else random_bytes
        self._lock = threading.Lock()
        self._pending = None

    @staticmethod
    def _fingerprint(public_key):
        if type(public_key) is not bytes or len(public_key) != 32:
            return None
        return hashlib.sha256(public_key).digest()

    def begin(self, public_key):
        """Issue an ephemeral domain-separated challenge only for stored key.

        A trusted caller MUST enforce transport/rate limits and must not expose
        whether a key fingerprint was registered in public HTTP responses.
        """
        with self._lock:
            now = self._clock()
            if self._pending is not None and now < self._pending[2]:
                raise ProofDenied("Proof not permitted")
            # After an expired challenge, do not allow replay of a stale
            # nonce; clear state before any new potentially failing operation.
            self._pending = None
            digest = self._fingerprint(public_key)
            if digest is None or not self._store.matches_public_key(public_key):
                raise ProofDenied("Proof not permitted")
            nonce = self._random_bytes(NONCE_BYTES)
            if type(nonce) is not bytes or len(nonce) != NONCE_BYTES:
                raise ProofDenied("Proof not permitted")
            message = DOMAIN + digest + nonce
            self._pending = (digest, message, now + CHALLENGE_TTL_SECONDS,
                             MAX_PROOF_FAILURES)
            return message

    def verify(self, public_key, signature):
        """Consume the challenge on success; return no session or network grant."""
        with self._lock:
            pending = self._pending
            if pending is None:
                return False
            digest, message, expires, remaining = pending
            if self._clock() >= expires or remaining <= 0:
                self._pending = None
                return False
            received = self._fingerprint(public_key)
            if (received is None or not hmac.compare_digest(received, digest)
                    or type(signature) is not bytes or len(signature) != 64
                    or not self._store.matches_public_key(public_key)):
                self._reject_attempt(digest, message, expires, remaining)
                return False
            try:
                verified = _verify_ed25519(public_key, signature, message)
            except (ImportError, OSError, RuntimeError):
                # Missing crypto backend must never produce success.
                verified = False
            if not verified:
                self._reject_attempt(digest, message, expires, remaining)
                return False
            self._pending = None
            return True

    def _reject_attempt(self, digest, message, expires, remaining):
        if remaining <= 1:
            self._pending = None
        else:
            self._pending = (digest, message, expires, remaining - 1)

    def public_status(self):
        """No challenge, public key or key fingerprint is included."""
        with self._lock:
            return {
                "proof_window_open": bool(
                    self._pending is not None and self._clock() < self._pending[2]
                    and self._pending[3] > 0
                ),
                "owner_authenticated": False,
                "network_onboarding_enabled": False,
                "release_ready": False,
            }
