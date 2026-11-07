"""Isolated source-only tests: never play audio or discover actual devices."""
import json
import struct
from threading import Barrier
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import usb_soundcheck as soundcheck


def node(index, name, media_class="Audio/Sink"):
    return {"id": index, "type": "PipeWire:Interface:Node",
            "info": {"props": {"node.name": name, "media.class": media_class}}}


EDIFIER = "alsa_output.usb-Edifier_R600USB-00.analog-stereo"


class UsbSoundcheckTests(unittest.TestCase):
    def test_fixed_quiet_stereo_pattern_is_bounded_and_channel_isolated(self):
        pcm = soundcheck.stereo_pattern()
        left = soundcheck.PULSE_FRAMES
        gap = soundcheck.GAP_FRAMES
        self.assertEqual(len(pcm), 4 * (2 * left + gap))
        self.assertLess(len(pcm), 100_000)
        samples = list(struct.iter_unpack("<hh", pcm))
        self.assertTrue(any(pair[0] for pair in samples[:left]))
        self.assertTrue(all(pair[1] == 0 for pair in samples[:left]))
        self.assertTrue(all(pair == (0, 0) for pair in samples[left:left + gap]))
        self.assertTrue(any(pair[1] for pair in samples[left + gap:]))
        self.assertTrue(all(pair[0] == 0 for pair in samples[left + gap:]))
        self.assertLessEqual(max(max(abs(a), abs(b)) for a, b in samples), 656)
        self.assertLess(len(samples) / soundcheck.RATE, 1)

    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_without_explicit_confirmation_never_inspects_or_plays(self, inspect, player):
        for flag in (False, None, 1, "yes"):
            with self.subTest(flag=flag), self.assertRaisesRegex(
                    soundcheck.SoundcheckUnavailable, "confirmation"):
                soundcheck.run_soundcheck(confirmed=flag)
        inspect.assert_not_called()
        player.assert_not_called()

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=0)
    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_root_cannot_play_automatically(self, inspect, player, euid):
        with self.assertRaisesRegex(soundcheck.SoundcheckUnavailable, "unprivileged"):
            soundcheck.run_soundcheck(confirmed=True)
        inspect.assert_not_called()
        player.assert_not_called()

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_target_is_only_the_single_usb_sink_not_default_or_hdmi(self, inspect):
        source = [node(20, "alsa_output.pci-HDMI"), node(11, EDIFIER)]
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(source), ""
        )
        self.assertEqual(soundcheck.safe_usb_target(), EDIFIER)
        inspect.assert_called_once_with(("pw-dump",), timeout=5)
        for graph in (
            [node(20, "alsa_output.pci-HDMI")],
            [node(10, "alsa_output.usb-First"), node(11, "alsa_output.usb-Second")],
            [node(11, EDIFIER), node(12, EDIFIER)],
            [node(11, "alsa_output.usb-Evil bad target")],
        ):
            with self.subTest(graph=graph):
                inspect.return_value = subprocess.CompletedProcess(
                    ("pw-dump",), 0, json.dumps(graph), ""
                )
                with self.assertRaises(soundcheck.SoundcheckUnavailable):
                    soundcheck.safe_usb_target()

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_broken_graph_or_inspection_failure_never_picks_default(self, inspect):
        for result in (
            None,
            subprocess.CompletedProcess(("pw-dump",), 2, "", "SECRET-MAC"),
            subprocess.CompletedProcess(("pw-dump",), 0, "[invalid-json", ""),
            subprocess.CompletedProcess(("pw-dump",), 0, "[]", ""),
        ):
            inspect.return_value = result
            with self.subTest(result=str(result)[:30]):
                with self.assertRaises(soundcheck.SoundcheckUnavailable):
                    soundcheck.safe_usb_target()

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_confirmed_pattern_targets_only_usb_and_never_uses_shell(
            self, inspect, player, euid):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps([node(11, EDIFIER)]), ""
        )
        player.return_value = subprocess.CompletedProcess(("pw-cat",), 0, "", "")
        self.assertTrue(soundcheck.run_soundcheck(confirmed=True))
        player.assert_called_once()
        args, kwargs = player.call_args
        self.assertEqual(args[0][0], "pw-cat")
        self.assertIn("--target=" + EDIFIER, args[0])
        self.assertIn("--playback", args[0])
        self.assertIn("--raw", args[0])
        self.assertNotIn("--target=auto", args[0])
        self.assertNotIn("wpctl", args[0])
        self.assertTrue(kwargs["input"])
        self.assertEqual(kwargs["timeout"], 5)
        self.assertFalse(kwargs["shell"])
        self.assertFalse(kwargs["check"])
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(inspect.call_count, 1)

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_failed_player_or_timeout_is_not_reported_as_success(
            self, inspect, player, euid):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps([node(11, EDIFIER)]), ""
        )
        for outcome in (
            subprocess.CompletedProcess(("pw-cat",), 9, "", ""),
            OSError("SECRET-USB-IDENTIFIER"),
            subprocess.TimeoutExpired(cmd="pw-cat", timeout=5),
        ):
            player.side_effect = outcome if isinstance(outcome, BaseException) else None
            if not isinstance(outcome, BaseException):
                player.return_value = outcome
            with self.subTest(outcome=type(outcome).__name__):
                with self.assertRaises(soundcheck.SoundcheckUnavailable) as failure:
                    soundcheck.run_soundcheck(confirmed=True)
                self.assertNotIn("SECRET", str(failure.exception))


    @staticmethod
    def eq_graph(slot="music", *, connected=True, foreign=False,
                 duplicated=False, missing_sink=False, missing_usb=False):
        """Synthetic topology: exact virtual input + filter output -> USB."""
        target = "audiohub." + slot
        data = ([] if missing_usb else [node(11, EDIFIER)])
        if not missing_sink:
            data.append(node(31, target))
        data.append(node(32, target + ".output", "Stream/Output/Audio"))
        if duplicated:
            data.append(node(33, target + ".output", "Stream/Output/Audio"))
        if connected:
            data.append({"type": "PipeWire:Interface:Link",
                         "info": {"output-node-id": 32, "input-node-id": 11}})
        if foreign:
            data.extend([
                node(12, "alsa_output.pci-HDMI"),
                {"type": "PipeWire:Interface:Link",
                 "info": {"output-node-id": 32, "input-node-id": 12}},
            ])
        return data

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_each_virtual_eq_input_requires_one_direct_usb_link(self, inspect):
        for slot in ("music", "laptop", "tablet"):
            with self.subTest(slot=slot):
                inspect.return_value = subprocess.CompletedProcess(
                    ("pw-dump",), 0, json.dumps(self.eq_graph(slot)), ""
                )
                self.assertEqual(soundcheck.safe_input_target(slot), "audiohub." + slot)
        self.assertEqual(inspect.call_count, 3)
        for call in inspect.call_args_list:
            self.assertEqual(call.args[0], ("pw-dump",))
            self.assertEqual(call.kwargs, {"timeout": 5})

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_eq_input_refuses_missing_competing_or_ambiguous_output(self, inspect):
        configurations = (
            {"connected": False},
            {"foreign": True},
            {"duplicated": True},
            {"missing_sink": True},
            {"missing_usb": True},
        )
        for opts in configurations:
            with self.subTest(opts=opts):
                inspect.return_value = subprocess.CompletedProcess(
                    ("pw-dump",), 0, json.dumps(self.eq_graph(**opts)), ""
                )
                with self.assertRaises(soundcheck.SoundcheckUnavailable):
                    soundcheck.safe_input_target("music")

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_eq_input_rejects_unsafe_identifiers_and_broken_graph(self, inspect):
        for slot in (None, 1, True, "bluetooth", "music; cat /etc/passwd", ""):
            with self.subTest(slot=repr(slot)), self.assertRaises(
                    soundcheck.SoundcheckUnavailable):
                soundcheck.safe_input_target(slot)
        inspect.assert_not_called()
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, "[invalid-json", ""
        )
        with self.assertRaises(soundcheck.SoundcheckUnavailable):
            soundcheck.safe_input_target("tablet")

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_explicit_virtual_input_sends_quiet_stereo_to_only_selected_eq(
            self, inspect, player, euid):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(self.eq_graph("tablet")), ""
        )
        player.return_value = subprocess.CompletedProcess(("pw-cat",), 0, "", "")
        self.assertTrue(soundcheck.run_soundcheck(
            confirmed=True, through_input="tablet"
        ))
        player.assert_called_once()
        cmd, kwargs = player.call_args
        self.assertIn("--target=audiohub.tablet", cmd[0])
        self.assertNotIn("--target=" + EDIFIER, cmd[0])
        self.assertFalse(any("HDMI" in arg or "wpctl" in arg for arg in cmd[0]))
        self.assertLessEqual(max(abs(sample) for pair in
                             struct.iter_unpack("<hh", kwargs["input"])
                             for sample in pair), 656)
        self.assertEqual(kwargs["timeout"], soundcheck.MAX_PLAY_SECONDS)
        self.assertFalse(kwargs["shell"])

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_eq_check_missing_direct_link_cannot_start_player(self, inspect, player, euid):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(self.eq_graph(connected=False)), ""
        )
        with self.assertRaises(soundcheck.SoundcheckUnavailable):
            soundcheck.run_soundcheck(confirmed=True, through_input="music")
        player.assert_not_called()

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.run")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_explicit_input_requires_same_manual_confirmation(self, inspect, player, euid):
        with self.assertRaisesRegex(soundcheck.SoundcheckUnavailable, "confirmation"):
            soundcheck.run_soundcheck(confirmed=False, through_input="music")
        inspect.assert_not_called()
        player.assert_not_called()


    @staticmethod
    def mix_graph(*, disconnected=None, foreign=None,
                  missing=None, duplicated=None, malformed=False):
        nodes = [node(11, EDIFIER)]
        for i, slot in enumerate(("music", "laptop", "tablet")):
            target = "audiohub." + slot
            if slot != missing:
                nodes.append(node(30 + i, target))
            nodes.append(node(40 + i, target + ".output",
                              "Stream/Output/Audio"))
            if slot == duplicated:
                nodes.append(node(60 + i, target + ".output",
                                  "Stream/Output/Audio"))
            if slot != disconnected:
                nodes.append({"type": "PipeWire:Interface:Link",
                              "info": {"output-node-id": 40 + i,
                                       "input-node-id": 11}})
            if slot == foreign:
                nodes.append({"type": "PipeWire:Interface:Link",
                              "info": {"output-node-id": 40 + i,
                                       "input-node-id": 19}})
        if malformed:
            nodes.append({"type": "PipeWire:Interface:Link",
                          "info": {"output-node-id": "PRIVATE",
                                   "input-node-id": False}})
        return nodes

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_all_three_virtual_eq_inputs_require_one_consistent_graph(self, inspect):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(self.mix_graph()), ""
        )
        self.assertEqual(soundcheck.safe_three_input_targets(),
                         ("audiohub.music", "audiohub.laptop", "audiohub.tablet"))
        inspect.assert_called_once_with(("pw-dump",), timeout=5)

    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_mix_graph_refuses_silent_foreign_or_ambiguous_routes(self, inspect):
        scenarios = [
            self.mix_graph(disconnected="music"),
            self.mix_graph(disconnected="laptop"),
            self.mix_graph(disconnected="tablet"),
            self.mix_graph(foreign="laptop"),
            self.mix_graph(missing="tablet"),
            self.mix_graph(duplicated="music"),
            self.mix_graph(malformed=True),
            self.mix_graph() + [node(91, "alsa_output.usb-Second")],
        ]
        for graph in scenarios:
            with self.subTest(graph=repr(graph)[-90:]):
                inspect.return_value = subprocess.CompletedProcess(
                    ("pw-dump",), 0, json.dumps(graph), ""
                )
                with self.assertRaises(soundcheck.SoundcheckUnavailable):
                    soundcheck.safe_three_input_targets()
        for result in (
            None,
            subprocess.CompletedProcess(("pw-dump",), 1, "", "SECRET"),
            subprocess.CompletedProcess(("pw-dump",), 0, "[invalid", "")
        ):
            inspect.return_value = result
            with self.assertRaises(soundcheck.SoundcheckUnavailable):
                soundcheck.safe_three_input_targets()

    def test_three_input_patterns_have_distinct_markers_and_bounded_sum(self):
        signals = [soundcheck.three_input_pattern(slot)
                   for slot in ("music", "laptop", "tablet")]
        self.assertEqual(len(set(signals)), 3)
        self.assertEqual({len(pcm) for pcm in signals},
                         {soundcheck.MIX_FRAMES * 4})
        self.assertEqual(soundcheck.MIX_FRAMES, 2 * soundcheck.RATE)
        samples = [list(struct.iter_unpack("<hh", pcm)) for pcm in signals]
        peak = round(32767 * soundcheck.MIX_GAIN)
        for stereo in samples:
            self.assertEqual(stereo[0], (0, 0))
            self.assertEqual(stereo[-1], (0, 0))
            self.assertTrue(any(a != 0 for a, b in stereo))
            self.assertTrue(all(a == b for a, b in stereo))
            self.assertLessEqual(max(abs(a) for a, b in stereo), peak)
        # Even worst-case in-phase sum stays quieter than direct USB tone.
        self.assertLessEqual(3 * peak, round(32767 * soundcheck.GAIN))
        for value in (None, False, 2, "unknown", "music; rm -rf /"):
            with self.assertRaises(soundcheck.SoundcheckUnavailable):
                soundcheck.three_input_pattern(value)

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.Popen")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_three_mix_never_runs_without_explicit_consent(self, inspect, popen, uid):
        for confirm in (False, None, "yes", 1):
            with self.assertRaisesRegex(
                    soundcheck.SoundcheckUnavailable, "confirmation"):
                soundcheck.run_three_input_probe(confirmed=confirm)
        inspect.assert_not_called()
        popen.assert_not_called()

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=0)
    @mock.patch("audiohub.usb_soundcheck.subprocess.Popen")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_three_mix_refuses_root_without_any_graph_probe(self, inspect, popen, uid):
        with self.assertRaisesRegex(soundcheck.SoundcheckUnavailable, "unprivileged"):
            soundcheck.run_three_input_probe(confirmed=True)
        inspect.assert_not_called()
        popen.assert_not_called()

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.Popen")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_three_mix_opens_three_explicit_streams_concurrently(
            self, inspect, popen, uid):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(self.mix_graph()), ""
        )
        call_gate = Barrier(3)
        observed = []
        class Player:
            def __init__(self, args, kwargs):
                self.args = args
                self.kwargs = kwargs
                self.returncode = 0
                self.did_communicate = False
            def communicate(self, *, input, timeout):
                self.did_communicate = True
                observed.append((self.args[-3], input, timeout))
                call_gate.wait(timeout=2)  # Prove all streams write in parallel.
                return (b"", b"")
            def poll(self):
                return self.returncode
            def wait(self, timeout):
                return self.returncode
            def kill(self):
                raise AssertionError("Successful source must not be killed")
        players = []
        def start(args, **kwargs):
            player = Player(args, kwargs)
            players.append(player)
            return player
        popen.side_effect = start
        self.assertTrue(soundcheck.run_three_input_probe(confirmed=True))
        self.assertEqual(len(players), 3)
        self.assertEqual(len(observed), 3)
        inspect.assert_called_once_with(("pw-dump",), timeout=5)
        targets = ["--target=audiohub." + slot for slot in
                   ("music", "laptop", "tablet")]
        self.assertEqual([p.args[-3] for p in players], targets)
        for player in players:
            self.assertIn("--playback", player.args)
            self.assertNotIn("--target=auto", player.args)
            self.assertFalse(player.kwargs["shell"])
            self.assertEqual(player.kwargs["stdin"], subprocess.PIPE)
            self.assertEqual(player.kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(player.kwargs["stderr"], subprocess.DEVNULL)
            self.assertTrue(player.did_communicate)
        self.assertTrue(all(timeout == soundcheck.MAX_PLAY_SECONDS
                            for target, payload, timeout in observed))
        self.assertTrue(all(payload for target, payload, timeout in observed))

    @mock.patch("audiohub.usb_soundcheck.os.geteuid", return_value=1000)
    @mock.patch("audiohub.usb_soundcheck.subprocess.Popen")
    @mock.patch("audiohub.usb_soundcheck.bounded_command_output")
    def test_mix_stream_failure_cleans_up_and_never_claims_success(
            self, inspect, popen, uid):
        inspect.return_value = subprocess.CompletedProcess(
            ("pw-dump",), 0, json.dumps(self.mix_graph()), ""
        )
        class Player:
            def __init__(self, number):
                self.number = number
                self.returncode = 2 if number == 1 else 0
                self.waited = False
                self.killed = False
            def communicate(self, *, input, timeout):
                return (b"", b"")
            def poll(self):
                return self.returncode
            def wait(self, timeout):
                self.waited = True
                return self.returncode
            def kill(self):
                self.killed = True
        players = []
        def start(args, **kwargs):
            player = Player(len(players))
            players.append(player)
            return player
        popen.side_effect = start
        with self.assertRaisesRegex(soundcheck.SoundcheckUnavailable, "unavailable"):
            soundcheck.run_three_input_probe(confirmed=True)
        self.assertEqual(len(players), 3)
        self.assertTrue(all(p.waited for p in players))

    @mock.patch("audiohub.usb_soundcheck.run_soundcheck")
    @mock.patch("audiohub.usb_soundcheck.run_three_input_probe", return_value=True)
    def test_cli_three_input_probe_requires_both_flags(self, mix, direct):
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()):
            soundcheck.main(["--confirm-isolated-usb-test", "--three-input-mix-probe"])
        mix.assert_called_once_with(confirmed=True)
        direct.assert_not_called()
        with self.assertRaises(SystemExit) as ctx:
            soundcheck.main(["--three-input-mix-probe", "--through-input", "music"])
        self.assertEqual(ctx.exception.code, 2)

    @mock.patch("audiohub.usb_soundcheck.run_soundcheck")
    def test_cli_disabled_without_explicit_operator_option(self, run):
        run.side_effect = soundcheck.SoundcheckUnavailable("confirmation required")
        with self.assertRaises(SystemExit) as stopped:
            soundcheck.main([])
        self.assertEqual(stopped.exception.code, 2)
        run.assert_called_once_with(confirmed=False, through_input=None)


if __name__ == "__main__":
    unittest.main()
