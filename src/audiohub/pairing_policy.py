# SPDX-License-Identifier: AGPL-3.0-only
"""Pure, fail-closed guards for temporary BlueZ pairing authorization."""
from __future__ import annotations

MAX_PEERS = 2
PENDING_TTL_SECONDS = 90


def may_pair(initially_unpaired, now, deadline, paired_count):
    return (
        initially_unpaired is True
        and isinstance(now, (int, float))
        and isinstance(deadline, (int, float))
        and now < deadline
        and isinstance(paired_count, int) and not isinstance(paired_count, bool)
        and 0 <= paired_count < MAX_PEERS
    )


def may_trust_pair(initially_unpaired, now, deadline, paired_count, candidate_authorized):
    """Only trust a bounded device that was challenged by our current agent."""
    return (
        initially_unpaired is True
        and candidate_authorized is True
        and isinstance(now, (int, float))
        and isinstance(deadline, (int, float))
        and now < deadline
        and isinstance(paired_count, int) and not isinstance(paired_count, bool)
        and 1 <= paired_count <= MAX_PEERS
    )


def valid_pending(now, expiry):
    return isinstance(expiry, (float, int)) and now < expiry
