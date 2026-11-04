# SPDX-License-Identifier: AGPL-3.0-only
"""Isolated owner-claim policy prototype. NOT a deployed onboarding mechanism.

Only a future *trusted physical-presence adapter* may call arm_physical().
A boolean argument cannot itself prove that a physical action occurred. No
HTTP, Bluetooth, Wi-Fi, OS credential, or service integration exists here.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

CLAIM_TTL_SECONDS = 120
MAX_ATTEMPTS = 5
SESSION_TTL_SECONDS = 600
SECRET_BYTES = 32


class ClaimDenied(Exception):
    """Uninformative denial: do not expose whether a claim secret was close."""


class OwnerClaimPolicy:
    """Bounded one-use claim and short-lived owner session in volatile memory.

    The caller MUST separately verify persistent 'factory unowned' state using
    trusted storage and a real physical event. A new Python instance loses
    state on reboot; it must never be used as the authoritative owner store.
    """

    def __init__(self, *, trusted_factory_unowned=False, clock=None, random_bytes=None):
        if type(trusted_factory_unowned) is not bool:
            raise ValueError("Explicit factory state must be a boolean")
        self._factory_unowned = trusted_factory_unowned
        self._clock = time.monotonic if clock is None else clock
        self._random_bytes = secrets.token_bytes if random_bytes is None else random_bytes
        self._lock = threading.Lock()
        self._claimed = False
        self._pending_digest = None
        self._deadline = 0.0
        self._remaining_attempts = 0
        self._session_digest = None
        self._session_deadline = 0.0

    def _secret(self):
        raw = self._random_bytes(SECRET_BYTES)
        if type(raw) is not bytes or len(raw) != SECRET_BYTES:
            raise RuntimeError("Secure random source unavailable")
        return raw.hex()

    @staticmethod
    def _digest(candidate):
        # Always hash to fixed-size bytes before the constant-time comparison.
        if type(candidate) is not str or len(candidate) != SECRET_BYTES * 2:
            return None
        if any(char not in "0123456789abcdef" for char in candidate):
            return None
        return hashlib.sha256(candidate.encode("ascii")).digest()

    def arm_physical(self, *, trusted_physical_event=False):
        """Issue one-use proof ONLY to a privileged physical/OOB adapter.

        The proof MUST NOT be returned from HTTP, logs, status, or Bluetooth.
        This module does not implement or verify the physical-event hardware.
        """
        with self._lock:
            if (trusted_physical_event is not True or not self._factory_unowned
                    or self._claimed):
                raise ClaimDenied("Claim not permitted")
            now = self._clock()
            if self._pending_digest is not None and now < self._deadline:
                raise ClaimDenied("Claim already pending")
            self._pending_digest = None
            self._remaining_attempts = 0
            self._deadline = 0.0
            proof = self._secret()
            self._pending_digest = self._digest(proof)
            self._deadline = now + CLAIM_TTL_SECONDS
            self._remaining_attempts = MAX_ATTEMPTS
            return proof

    def claim(self, proof):
        """Consume physical one-time proof; issue a *volatile* session token.

        Successful claim in memory is not a persistent ownership assertion.
        The trusted adapter must atomically persist claimed state BEFORE
        enabling any network-accessible authenticated service.
        """
        with self._lock:
            now = self._clock()
            if (self._claimed or not self._factory_unowned
                    or self._pending_digest is None or now >= self._deadline
                    or self._remaining_attempts <= 0):
                self._pending_digest = None
                self._remaining_attempts = 0
                raise ClaimDenied("Claim not permitted")
            provided = self._digest(proof)
            matches = (provided is not None
                       and hmac.compare_digest(provided, self._pending_digest))
            if not matches:
                self._remaining_attempts -= 1
                if not self._remaining_attempts:
                    self._pending_digest = None
                raise ClaimDenied("Claim not permitted")
            # Generate the session BEFORE consuming the one-use proof. If the
            # entropy source fails, the claim remains closed to outsiders.
            session = self._secret()
            session_digest = self._digest(session)
            if hmac.compare_digest(session_digest, self._pending_digest):
                # A broken/repeating entropy source must never issue a session
                # identical to the out-of-band one-time claim proof.
                raise RuntimeError("Independent secure session entropy unavailable")
            self._pending_digest = None
            self._remaining_attempts = 0
            self._deadline = 0.0
            self._claimed = True
            self._session_digest = session_digest
            self._session_deadline = now + SESSION_TTL_SECONDS
            return session

    def authorize_session(self, token):
        """In-memory short-lived capability; never a production owner identity."""
        with self._lock:
            if (not self._claimed or self._session_digest is None
                    or self._clock() >= self._session_deadline):
                return False
            provided = self._digest(token)
            return bool(provided is not None
                        and hmac.compare_digest(provided, self._session_digest))

    def revoke_session(self):
        """Close volatile session without reopening initial physical pairing."""
        with self._lock:
            self._session_digest = None
            self._session_deadline = 0.0

    def status(self):
        """Only public booleans, never OOB proof, session token or metadata."""
        with self._lock:
            now = self._clock()
            return {
                "claim_window_open": bool(
                    self._pending_digest is not None and now < self._deadline
                    and self._remaining_attempts > 0 and not self._claimed
                ),
                "volatile_claim_completed": self._claimed,
                "session_active": bool(
                    self._session_digest is not None
                    and now < self._session_deadline and self._claimed
                ),
                "durable_owner_verified": False,
                "network_onboarding_enabled": False,
                "release_ready": False,
            }
