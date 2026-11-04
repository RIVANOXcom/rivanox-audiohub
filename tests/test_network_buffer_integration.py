"""Integration-style mocked tests of bounded receiver buffering and diagnostics."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import network_laptop


def packet(payload=b"abcd", rate=1, width=16, channels=2, mask=3):
    return bytes((rate, width, channels)) + mask.to_bytes(2, "little") + payload


class NetworkBufferIntegrationTests(unittest.TestCase):
    def test_two_packet_prefill_starts_single_player(self):
        with mock.patch("audiohub.network_laptop.check_audio_target") as check, \
             mock.patch("audiohub.network_laptop.socket.socket") as sock, \
             mock.patch("audiohub.network_laptop.subprocess.Popen") as popen, \
             mock.patch("audiohub.network_laptop.os.set_blocking"), \
             mock.patch("audiohub.network_laptop.os.write", return_value=4) as writer, \
             mock.patch("audiohub.network_laptop.close_player"):
            receiver = sock.return_value.__enter__.return_value
            receiver.recvfrom.side_effect = [
                (packet(b"abcd"), ("192.168.1.10", 4010)),
                (packet(b"wxyz"), ("192.168.1.10", 4010)),
                KeyboardInterrupt(),
            ]
            popen.return_value.stdin.fileno.return_value = 42
            with self.assertRaises(KeyboardInterrupt):
                network_laptop.serve("192.168.1.10", "127.0.0.1", 4010, prefill_packets=2)
            popen.assert_called_once()
            writer.assert_called_once_with(42, b"abcd")
            self.assertEqual(check.call_count, 2)

    def test_backpressure_retains_first_packet_until_next_datagram(self):
        with mock.patch("audiohub.network_laptop.check_audio_target"), \
             mock.patch("audiohub.network_laptop.socket.socket") as sock, \
             mock.patch("audiohub.network_laptop.subprocess.Popen") as popen, \
             mock.patch("audiohub.network_laptop.os.set_blocking"), \
             mock.patch("audiohub.network_laptop.os.write",
                        side_effect=[BlockingIOError(), 4]) as writer, \
             mock.patch("audiohub.network_laptop.close_player"):
            receiver = sock.return_value.__enter__.return_value
            receiver.recvfrom.side_effect = [
                (packet(b"abcd"), ("192.168.1.10", 4010)),
                (packet(b"wxyz"), ("192.168.1.10", 4010)),
                KeyboardInterrupt(),
            ]
            popen.return_value.stdin.fileno.return_value = 42
            popen.return_value.poll.return_value = None
            with self.assertRaises(KeyboardInterrupt):
                network_laptop.serve("192.168.1.10", "127.0.0.1", 4010)
            self.assertEqual(writer.call_count, 2)
            writer.assert_any_call(42, b"abcd")

    def test_diagnostics_report_aggregates_not_peer_addresses(self):
        with mock.patch("audiohub.network_laptop.check_audio_target"), \
             mock.patch("audiohub.network_laptop.socket.socket") as sock, \
             mock.patch("audiohub.network_laptop.sys.stderr", new_callable=io.StringIO) as output, \
             mock.patch("audiohub.network_laptop.subprocess.Popen") as popen:
            receiver = sock.return_value.__enter__.return_value
            receiver.recvfrom.side_effect = [
                (packet(), ("192.168.1.99", 4010)),
                (packet(width=24), ("192.168.1.10", 4010)),
                KeyboardInterrupt(),
            ]
            with self.assertRaises(KeyboardInterrupt):
                network_laptop.serve("192.168.1.10", "127.0.0.1", 4010, diagnostics=True)
            line = output.getvalue().strip()
            self.assertTrue(line.startswith("audiohub.network "))
            counters = json.loads(line[len("audiohub.network "):])
            self.assertEqual(counters["datagrams"], 2)
            self.assertEqual(counters["foreign_sender"], 1)
            self.assertEqual(counters["invalid_format"], 1)
            self.assertEqual(counters["accepted"], 0)
            self.assertNotIn("192.168.1.", line)
            popen.assert_not_called()

    def test_cli_forwards_explicit_prefill_and_diagnostics(self):
        with mock.patch("audiohub.network_laptop.serve") as receiver:
            network_laptop.main([
                "--sender-ip", "127.0.0.1", "--bind-ip", "127.0.0.1",
                "--unsafe-lan-test", "--prefill-packets", "3", "--diagnostics",
            ])
            receiver.assert_called_once_with(
                "127.0.0.1", "127.0.0.1", 4010,
                prefill_packets=3, diagnostics=True,
            )


if __name__ == "__main__":
    unittest.main()
