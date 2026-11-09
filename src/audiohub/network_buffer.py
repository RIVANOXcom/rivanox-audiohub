# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded PCM packet backlog and privacy-safe counters for a LAN test receiver.

This is not a sequence-aware jitter buffer: the legacy Scream UDP protocol
carries no sequence number, and late/reordered frames cannot be reconstructed.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import json

MAX_PCM_PACKET_BYTES = 1152
MAX_BUFFER_PACKETS = 16


class PcmPacketBuffer:
    """Keep a finite, frame-aligned packet backlog with optional prefill.

    When full, discard the oldest packet to limit latency instead of allowing
    memory growth or replaying stale audio after a stalled writer recovers.
    """

    def __init__(self, capacity=MAX_BUFFER_PACKETS, prefill=1):
        if (isinstance(capacity, bool) or not isinstance(capacity, int)
                or not 1 <= capacity <= MAX_BUFFER_PACKETS):
            raise ValueError("PCM capacity must be 1..16 packets")
        if (isinstance(prefill, bool) or not isinstance(prefill, int)
                or not 1 <= prefill <= capacity):
            raise ValueError("PCM prefill must be 1..capacity packets")
        self.capacity = capacity
        self.prefill = prefill
        self._packets = deque()
        self._ready = False
        self.dropped_oldest = 0

    def append(self, pcm):
        if (not isinstance(pcm, bytes) or not 4 <= len(pcm) <= MAX_PCM_PACKET_BYTES
                or len(pcm) % 4):
            raise ValueError("PCM must be nonempty aligned stereo S16LE frames")
        if len(self._packets) == self.capacity:
            self._packets.popleft()
            self.dropped_oldest += 1
        self._packets.append(pcm)
        if len(self._packets) >= self.prefill:
            self._ready = True

    def peek(self):
        return self._packets[0] if self._ready and self._packets else None

    def consume(self):
        if self.peek() is None:
            raise ValueError("No ready PCM packet")
        pcm = self._packets.popleft()
        if not self._packets:
            self._ready = False
        return pcm

    def clear(self):
        """Discard backlog on USB, player or sender reset; prevent stale replay."""
        self._packets.clear()
        self._ready = False

    @property
    def packet_count(self):
        return len(self._packets)


@dataclass
class ReceiverCounters:
    """Aggregate in-memory counts only; no IP addresses, payload or device IDs."""

    datagrams: int = 0
    foreign_sender: int = 0
    invalid_format: int = 0
    accepted: int = 0
    backlog_dropped: int = 0
    write_blocked: int = 0
    write_failed: int = 0
    player_started: int = 0
    player_stopped: int = 0
    idle_shutdown: int = 0
    output_lost: int = 0
    session_expired: int = 0

    def json_line(self):
        """Stable machine-readable line for manual engineer diagnostics."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
