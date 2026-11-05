"""Finite LAN PCM buffering and failure diagnostics regression tests."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.network_buffer import PcmPacketBuffer, ReceiverCounters


FRAME_A = b"\x01\x02\x03\x04"
FRAME_B = b"\x05\x06\x07\x08"
FRAME_C = b"\x09\x0a\x0b\x0c"


class PacketBufferTests(unittest.TestCase):
    def test_prefill_and_rearm_after_drain(self):
        q = PcmPacketBuffer(capacity=4, prefill=3)
        q.append(FRAME_A)
        q.append(FRAME_B)
        self.assertIsNone(q.peek())
        q.append(FRAME_C)
        self.assertEqual(q.peek(), FRAME_A)
        self.assertEqual(q.consume(), FRAME_A)
        self.assertEqual(q.consume(), FRAME_B)
        self.assertEqual(q.consume(), FRAME_C)
        self.assertIsNone(q.peek())
        self.assertEqual(q.packet_count, 0)
        q.append(FRAME_A)
        self.assertIsNone(q.peek())

    def test_saturated_queue_drops_oldest_not_newest(self):
        q = PcmPacketBuffer(capacity=2, prefill=1)
        q.append(FRAME_A)
        q.append(FRAME_B)
        q.append(FRAME_C)
        self.assertEqual(q.packet_count, 2)
        self.assertEqual(q.dropped_oldest, 1)
        self.assertEqual(q.consume(), FRAME_B)
        self.assertEqual(q.consume(), FRAME_C)

    def test_high_volume_input_has_hard_memory_bound(self):
        q = PcmPacketBuffer(capacity=16, prefill=3)
        for i in range(1000):
            q.append(bytes([i % 256]) * 1152)
            self.assertLessEqual(q.packet_count * 1152, 18432)
        self.assertEqual(q.packet_count, 16)
        self.assertEqual(q.dropped_oldest, 984)

    def test_clear_discards_stale_frames_and_needs_new_prefill(self):
        q = PcmPacketBuffer(capacity=4, prefill=2)
        q.append(FRAME_A)
        q.append(FRAME_B)
        q.clear()
        self.assertIsNone(q.peek())
        self.assertEqual(q.packet_count, 0)
        q.append(FRAME_C)
        self.assertIsNone(q.peek())
        q.append(FRAME_A)
        self.assertEqual(q.peek(), FRAME_C)

    def test_invalid_capacity_or_prefill_is_rejected(self):
        for capacity, prefill in ((0, 1), (17, 1), (3, 4), (2, 0), (True, 1), (3, True), (2.2, 1)):
            with self.subTest(capacity=capacity, prefill=prefill), self.assertRaises(ValueError):
                PcmPacketBuffer(capacity=capacity, prefill=prefill)

    def test_non_pcm_and_unaligned_packets_are_rejected(self):
        q = PcmPacketBuffer()
        for payload in (b"", b"abc", bytes(1156), "ABCD", bytearray(FRAME_A), 42):
            with self.subTest(payload=str(payload)[:16]), self.assertRaises(ValueError):
                q.append(payload)
        self.assertEqual(q.packet_count, 0)

    def test_consume_requires_prefill(self):
        q = PcmPacketBuffer(prefill=2)
        q.append(FRAME_A)
        with self.assertRaises(ValueError):
            q.consume()

    def test_counters_emit_only_aggregate_machine_readable_values(self):
        counters = ReceiverCounters(datagrams=4, foreign_sender=2, accepted=1, write_blocked=3)
        raw = counters.json_line()
        parsed = json.loads(raw)
        self.assertEqual(parsed["datagrams"], 4)
        self.assertEqual(parsed["foreign_sender"], 2)
        self.assertEqual(parsed["write_blocked"], 3)
        self.assertNotIn("address", raw)
        self.assertNotIn("payload", raw)
        self.assertNotIn("192.168", raw)


if __name__ == "__main__":
    unittest.main()
