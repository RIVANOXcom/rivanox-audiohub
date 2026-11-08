"""Source-only tests for the manual, unauthenticated LAN audio prototype."""
import json
import socket
import sys
import subprocess
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import network_laptop as laptop


def packet(payload=b"\x01\x02\x03\x04", rate=1, width=16, channels=2, mask=3):
    return bytes((rate, width, channels)) + mask.to_bytes(2, "little") + payload


def node(nid, name, media_class):
    return {
        "id": nid, "type": "PipeWire:Interface:Node",
        "info": {"props": {"node.name": name, "media.class": media_class}}
    }


class NetworkLaptopTests(unittest.TestCase):
    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_direct_serve_cannot_bypass_manual_lan_opt_in(self, socket, target):
        with self.assertRaisesRegex(ValueError, "opt-in"):
            laptop.serve("192.168.1.10", "192.168.1.20", 4010)
        socket.assert_not_called()
        target.assert_not_called()

    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_manual_opt_in_still_rejects_wildcard_binding(self, socket, target):
        with self.assertRaisesRegex(ValueError, "specific"):
            laptop.serve("192.168.1.10", "0.0.0.0", 4010, unsafe_lan_test=True)
        socket.assert_not_called()
        target.assert_not_called()

    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_malformed_prefill_cannot_open_receiver_port(self, socket, target):
        with self.assertRaises(ValueError):
            laptop.serve("192.168.1.10", "192.168.1.20", 4010,
                         unsafe_lan_test=True, prefill_packets=17)
        socket.assert_not_called()
        target.assert_not_called()

    def test_legacy_scream_stereo_frame_is_parsed(self):
        data = bytes(1152)
        self.assertEqual(laptop.parse_scream_packet(packet(data)), data)
        self.assertEqual(laptop.parse_scream_packet(packet(data, mask=0)), data)

    def test_invalid_packets_are_dropped(self):
        good = packet()
        bad = (
            b"", b"short", good + b"x", packet(b"abc"),
            packet(bytes(1156)), packet(rate=0x81),
            packet(width=24), packet(channels=6),
            packet(mask=4), bytearray(good), "not bytes",
        )
        for value in bad:
            with self.subTest(value=str(value)[:30]):
                self.assertIsNone(laptop.parse_scream_packet(value))

    def test_explicit_untrusted_lan_opt_in_is_mandatory(self):
        with self.assertRaises(ValueError):
            laptop.validate_options("192.168.1.10", "192.168.1.20", 4010, False)
        self.assertEqual(
            laptop.validate_options("192.168.1.10", "192.168.1.20", 4010, True),
            ("192.168.1.10", "192.168.1.20", 4010),
        )
        self.assertEqual(
            laptop.validate_options("127.0.0.1", "127.0.0.1", 4010, True),
            ("127.0.0.1", "127.0.0.1", 4010),
        )

    def test_public_or_unsafe_sender_and_bind_addresses_are_rejected(self):
        for sender, bind in (
            ("8.8.8.8", "192.168.1.20"),
            ("239.255.77.77", "192.168.1.20"),
            ("0.0.0.0", "192.168.1.20"),
            ("2001:db8::1", "192.168.1.20"),
            ("192.168.1.10", "8.8.8.8"),
            ("192.168.1.10", "239.255.77.77"),
        ):
            with self.subTest(sender=sender, bind=bind), self.assertRaises(ValueError):
                laptop.validate_options(sender, bind, 4010, True)
        for port in (0, 80, 65536, True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                laptop.validate_options("127.0.0.1", "127.0.0.1", port, True)

    def test_sender_allowlist_is_exact(self):
        data = packet()
        self.assertEqual(laptop.accepted_pcm(data, ("192.168.1.10", 4000), "192.168.1.10"), data[5:])
        self.assertIsNone(laptop.accepted_pcm(data, ("192.168.1.11", 4000), "192.168.1.10"))
        self.assertIsNone(laptop.accepted_pcm(packet(width=24), ("192.168.1.10", 4000), "192.168.1.10"))

    def test_player_only_targets_isolated_laptop_sink(self):
        command = laptop.player_command()
        self.assertEqual(command[0], "pw-cat")
        self.assertIn("--target=audiohub.laptop", command)
        self.assertNotIn("--target=auto", command)
        self.assertIn("--rate=48000", command)
        self.assertIn("--raw", command)
        self.assertEqual(command[-1], "-")

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_audio_target_requires_both_sink_and_usb(self, run):
        found = [
            node(5, "audiohub.laptop", "Audio/Sink"),
            node(10, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        ]
        run.return_value = subprocess.CompletedProcess(["pw-dump"], 0, json.dumps(found), "")
        self.assertEqual(laptop.check_audio_target(), (5, 10))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], ("wpctl", "set-default", "10"))
        self.assertEqual(run.call_args.kwargs, {"timeout": 5})
        self.assertEqual(run.call_args_list[0].args[0], ("pw-dump",))
        run.return_value = subprocess.CompletedProcess(["pw-dump"], 0, json.dumps(found[:1]), "")
        with self.assertRaisesRegex(RuntimeError, "USB"):
            laptop.check_audio_target()
        run.return_value = subprocess.CompletedProcess(["pw-dump"], 0, json.dumps(found[1:]), "")
        with self.assertRaisesRegex(RuntimeError, "Laptop"):
            laptop.check_audio_target()
        run.return_value = subprocess.CompletedProcess(["pw-dump"], 1, "", "error")
        with self.assertRaises(RuntimeError):
            laptop.check_audio_target()

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_missing_usb_default_selection_denies_laptop_audio(self, run):
        found = [
            node(5, "audiohub.laptop", "Audio/Sink"),
            node(10, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        ]
        run.side_effect = [
            subprocess.CompletedProcess(["pw-dump"], 0, json.dumps(found), ""),
            subprocess.CompletedProcess(["wpctl", "set-default", "10"], 1, "", "error"),
        ]
        with self.assertRaisesRegex(RuntimeError, "routing not ready"):
            laptop.check_audio_target()
        self.assertEqual(run.call_count, 2)

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_oversized_pipewire_capture_rejects_before_usb_mutation(self, command):
        # The shared 4 MiB/5 s reader returns None on oversized output,
        # invalid UTF-8, missing executable, or timeout.
        command.return_value = None
        with self.assertRaisesRegex(RuntimeError, "inspection failed"):
            laptop.check_audio_target()
        command.assert_called_once_with(("pw-dump",), timeout=5)

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_corrupt_or_failed_graph_never_runs_wpctl(self, command):
        for result in (
            subprocess.CompletedProcess(("pw-dump",), 17, "", ""),
            subprocess.CompletedProcess(("pw-dump",), 0, "{not json", ""),
            subprocess.CompletedProcess(("pw-dump",), 0, "[]", ""),
        ):
            with self.subTest(result=result.returncode, stdout=result.stdout):
                command.reset_mock()
                command.return_value = result
                with self.assertRaises(RuntimeError):
                    laptop.check_audio_target()
                command.assert_called_once_with(("pw-dump",), timeout=5)

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_ambiguous_virtual_sink_denies_usb_mutation(self, command):
        graph = [
            node(5, "audiohub.laptop", "Audio/Sink"),
            node(6, "audiohub.laptop", "Audio/Sink"),
            node(10, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        ]
        command.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(graph), ""
        )
        with self.assertRaisesRegex(RuntimeError, "virtual sink unavailable"):
            laptop.check_audio_target()
        command.assert_called_once_with(("pw-dump",), timeout=5)

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_duplicate_usb_node_id_denies_usb_mutation(self, command):
        graph = [
            node(5, "audiohub.laptop", "Audio/Sink"),
            node(5, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        ]
        command.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(graph), ""
        )
        with self.assertRaises(RuntimeError):
            laptop.check_audio_target()
        command.assert_called_once_with(("pw-dump",), timeout=5)

    @mock.patch("audiohub.network_laptop.bounded_command_output")
    def test_wpctl_bounded_capture_failure_refuses_startup(self, command):
        graph = [
            node(5, "audiohub.laptop", "Audio/Sink"),
            node(10, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
        ]
        command.side_effect = [
            subprocess.CompletedProcess(("pw-dump",), 0, json.dumps(graph), ""),
            None,  # capped/timeout/failure; cannot assert default selection
        ]
        with self.assertRaisesRegex(RuntimeError, "routing not ready"):
            laptop.check_audio_target()
        self.assertEqual(command.call_count, 2)
        self.assertEqual(command.call_args_list[1].args[0],
                         ("wpctl", "set-default", "10"))
        self.assertEqual(command.call_args_list[1].kwargs, {"timeout": 5})

    def test_manual_receiver_cannot_buffer_unbounded_pw_dump(self):
        code = (Path(__file__).resolve().parents[1] /
                "src/audiohub/network_laptop.py").read_text()
        self.assertIn("from .process_capture import bounded_command_output", code)
        self.assertIn('bounded_command_output(("pw-dump",), timeout=5)', code)
        self.assertIn('bounded_command_output(', code)
        self.assertNotIn("capture_output=True", code)
        self.assertNotIn("subprocess.run(", code)

    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_stranger_or_malformed_packets_never_start_player(self, sock, player, target):
        receiver = sock.return_value.__enter__.return_value
        receiver.recvfrom.side_effect = [
            (packet(), ("192.168.1.99", 4010)),
            (packet(width=24), ("192.168.1.10", 4010)),
            KeyboardInterrupt(),
        ]
        with self.assertRaises(KeyboardInterrupt):
            laptop.serve("192.168.1.10", "127.0.0.1", 4010, unsafe_lan_test=True)
        receiver.bind.assert_called_once_with(("127.0.0.1", 4010))
        player.assert_not_called()

    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.close_player")
    @mock.patch("audiohub.network_laptop.os.write", return_value=4)
    @mock.patch("audiohub.network_laptop.os.set_blocking")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_valid_sender_streams_only_pcm_to_pipewire(
        self, sock, player, set_blocking, write, close_player, target
    ):
        receiver = sock.return_value.__enter__.return_value
        receiver.recvfrom.side_effect = [(packet(), ("192.168.1.10", 4010)), KeyboardInterrupt()]
        process = player.return_value
        process.stdin.fileno.return_value = 42
        process.poll.return_value = None
        with self.assertRaises(KeyboardInterrupt):
            laptop.serve("192.168.1.10", "127.0.0.1", 4010, unsafe_lan_test=True)
        command = player.call_args.args[0]
        self.assertIn("--target=audiohub.laptop", command)
        write.assert_called_once_with(42, b"\x01\x02\x03\x04")
        set_blocking.assert_called_once_with(42, False)
        close_player.assert_called_once_with(process)


    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.close_player")
    @mock.patch("audiohub.network_laptop.os.write", return_value=4)
    @mock.patch("audiohub.network_laptop.os.set_blocking")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.time.monotonic")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_stable_sink_and_usb_generation_does_not_restart_lan_player(
        self, sock, clock, popen, set_blocking, write, close_player, check_target
    ):
        receiver = sock.return_value.__enter__.return_value
        receiver.recvfrom.side_effect = [
            (packet(), ("192.168.1.10", 4010)),
            socket.timeout(),
            KeyboardInterrupt(),
        ]
        clock.side_effect = [100., 100., 100., 104., 105.]
        check_target.return_value = (5, 10)
        process = popen.return_value
        process.poll.return_value = None
        process.stdin.fileno.return_value = 42
        with self.assertRaises(KeyboardInterrupt):
            laptop.serve("192.168.1.10", "127.0.0.1", 4010,
                         unsafe_lan_test=True)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(check_target.call_count, 3)
        close_player.assert_called_once_with(process)

    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.close_player")
    @mock.patch("audiohub.network_laptop.os.write", return_value=4)
    @mock.patch("audiohub.network_laptop.os.set_blocking")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.time.monotonic")
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_recreated_eq_or_usb_node_restarts_opt_in_lan_player_without_stale_pcm(
        self, sock, clock, popen, set_blocking, write, close_player, check_target
    ):
        for new_graph in ((6, 10), (5, 11)):
            with self.subTest(new_graph=new_graph):
                receiver = sock.return_value.__enter__.return_value
                receiver.recvfrom.side_effect = [
                    (packet(), ("192.168.1.10", 4010)),
                    socket.timeout(),
                    (packet(b"ABCD"), ("192.168.1.10", 4010)),
                    KeyboardInterrupt(),
                ]
                check_target.side_effect = [
                    (5, 10), (5, 10), new_graph, new_graph,
                ]
                clock.side_effect = [
                    100., 100., 100., 104., 107., 107., 107., 108.,
                ]
                first, second = mock.Mock(), mock.Mock()
                for process in (first, second):
                    process.poll.return_value = None
                    process.stdin.fileno.return_value = 42
                popen.side_effect = [first, second]
                with self.assertRaises(KeyboardInterrupt):
                    laptop.serve("192.168.1.10", "127.0.0.1", 4010,
                                 unsafe_lan_test=True)
                self.assertEqual(popen.call_count, 2)
                self.assertEqual(check_target.call_count, 4)
                self.assertEqual(close_player.call_count, 2)
                self.assertEqual(close_player.call_args_list[0].args, (first,))
                self.assertEqual(close_player.call_args_list[1].args, (second,))
                self.assertEqual(write.call_count, 2)
                self.assertEqual(write.call_args_list[-1].args[1], b"ABCD")
                self.assertTrue(all(
                    "--target=audiohub.laptop" in call.args[0]
                    for call in popen.call_args_list
                ))
                receiver.recvfrom.reset_mock(side_effect=True)
                for obj in (popen, check_target, clock, close_player, write):
                    obj.reset_mock(side_effect=True)

    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.close_player")
    @mock.patch("audiohub.network_laptop.os.write", return_value=4)
    @mock.patch("audiohub.network_laptop.os.set_blocking")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.time.monotonic", side_effect=[100.0, 100.0, 100.0, 106.0])
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_idle_sender_releases_player(
        self, sock, clock, popen, set_blocking, write, close_player, check_target
    ):
        receiver = sock.return_value.__enter__.return_value
        receiver.recvfrom.side_effect = [(packet(), ("192.168.1.10", 4010)), KeyboardInterrupt()]
        process = popen.return_value
        process.stdin.fileno.return_value = 42
        process.poll.return_value = None
        with self.assertRaises(KeyboardInterrupt):
            laptop.serve("192.168.1.10", "127.0.0.1", 4010, unsafe_lan_test=True)
        close_player.assert_any_call(process)
        self.assertEqual(write.call_count, 1)

    @mock.patch("audiohub.network_laptop.check_audio_target",
                side_effect=[None, None, RuntimeError("USB removed")])
    @mock.patch("audiohub.network_laptop.close_player")
    @mock.patch("audiohub.network_laptop.os.write", return_value=4)
    @mock.patch("audiohub.network_laptop.os.set_blocking")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.time.monotonic", side_effect=[100.0, 100.0, 100.0, 104.0])
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_usb_disappearance_stops_playback(
        self, sock, clock, popen, set_blocking, write, close_player, check_target
    ):
        receiver = sock.return_value.__enter__.return_value
        receiver.recvfrom.side_effect = [(packet(), ("192.168.1.10", 4010)), KeyboardInterrupt()]
        process = popen.return_value
        process.stdin.fileno.return_value = 42
        process.poll.return_value = None
        with self.assertRaises(KeyboardInterrupt):
            laptop.serve("192.168.1.10", "127.0.0.1", 4010, unsafe_lan_test=True)
        self.assertEqual(check_target.call_count, 3)
        close_player.assert_any_call(process)
        self.assertEqual(write.call_count, 1)


    @mock.patch("audiohub.network_laptop.check_audio_target")
    @mock.patch("audiohub.network_laptop.close_player")
    @mock.patch("audiohub.network_laptop.os.write", side_effect=BlockingIOError)
    @mock.patch("audiohub.network_laptop.os.set_blocking")
    @mock.patch("audiohub.network_laptop.subprocess.Popen")
    @mock.patch("audiohub.network_laptop.time.monotonic",
                side_effect=[100.0, 100.0, 100.0, 106.0, 107.0])
    @mock.patch("audiohub.network_laptop.socket.socket")
    def test_first_pcm_write_always_blocked_still_stops_idle_player(
        self, sock, clock, popen, set_blocking, write, close_player, check_target
    ):
        """Without startup deadline, zero successful PCM writes stall forever."""
        receiver = sock.return_value.__enter__.return_value
        receiver.recvfrom.side_effect = [
            (packet(), ("192.168.1.10", 4010)),
            socket.timeout(),
            KeyboardInterrupt(),
        ]
        process = popen.return_value
        process.stdin.fileno.return_value = 42
        process.poll.return_value = None
        with self.assertRaises(KeyboardInterrupt):
            laptop.serve("192.168.1.10", "127.0.0.1", 4010,
                         unsafe_lan_test=True)
        # The five-second timeout must stop the blocked process and discard
        # stale PCM rather than retry the same unsent packet indefinitely.
        self.assertEqual(write.call_count, 1)
        close_player.assert_called_once_with(process)
        self.assertEqual(popen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
