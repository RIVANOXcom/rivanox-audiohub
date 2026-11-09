"""Driverless, low-volume manual speaker test over authenticated AudioHub TLS.

All tests are offline and synthetic: a passing test does NOT certify audible
Edifier playback or an installed Raspberry Pi.
"""
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import secure_lan as lan
from audiohub import windows_bridge_setup as setup


class SoundCheckTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key = Path(self.folder.name) / "private.bin"
        self.key.write_bytes(os.urandom(32))
        if os.name == "posix":
            self.key.chmod(0o600)
        self.pin = "a" * 64

    def test_tone_has_bounded_stereo_pcm_frames_and_no_clipping(self):
        self.assertEqual((lan.TONE_RATE, lan.TONE_SECONDS, lan.TONE_HZ),
                         (48000, 5, 440))
        self.assertLess(lan.TONE_AMPLITUDE, 1200)
        total = lan.TONE_SECONDS * lan.TONE_RATE
        for start in (0, 4800, total - 240):
            pcm = lan.make_test_tone_pcm(start, 240, total)
            self.assertEqual(len(pcm), 960)
            samples = struct.unpack("<" + "h" * 480, pcm)
            self.assertTrue(all(samples[i] == samples[i+1]
                                for i in range(0, 480, 2)))
            self.assertLessEqual(max(map(abs, samples)), lan.TONE_AMPLITUDE)
        self.assertEqual(lan.make_test_tone_pcm(0, 1, total), b"\x00" * 4)
        self.assertEqual(lan.make_test_tone_pcm(total - 1, 1, total), b"\x00" * 4)

    def test_each_stereo_channel_is_isolated_without_mixing(self):
        total = lan.TONE_RATE * lan.TONE_SECONDS
        for channel in ("left", "right", "both"):
            with self.subTest(channel=channel):
                pcm = lan.make_test_tone_pcm(
                    lan.TONE_RATE, 240, total, channel=channel)
                channels = struct.unpack("<" + "hh" * 240, pcm)
                left = channels[0::2]
                right = channels[1::2]
                if channel == "left":
                    self.assertGreater(max(map(abs, left)), 0)
                    self.assertTrue(all(x == 0 for x in right))
                elif channel == "right":
                    self.assertGreater(max(map(abs, right)), 0)
                    self.assertTrue(all(x == 0 for x in left))
                else:
                    self.assertEqual(left, right)
                    self.assertGreater(max(map(abs, left)), 0)
                self.assertLessEqual(max(map(abs, channels)), lan.TONE_AMPLITUDE)

    def test_sequence_left_silence_right_and_silence_in_five_seconds(self):
        total = lan.TONE_RATE * lan.TONE_SECONDS
        samples = (
            (lan.TONE_RATE, True, False),       # 1 s: left only
            (lan.TONE_RATE * 9 // 4, False, False),  # 2.25 s: gap
            (lan.TONE_RATE * 3, False, True),  # 3 s: right only
            (lan.TONE_RATE * 19 // 4, False, False),  # 4.75 s: silence
        )
        for start, want_left, want_right in samples:
            with self.subTest(start=start):
                pcm = lan.make_test_tone_pcm(
                    start, 240, total, channel="sequence")
                values = struct.unpack("<" + "hh" * 240, pcm)
                left = values[0::2]
                right = values[1::2]
                self.assertEqual(any(x != 0 for x in left), want_left)
                self.assertEqual(any(x != 0 for x in right), want_right)
                self.assertLessEqual(max(map(abs, values)), lan.TONE_AMPLITUDE)

    def test_sequence_edges_have_fade_and_zero_cross_silence(self):
        total = lan.TONE_RATE * lan.TONE_SECONDS
        for n in (0, 2 * lan.TONE_RATE - 1,
                  5 * lan.TONE_RATE // 2, 9 * lan.TONE_RATE // 2,
                  total - 1):
            with self.subTest(sample=n):
                self.assertEqual(
                    lan.make_test_tone_pcm(n, 1, total, channel="sequence"),
                    bytes(4))

    def test_channel_mode_rejects_unknown_and_unauthorized_selection(self):
        for name in (None, "", "LEFT", "center", "left-right", True, 1):
            with self.subTest(name=name), self.assertRaises(ValueError):
                lan.validate_tone_channel(name)
        self.assertEqual(
            tuple(lan.validate_tone_channel(name) for name in lan.TONE_CHANNELS),
            ("both", "left", "right", "sequence"))
        with mock.patch.object(lan.socket, "create_connection") as create:
            with self.assertRaisesRegex(ValueError, "requires explicit"):
                lan.run_bridge(
                    server_ip="192.168.10.30", port=4044, udp_port=4010,
                    key_file=self.key, pin_sha256=self.pin,
                    isolated_lab=True, test_tone=False, test_channel="left")
            create.assert_not_called()

    def test_channel_selection_flows_through_tls_no_udp(self):
        stream = mock.MagicMock()
        stream.__enter__.return_value = stream
        raw = mock.MagicMock()
        raw.__enter__.return_value = raw
        with mock.patch.object(lan.socket, "create_connection", return_value=raw), \
             mock.patch.object(lan, "make_client_tls", return_value=stream), \
             mock.patch.object(lan, "authenticate_client", return_value=True), \
             mock.patch.object(lan, "forward_test_tone", return_value=4) as tone, \
             mock.patch.object(lan.socket, "socket") as udp:
            result = lan.run_bridge(
                server_ip="192.168.10.30", port=4044, udp_port=4010,
                key_file=self.key, pin_sha256=self.pin,
                isolated_lab=True, test_tone=True, test_channel="sequence")
            self.assertEqual(result, 4)
            self.assertEqual(tone.call_args.kwargs["channel"], "sequence")
            udp.assert_not_called()

    def test_cli_channel_requires_tone_and_explicit_operator_consent(self):
        output = []
        execute = mock.Mock(return_value=7)
        answer = iter(["192.168.10.30", self.pin, str(self.key), "1",
                       "ISOLATED"])
        self.assertEqual(setup.interactive_bridge(
            input_fn=lambda _: next(answer), output=output.append,
            execute=execute, test_tone=True, test_channel="right"), 0)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.kwargs["test_channel"], "right")
        self.assertIn("right", " ".join(output))
        with mock.patch.object(lan.socket, "create_connection") as dial, \
             self.assertRaises(ValueError):
            setup.interactive_bridge(
                input_fn=lambda _: self.fail("should not prompt"),
                test_channel="right")
            dial.assert_not_called()

    def test_tone_rejects_unbounded_or_malformed_generation(self):
        for args in ((-1, 5, 240000), (0, 0, 240000),
                     (0, 241, 240000), (240000, 1, 240000),
                     (0, 240, 50)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                lan.make_test_tone_pcm(*args)
        for duration in (0, -1, 5.001, 30, False, "5"):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                lan.forward_test_tone(mock.Mock(), time.monotonic() + 10,
                                      seconds=duration)

    def test_generated_tone_is_framed_paced_and_stops_at_five_seconds(self):
        sender = mock.Mock()
        frames = lan.forward_test_tone(sender, time.monotonic() + 2, seconds=0.025)
        self.assertEqual(frames, 5)
        self.assertEqual(sender.sendall.call_count, 5)
        for call in sender.sendall.call_args_list:
            payload = call.args[0]
            length = struct.unpack("!H", payload[:2])[0]
            self.assertEqual(length, len(payload) - 2)
            self.assertTrue(4 <= length <= 1152)
            self.assertEqual(length % 4, 0)
        sender.settimeout.assert_called_once_with(0.5)

    def test_cancelled_test_does_not_send_frames(self):
        stop = threading.Event()
        stop.set()
        stream = mock.Mock()
        self.assertEqual(lan.forward_test_tone(stream, time.monotonic() + 10,
                                               stop_event=stop), 0)
        stream.sendall.assert_not_called()

    def test_tone_bridge_reuses_exact_tls_auth_but_never_opens_scream_udp(self):
        # Separate mock network operation from a genuine hardware test.
        stream = mock.MagicMock()
        stream.__enter__.return_value = stream
        raw = mock.MagicMock()
        raw.__enter__.return_value = raw
        with mock.patch.object(lan.socket, "create_connection", return_value=raw) as dial, \
             mock.patch.object(lan, "make_client_tls", return_value=stream) as tls, \
             mock.patch.object(lan, "authenticate_client", return_value=True) as auth, \
             mock.patch.object(lan, "forward_test_tone", return_value=5) as tone, \
             mock.patch.object(lan.socket, "socket") as udp:
            result = lan.run_bridge(
                server_ip="192.168.10.30", port=4044, udp_port=4010,
                key_file=self.key, pin_sha256=self.pin,
                isolated_lab=True, test_tone=True)
            self.assertEqual(result, 5)
            dial.assert_called_once()
            tls.assert_called_once_with(raw, self.pin)
            auth.assert_called_once()
            tone.assert_called_once()
            udp.assert_not_called()

    def test_terminal_tone_requires_literal_consent_and_no_external_driver(self):
        answers = iter(["192.168.10.30", self.pin, str(self.key), "1",
                        "ISOLATED"])
        called = []
        def fake_bridge(**kwargs):
            called.append(kwargs)
            return 4
        output = []
        status = setup.interactive_bridge(
            input_fn=lambda _: next(answers), output=output.append,
            execute=fake_bridge, test_tone=True)
        self.assertEqual(status, 0)
        self.assertTrue(called[0]["test_tone"])
        self.assertTrue(called[0]["isolated_lab"])
        self.assertTrue(any("NO Windows Scream driver" in msg for msg in output))
        self.assertFalse(any(str(self.key) in msg for msg in output))
        self.assertFalse(any(self.pin in msg for msg in output))

    def test_terminal_tone_cancelled_before_connection(self):
        answers = iter(["192.168.10.30", self.pin, str(self.key), "1",
                        "not ISOLATED"])
        execute = mock.Mock()
        self.assertEqual(
            setup.interactive_bridge(
                input_fn=lambda _: next(answers), output=lambda _: None,
                execute=execute, test_tone=True),
            1)
        execute.assert_not_called()

    def test_receiving_complete_pcm_then_closed_stream_is_clean(self):
        stream = mock.Mock()
        stream.recv.side_effect = [b"\x00\x04", b"\x00" * 4, b""]
        process = mock.Mock()
        process.stdin.fileno.return_value = 21
        process.poll.return_value = None
        with mock.patch.object(lan, "check_audio_target", return_value=(3, 9)), \
             mock.patch.object(lan, "lan_target", return_value="audiohub.laptop"), \
             mock.patch.object(lan.subprocess, "Popen", return_value=process), \
             mock.patch.object(lan, "close_player") as close, \
             mock.patch.object(lan.os, "set_blocking"), \
             mock.patch.object(lan.os, "write", return_value=4):
            count = lan.consume_authenticated_pcm(
                stream, "audiohub.laptop", time.monotonic() + 10)
            self.assertEqual(count, 1)
            close.assert_called_once_with(process)

    def test_receiving_incomplete_first_frame_is_not_success(self):
        stream = mock.Mock()
        stream.recv.side_effect = [b""]
        with mock.patch.object(lan, "check_audio_target", return_value=(3, 9)), \
             mock.patch.object(lan, "lan_target", return_value="audiohub.laptop"), \
             mock.patch.object(lan.subprocess, "Popen") as player:
            with self.assertRaises(ConnectionError):
                lan.consume_authenticated_pcm(
                    stream, "audiohub.laptop", time.monotonic() + 10)
            player.assert_not_called()


if __name__ == "__main__":
    unittest.main()
