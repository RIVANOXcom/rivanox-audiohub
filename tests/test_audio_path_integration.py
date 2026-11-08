"""AudioHub: audio path integration regression tests (no device assumed)."""
import json
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import os
import stat
import tempfile
from pathlib import Path
import sys
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import runtime, eq_setup, mixer_control
from audiohub.discovery import (
    pipewire_nodes, props, choose_usb_output, bluetooth_sources, virtual_sinks,
)

PHONE = "AA:BB:CC:DD:EE:FF"
PHONE2 = "00:11:22:33:44:55"
PHONE3 = "DD:EE:11:22:33:44"


def node(ident, name, media_class, **other):
    return {"type": "PipeWire:Interface:Node", "id": ident,
            "info": {"props": {"node.name": name, "media.class": media_class, **other}}}


def bt_node(ident=5, address=PHONE):
    return node(ident, "bluez_input." + address.replace(":", "_") + ".0",
                "Audio/Source", **{"api.bluez5.address": address})


def speaker(ident=11):
    return node(ident, "alsa_output.usb-Edifier_R600USB", "Audio/Sink")


def mixer_nodes():
    return [
        speaker(),
        bt_node(),
        node(21, "audiohub.music", "Audio/Sink"),
        node(22, "audiohub.tablet", "Audio/Sink"),
        node(23, "audiohub.laptop", "Audio/Sink"),
    ]


class Process:
    def __init__(self, alive=True):
        self.alive = alive
        self.terminated = False

    def poll(self):
        return None if self.alive else 1

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout=2):
        return 0

    def kill(self):
        self.alive = False


class AudioPathTests(unittest.TestCase):
    def supervisor(self, *, assignments=None):
        obj = runtime.Supervisor.__new__(runtime.Supervisor)
        obj.assignments = {PHONE: "music"} if assignments is None else assignments
        obj.loopbacks = {}
        obj.retry_state = {}
        obj.route_failures_total = 0
        obj.output_switch_failures = 0
        obj.settings = runtime.defaults()
        obj.last_default = None
        return obj

    def src(self, address=PHONE):
        return {"name": "bluez_input." + address.replace(":", "_") + ".0",
                "address": address}

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_explicit_capture_routes_to_eq_not_direct_usb_or_hdmi(self, launch):
        launch.return_value = Process()
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=100)
        argv = launch.call_args.args[0]
        self.assertEqual(argv, [
            "pw-loopback", "--name", "audiohub-music", "--channels", "2",
            "--capture", "bluez_input.AA_BB_CC_DD_EE_FF.0",
            "--playback", "audiohub.music",
        ])
        self.assertNotIn("alsa_output", " ".join(argv))
        self.assertNotIn("shell", str(launch.call_args.kwargs))

    def test_rejects_unsupported_or_injected_capture_targets(self):
        for name, channel in (
            ("bluez_input.A;touch /tmp/x", "music"),
            ("bluez_input.first", "unknown"),
            ("alsa_output.usb-Edifier", "music"),
            ("bluez_input." + "A"*200, "music"),
            (None, "music"),
        ):
            with self.subTest(name=str(name)[:25], channel=channel):
                with self.assertRaises(ValueError):
                    runtime.pipewire_loopback_args(name, channel)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_two_independent_bluetooth_sources_have_different_eq_sinks(self, launch):
        launch.side_effect = [Process(), Process()]
        s = self.supervisor(assignments={})
        s._route([self.src(PHONE), self.src(PHONE2)],
                 {"audiohub.music": 21, "audiohub.tablet": 22}, now=0)
        self.assertEqual(launch.call_count, 2)
        targets = [c.args[0][-1] for c in launch.call_args_list]
        self.assertEqual(set(targets), {"audiohub.music", "audiohub.tablet"})
        self.assertEqual(set(s.assignments.values()), {"music", "tablet"})

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_only_two_sources_admitted_even_when_three_present(self, launch):
        launch.side_effect = [Process(), Process(), Process()]
        s = self.supervisor(assignments={})
        s._route([self.src(PHONE), self.src(PHONE2), self.src(PHONE3)],
                 {"audiohub.music": 21, "audiohub.tablet": 22}, now=0)
        self.assertEqual(launch.call_count, 2)
        self.assertEqual(len(s.loopbacks), 2)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_no_route_without_verified_usb_sinks(self, launch):
        s = self.supervisor()
        s._route([self.src()], {}, now=0)
        launch.assert_not_called()

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_existing_healthy_route_is_not_restarted(self, launch):
        proc = Process()
        launch.return_value = proc
        s = self.supervisor()
        for second in (0, 5, 15, 30, 100):
            s._route([self.src()], {"audiohub.music": 21}, now=second)
        self.assertEqual(launch.call_count, 1)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_dead_process_retries_only_after_bounded_backoff(self, launch):
        first, second, third = Process(), Process(), Process()
        launch.side_effect = [first, second, third]
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=0)
        first.alive = False
        s._route([self.src()], {"audiohub.music": 21}, now=1)
        self.assertEqual(s.route_failures_total, 1)
        self.assertEqual(launch.call_count, 1)
        s._route([self.src()], {"audiohub.music": 21}, now=5)
        self.assertEqual(launch.call_count, 1)
        s._route([self.src()], {"audiohub.music": 21}, now=6)
        self.assertEqual(launch.call_count, 2)
        second.alive = False
        s._route([self.src()], {"audiohub.music": 21}, now=7)
        s._route([self.src()], {"audiohub.music": 21}, now=16)
        self.assertEqual(launch.call_count, 2)
        s._route([self.src()], {"audiohub.music": 21}, now=17)
        self.assertEqual(launch.call_count, 3)

    @mock.patch("audiohub.runtime.subprocess.Popen", side_effect=OSError("stream failed"))
    def test_repeated_spawn_failures_never_create_fork_bomb(self, launch):
        s = self.supervisor()
        for second in (0, 1, 5, 6, 7, 15, 16, 30, 31, 70, 71):
            s._route([self.src()], {"audiohub.music": 21}, now=second)
        self.assertLessEqual(launch.call_count, 5)
        self.assertEqual(s.route_failures_total, launch.call_count)
        self.assertLessEqual(max([x[1] for x in s.retry_state.values()]), 131)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_usb_unplug_terminates_routes_and_clears_failures(self, launch):
        proc = Process()
        launch.return_value = proc
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=0)
        s._route([self.src()], {}, now=1)
        self.assertTrue(proc.terminated)
        self.assertEqual(s.loopbacks, {})
        self.assertEqual(s.retry_state, {})

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_source_node_change_reconnects_without_old_target(self, launch):
        first, second = Process(), Process()
        launch.side_effect = [first, second]
        s = self.supervisor()
        s._route([self.src()], {"audiohub.music": 21}, now=0)
        changed = {"address": PHONE, "name": "bluez_input.AA_BB_CC_DD_EE_FF.1"}
        s._route([changed], {"audiohub.music": 21}, now=1)
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(first.terminated)


    def test_bt_auto_assignment_persist_error_leaves_no_in_memory_or_audio_route(self):
        s = self.supervisor(assignments={})
        with (mock.patch("audiohub.runtime.atomic_json",
                         side_effect=OSError("storage unavailable")) as saved,
              mock.patch("audiohub.runtime.subprocess.Popen") as launched):
            with self.assertRaisesRegex(OSError, "storage unavailable"):
                s._route([self.src(PHONE)], {"audiohub.music": 21}, now=0)
        self.assertEqual(s.assignments, {})
        self.assertEqual(s.loopbacks, {})
        saved.assert_called_once()
        launched.assert_not_called()

    def test_bt_auto_assignment_persists_on_retry_after_transient_write_error(self):
        s = self.supervisor(assignments={})
        with mock.patch("audiohub.runtime.atomic_json",
                        side_effect=[OSError("one failed write"), None]) as saved:
            with self.assertRaisesRegex(OSError, "one failed write"):
                s._assign([self.src(PHONE)])
            self.assertEqual(s.assignments, {})
            s._assign([self.src(PHONE)])
        self.assertEqual(s.assignments, {PHONE: "music"})
        self.assertEqual(saved.call_count, 2)
        self.assertEqual(saved.call_args_list[0].args[1], {PHONE: "music"})
        self.assertEqual(saved.call_args_list[1].args[1], {PHONE: "music"})

    def test_bt_auto_invalid_mapping_cleanup_retries_when_write_failed(self):
        original = {PHONE: "music", PHONE2: "music", "not-a-mac": "tablet"}
        s = self.supervisor(assignments=dict(original))
        with mock.patch("audiohub.runtime.atomic_json",
                        side_effect=[OSError("storage failed"), None]) as saved:
            with self.assertRaisesRegex(OSError, "storage failed"):
                s._assign([self.src(PHONE)])
            self.assertEqual(s.assignments, original)
            s._assign([self.src(PHONE)])
        self.assertEqual(s.assignments, {PHONE: "tablet", PHONE2: "music"})
        self.assertEqual(saved.call_count, 2)
        self.assertEqual(saved.call_args.args[1], s.assignments)

    def test_invalid_stored_assignments_do_not_grant_extra_channels(self):
        s = self.supervisor(assignments={
            PHONE: "music", PHONE2: "music", "non-mac": "tablet",
        })
        with mock.patch("audiohub.runtime.atomic_json") as write:
            s._assign([self.src(PHONE)])
        self.assertEqual(s.assignments, {PHONE2: "music", PHONE: "tablet"})
        write.assert_called_once()

    def test_capped_exponential_failure_delays(self):
        self.assertEqual([runtime.backoff_seconds(i) for i in range(1, 8)],
                         [5, 10, 20, 40, 60, 60, 60])

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_poll_routes_only_after_usb_default_succeeds(self, commands, launch, atomic):
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=0, stdout=json.dumps(mixer_nodes()) if args == ("pw-dump",) else ""
        )
        launch.return_value = Process()
        s = self.supervisor()
        s.poll()
        self.assertEqual(launch.call_count, 1)
        self.assertIn(("wpctl", "set-default", "11"),
                      [x.args for x in commands.call_args_list])
        output = atomic.call_args.args[1]
        self.assertTrue(output["usb_route_ready"])
        self.assertEqual(output["active_routes"], 1)
        self.assertEqual(output["route_start_failures"], 0)

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_failed_default_prevents_speaker_routes_and_volume(self, commands, launch, atomic):
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=1 if args[:2] == ("wpctl", "set-default") else 0,
            stdout=json.dumps(mixer_nodes()) if args == ("pw-dump",) else ""
        )
        s = self.supervisor()
        s.poll()
        launch.assert_not_called()
        output = atomic.call_args.args[1]
        self.assertTrue(output["usb_output"])
        self.assertFalse(output["usb_route_ready"])
        self.assertEqual(output["active_routes"], 0)
        self.assertEqual(output["output_switch_failures"], 1)
        self.assertNotIn(("wpctl", "set-volume", "11", "0.7"),
                         [x.args for x in commands.call_args_list])

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_no_usb_never_routes_to_hdmi_default(self, commands, launch, atomic):
        nodes = [
            node(15, "alsa_output.platform-hdmi", "Audio/Sink"), bt_node(),
            node(21, "audiohub.music", "Audio/Sink"),
        ]
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=0, stdout=json.dumps(nodes) if args == ("pw-dump",) else ""
        )
        s = self.supervisor()
        s.poll()
        launch.assert_not_called()
        self.assertFalse(atomic.call_args.args[1]["usb_route_ready"])
        self.assertNotIn("set-default", str(commands.call_args_list))

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_hot_unplug_stops_existing_route(self, commands, launch, atomic):
        current = [mixer_nodes(), [bt_node(), node(21, "audiohub.music", "Audio/Sink")]]
        def invoke(*args):
            if args == ("pw-dump",):
                return SimpleNamespace(returncode=0, stdout=json.dumps(current.pop(0)))
            return SimpleNamespace(returncode=0, stdout="")
        commands.side_effect = invoke
        proc = Process()
        launch.return_value = proc
        s = self.supervisor()
        s.poll()
        s.poll()
        self.assertTrue(proc.terminated)
        self.assertFalse(atomic.call_args.args[1]["usb_route_ready"])
        self.assertEqual(s.loopbacks, {})

    @mock.patch("audiohub.runtime.atomic_json")
    @mock.patch("audiohub.runtime.subprocess.Popen")
    @mock.patch("audiohub.runtime.run")
    def test_full_scale_three_source_gain_is_bounded_in_actual_usb_commands(
            self, commands, launch, atomic):
        from audiohub.mixer import CHANNELS
        s = self.supervisor()
        s.settings["master"] = 100
        for channel in CHANNELS:
            s.settings[channel].update({
                "volume": 100, "mute": False,
                "bass": 0, "mid": 0, "treble": 0,
            })
        commands.side_effect = lambda *args: SimpleNamespace(
            returncode=0, stdout=json.dumps(mixer_nodes()) if args == ("pw-dump",) else ""
        )
        launch.return_value = Process()
        with mock.patch("audiohub.runtime.read_json", side_effect=lambda path, fallback: fallback):
            s.poll()
        self.assertIn(
            ("wpctl", "set-volume", "11", str(1 / 3)),
            [call.args for call in commands.call_args_list],
        )
        data = atomic.call_args.args[1]
        self.assertEqual(data["effective_master_percent"], 33)
        self.assertTrue(data["usb_route_ready"])

    def test_malformed_pipewire_props_never_crash_discovery(self):
        values = [
            node(5, "bad", "Audio/Source"),
            {"type": "PipeWire:Interface:Node", "info": {"props": ["wrong"]}},
            {"type": "PipeWire:Interface:Node", "info": []},
            {"type": "PipeWire:Interface:Node", "info": {"props": None}},
        ]
        self.assertEqual(bluetooth_sources(values), [])
        self.assertEqual(virtual_sinks(values), {})
        self.assertIsNone(choose_usb_output(values))


    def test_reserved_bluetooth_macs_never_occupy_auto_slots_or_start_audio(self):
        for placeholder in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            with self.subTest(placeholder=placeholder):
                s = self.supervisor(assignments={placeholder: "music"})
                with (mock.patch("audiohub.runtime.atomic_json") as saved,
                      mock.patch("audiohub.runtime.subprocess.Popen") as started):
                    s._route([self.src(placeholder)],
                             {"audiohub.music": 21}, now=0)
                self.assertEqual(s.assignments, {})
                self.assertEqual(s.loopbacks, {})
                saved.assert_called_once()
                started.assert_not_called()

    def test_rejected_placeholder_does_not_block_valid_bluetooth_auto_route(self):
        s = self.supervisor(assignments={"00:00:00:00:00:00": "music"})
        with (mock.patch("audiohub.runtime.atomic_json") as saved,
              mock.patch("audiohub.runtime.subprocess.Popen",
                         return_value=Process()) as started):
            s._route([self.src("00:00:00:00:00:00"), self.src(PHONE)],
                     {"audiohub.music": 21}, now=0)
        self.assertEqual(s.assignments, {PHONE: "music"})
        self.assertEqual(len(s.loopbacks), 1)
        saved.assert_called_once()
        started.assert_called_once()

    def test_bluetooth_addresses_are_valid_and_ambiguous_mac_fails_closed(self):
        # Two candidate nodes for one MAC are NOT a reliable source;
        # no arbitrary "first valid" capture is routed. Other phones remain.
        found = bluetooth_sources([bt_node(5), bt_node(6), bt_node(7, PHONE2)])
        self.assertEqual(len(found), 1)
        self.assertEqual({x["address"] for x in found}, {PHONE2})

    def test_mismatched_bt_name_address_is_rejected(self):
        mismatch = bt_node()
        mismatch["info"]["props"]["api.bluez5.address"] = PHONE2
        self.assertEqual(bluetooth_sources([mismatch]), [])

    def test_bad_id_node_is_not_routed(self):
        values = [bt_node("5"), node(True, "audiohub.music", "Audio/Sink")]
        self.assertEqual(bluetooth_sources(values), [])
        self.assertEqual(virtual_sinks(values), {})

    def test_only_real_eq_channels_are_discovered(self):
        nodes = [
            node(1, "audiohub.music", "Audio/Sink"),
            node(2, "audiohub.hijack", "Audio/Sink"),
            node(3, "audiohub.music.output", "Audio/Sink"),
        ]
        self.assertEqual(virtual_sinks(nodes), {"audiohub.music": 1})

    def test_ambiguous_usb_hardware_is_not_selected(self):
        self.assertIsNone(choose_usb_output([
            node(1, "alsa_output.usb-card1", "Audio/Sink"),
            node(2, "alsa_output.usb-card2", "Audio/Sink"),
        ]))
        self.assertIsNone(choose_usb_output([
            node(1, "alsa_output.usb-Edifier1", "Audio/Sink"),
            node(2, "alsa_output.usb-Edifier2", "Audio/Sink"),
        ]))

    def test_single_generic_usb_sink_is_allowed_without_hdmi_fallback(self):
        self.assertEqual(choose_usb_output([
            node(3, "alsa_output.platform-hdmi", "Audio/Sink"),
            node(5, "alsa_output.usb-Generic_USB_Audio", "Audio/Sink"),
        ])["id"], 5)

    def test_wireplumber_uses_input_role_to_prevent_bypassing_eq(self):
        config = (ROOT / "image/stage-audiohub/01-install/files/wireplumber"
                  / "90-audiohub.conf").read_text()
        self.assertIn("bluez5.roles = [ a2dp_sink ]", config)
        self.assertIn('node.name = "~bluez_input.*"', config)
        self.assertIn("bluez5.media-source-role = input", config)
        self.assertIn("monitor.bluez.rules = [", config)



class EqSetupFileSafetyTests(unittest.TestCase):
    """Exercise real local file writes without an actual Pi or PipeWire."""

    def home(self, base):
        home = Path(base) / "home"
        home.mkdir(mode=0o700)
        return home

    def config(self, home):
        return home / ".config" / "pipewire" / "pipewire.conf.d" / eq_setup.EQ_FILE

    def test_staged_eq_comparison_reports_missing_without_creating_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"bass": 4}},
                                 path=settings, confirmed=True)
            saved = settings.read_bytes()
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                with redirect_stdout(StringIO()) as output:
                    eq_setup.main(["--compare-staged"])
                result = json.loads(output.getvalue())
                self.assertEqual(result["mode"], "read-only-saved-vs-staged-eq")
                self.assertEqual(result["staging_status"], "missing")
                self.assertIsNone(result["staged_configuration_sha256"])
                self.assertFalse(result["configuration_staged_for_saved_eq"])
                self.assertFalse(result["settings_written"])
                self.assertFalse(result["configuration_written"])
                self.assertFalse(result["pipewire_restarted"])
                self.assertFalse(result["live_eq_applied"])
                self.assertFalse(result["hardware_audio_verified"])
                self.assertFalse(self.config(home).parent.exists())
                self.assertEqual(settings.read_bytes(), saved)

    def test_staged_eq_comparison_matches_then_shows_saved_curve_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({
                "music": {"bass": -5, "mid": 2, "treble": 1},
                "tablet": {"bass": 4},
            }, path=settings, confirmed=True)
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                plan = eq_setup.preview_saved_eq()
                staged = eq_setup.stage_saved_eq(plan["revision"], confirmed=True)
                target = self.config(home)
                prior_stage = target.read_bytes()
                prior_settings = settings.read_bytes()
                self.assertEqual(staged["configuration_sha256"],
                                 plan["configuration_sha256"])
                with redirect_stdout(StringIO()) as output:
                    eq_setup.main(["--compare-staged"])
                result = json.loads(output.getvalue())
                self.assertEqual(result["staging_status"], "matches_saved")
                self.assertTrue(result["configuration_staged_for_saved_eq"])
                self.assertEqual(result["saved_configuration_sha256"],
                                 result["staged_configuration_sha256"])
                self.assertEqual(result["equalizer"]["music"],
                                 {"bass": -5, "mid": 2, "treble": 1})
                self.assertFalse(result["live_eq_applied"])
                self.assertFalse(result["pipewire_restarted"])
                self.assertEqual(target.read_bytes(), prior_stage)
                self.assertEqual(settings.read_bytes(), prior_settings)

                mixer_control.change({"music": {"treble": 3}},
                                     path=settings, confirmed=True)
                new_settings = settings.read_bytes()
                with redirect_stdout(StringIO()) as output:
                    eq_setup.main(["--compare-staged"])
                result = json.loads(output.getvalue())
                self.assertEqual(result["staging_status"], "differs_from_saved")
                self.assertFalse(result["configuration_staged_for_saved_eq"])
                self.assertNotEqual(result["saved_configuration_sha256"],
                                    result["staged_configuration_sha256"])
                self.assertEqual(target.read_bytes(), prior_stage)
                self.assertEqual(settings.read_bytes(), new_settings)

    def test_staged_eq_comparison_never_trusts_symlink_public_or_hardlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"bass": 3}},
                                 path=settings, confirmed=True)
            target = self.config(home)
            target.parent.mkdir(parents=True, mode=0o700)
            victim = home / "private-note"
            victim.write_text("private device identity")
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                target.symlink_to(victim)
                for candidate in ("symlink", "public", "hardlink"):
                    with self.subTest(candidate=candidate):
                        if candidate == "public":
                            target.unlink()
                            target.write_text("untrusted staged content")
                            target.chmod(0o644)
                        elif candidate == "hardlink":
                            target.unlink()
                            os.link(victim, target)
                        with redirect_stdout(StringIO()) as output:
                            eq_setup.main(["--compare-staged"])
                        result = json.loads(output.getvalue())
                        self.assertEqual(result["staging_status"], "unavailable")
                        self.assertIsNone(result["staged_configuration_sha256"])
                        self.assertFalse(result["configuration_staged_for_saved_eq"])
                        self.assertNotIn("private device identity", output.getvalue())
                self.assertEqual(victim.read_text(), "private device identity")
                target.unlink()
                target.parent.chmod(0o755)
                with redirect_stdout(StringIO()) as output:
                    eq_setup.main(["--compare-staged"])
                result = json.loads(output.getvalue())
                self.assertEqual(result["staging_status"], "unavailable")
                self.assertFalse(result["configuration_staged_for_saved_eq"])

    def test_staged_eq_comparison_refuses_mixer_race_and_write_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"bass": 4}},
                                 path=settings, confirmed=True)
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                for args in (
                    ["--compare-staged", "--confirm-local-eq-stage"],
                    ["--compare-staged", "--if-preview-revision", "v1-" + "a"*64],
                    ["--compare-staged", "--stage-saved"],
                    ["--compare-staged", "--preview-saved"],
                ):
                    with (self.subTest(args=args),
                          redirect_stdout(StringIO()) as out,
                          redirect_stderr(StringIO())):
                        with self.assertRaises(SystemExit) as exc:
                            eq_setup.main(args)
                        self.assertEqual(exc.exception.code, 2)
                        self.assertEqual(out.getvalue(), "")
                original_digest = eq_setup._staged_eq_digest
                def interleaving_mixer_change():
                    mixer_control.change({"music": {"bass": 5}},
                                         path=settings, confirmed=True)
                    return original_digest()
                with (mock.patch.object(eq_setup, "_staged_eq_digest",
                                        side_effect=interleaving_mixer_change),
                      redirect_stdout(StringIO()) as out,
                      redirect_stderr(StringIO()) as err):
                    with self.assertRaises(SystemExit) as failed:
                        eq_setup.main(["--compare-staged"])
                self.assertEqual(failed.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertNotIn(str(settings), err.getvalue())
                self.assertFalse(self.config(home).parent.exists())

    def test_eq_text_explains_matching_and_differing_stages_not_live_sound(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({
                "music": {"bass": -3, "mid": 2, "treble": 1},
                "laptop": {"bass": 4, "mute": True},
            }, path=settings, confirmed=True)
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                plan = eq_setup.preview_saved_eq()
                eq_setup.stage_saved_eq(plan["revision"], confirmed=True)
                stage = self.config(home).read_bytes()
                saved = settings.read_bytes()
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "text"])
                report = out.getvalue()
                self.assertIn("Stage: matches saved", report)
                self.assertIn("music: bass -3 dB, mid +2 dB, treble +1 dB",
                              report)
                self.assertIn("not prove PipeWire loaded", report)
                self.assertIn("no audible output verified", report)
                self.assertNotIn(str(home), report)
                self.assertEqual(self.config(home).read_bytes(), stage)
                self.assertEqual(settings.read_bytes(), saved)

                mixer_control.change(
                    {"music": {"treble": -2}}, path=settings, confirmed=True)
                saved_new = settings.read_bytes()
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--format", "text", "--compare-staged"])
                report = out.getvalue()
                self.assertIn("Stage: differs from saved", report)
                self.assertIn("music: bass -3 dB, mid +2 dB, treble -2 dB",
                              report)
                self.assertIn("--preview-saved", report)
                self.assertIn("separate local consent", report)
                self.assertEqual(self.config(home).read_bytes(), stage)
                self.assertEqual(settings.read_bytes(), saved_new)

    def test_eq_text_missing_and_unsafe_stage_guide_without_touching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"bass": 5}},
                                 path=settings, confirmed=True)
            before = settings.read_bytes()
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "text"])
                text = out.getvalue()
                self.assertIn("Stage: missing", text)
                self.assertIn("--preview-saved", text)
                self.assertIn("no PipeWire restart", text)
                self.assertFalse(self.config(home).parent.exists())
                target = self.config(home)
                target.parent.mkdir(parents=True, mode=0o700)
                private_note = home / "private-note"
                private_note.write_text("secret device address")
                target.symlink_to(private_note)
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "text"])
                text = out.getvalue()
                self.assertIn("Stage: unavailable", text)
                self.assertIn("No automatic repair", text)
                self.assertNotIn("secret device address", text)
                self.assertEqual(private_note.read_text(),
                                 "secret device address")
                self.assertEqual(settings.read_bytes(), before)

    def test_eq_text_format_is_comparison_only_and_default_json_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"tablet": {"treble": 2}},
                                 path=settings, confirmed=True)
            before = settings.read_bytes()
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                for args in (
                    ["--format", "text"],
                    ["--preview-saved", "--format", "text"],
                    ["--stage-saved", "--format", "text"],
                    ["--compare-staged", "--format", "text",
                     "--confirm-local-eq-stage"],
                    ["--compare-staged", "--format", "text",
                     "--if-preview-revision", "v1-" + "a" * 64],
                    ["--compare-staged", "--format", "html"],
                ):
                    with (self.subTest(args=args),
                          redirect_stdout(StringIO()) as out,
                          redirect_stderr(StringIO())):
                        with self.assertRaises(SystemExit) as failed:
                            eq_setup.main(args)
                        self.assertEqual(failed.exception.code, 2)
                        self.assertEqual(out.getvalue(), "")
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged"])
                default_json = json.loads(out.getvalue())
                self.assertEqual(default_json["staging_status"], "missing")
                self.assertFalse(default_json["settings_written"])
                self.assertFalse(default_json["live_eq_applied"])
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "json"])
                explicit_json = json.loads(out.getvalue())
                self.assertEqual(explicit_json, default_json)
                self.assertFalse(self.config(home).parent.exists())
                self.assertEqual(settings.read_bytes(), before)

    def test_eq_overview_identifies_exact_fixed_profile_shapes_and_custom_curve(self):
        from audiohub import mixer_control
        for name, expected in (
                ("warm", {"bass": 3, "mid": 0, "treble": -1}),
                ("voice", {"bass": -2, "mid": 3, "treble": 1}),
                ("detail", {"bass": 0, "mid": 1, "treble": 3})):
            with self.subTest(name=name):
                self.assertEqual(
                    mixer_control.eq_preset_patch("music", name)["music"],
                    expected)
                self.assertEqual(eq_setup._saved_eq_profile_shape(expected),
                                 name.capitalize())
        self.assertEqual(eq_setup._saved_eq_profile_shape(
            {"bass": 0, "mid": 0, "treble": 0}), "Flat")
        self.assertEqual(eq_setup._saved_eq_profile_shape(
            {"bass": 3, "mid": 0, "treble": 0}), "Custom")
        for curve in (
                None, [], {}, {"bass": True, "mid": 0, "treble": 0},
                {"bass": "3", "mid": 0, "treble": 0},
                {"bass": 13, "mid": 0, "treble": 0},
                {"bass": 0, "mid": 0, "treble": 0, "secret": 1},
                {"bass": 0, "mid": 0},
        ):
            with self.subTest(invalid=curve):
                with self.assertRaises(ValueError):
                    eq_setup._saved_eq_profile_shape(curve)

    def test_eq_overview_real_stage_and_saved_curves_readonly_all_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({
                "master": 31,
                "music": {"bass": 3, "mid": 0, "treble": -1},
                "laptop": {"bass": -2, "mid": 3, "treble": 1},
                "tablet": {"bass": 1, "mid": 4, "treble": -2},
            }, path=settings, confirmed=True)
            saved_before = settings.read_bytes()
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "overview"])
                missing = out.getvalue()
                self.assertIn("ON-DISK STAGE: MISSING", missing)
                self.assertIn("music   Warm", missing)
                self.assertIn("laptop  Voice", missing)
                self.assertIn("tablet  Custom", missing)
                self.assertIn("bass +3 dB", missing)
                self.assertIn("treble -1 dB", missing)
                self.assertIn("NOT VERIFIED: current PipeWire load", missing)
                self.assertNotIn(str(home), missing)
                self.assertNotIn("1363", missing)
                self.assertFalse(self.config(home).parent.exists())
                self.assertEqual(settings.read_bytes(), saved_before)

                plan = eq_setup.preview_saved_eq()
                eq_setup.stage_saved_eq(plan["revision"], confirmed=True)
                stage = self.config(home).read_bytes()
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--format", "overview", "--compare-staged"])
                matched = out.getvalue()
                self.assertIn("ON-DISK STAGE: MATCHES", matched)
                self.assertIn("entire staged file digest", matched)
                self.assertIn("ALL three inputs as one file", matched)
                self.assertIn("STILL UNVERIFIED", matched)
                self.assertEqual(self.config(home).read_bytes(), stage)
                self.assertEqual(settings.read_bytes(), saved_before)

                mixer_control.change({"tablet": {"treble": -1}},
                                     path=settings, confirmed=True)
                new_settings = settings.read_bytes()
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "overview"])
                differing = out.getvalue()
                self.assertIn("ON-DISK STAGE: DIFFERS", differing)
                self.assertIn("--preview-saved", differing)
                self.assertIn("Custom", differing)
                self.assertEqual(self.config(home).read_bytes(), stage)
                self.assertEqual(settings.read_bytes(), new_settings)

                target = self.config(home)
                target.unlink()
                other = home / "private-note"
                other.write_text("SECRET DEVICE IDENTIFIER")
                target.symlink_to(other)
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "overview"])
                unsafe = out.getvalue()
                self.assertIn("ON-DISK STAGE: UNAVAILABLE", unsafe)
                self.assertIn("No automatic repair", unsafe)
                self.assertNotIn("SECRET DEVICE IDENTIFIER", unsafe)
                self.assertNotIn(str(home), unsafe)
                self.assertEqual(other.read_text(), "SECRET DEVICE IDENTIFIER")
                self.assertEqual(settings.read_bytes(), new_settings)

    def test_eq_overview_format_never_mutates_and_existing_output_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"bass": 3, "treble": -1}},
                                 path=settings, confirmed=True)
            raw = settings.read_bytes()
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged"])
                unchanged = json.loads(out.getvalue())
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "json"])
                self.assertEqual(json.loads(out.getvalue()), unchanged)
                self.assertNotIn("profile", unchanged)
                with redirect_stdout(StringIO()) as out:
                    eq_setup.main(["--compare-staged", "--format", "text"])
                self.assertIn("Saved requests", out.getvalue())
                for args in (
                    ["--format", "overview"],
                    ["--preview-saved", "--format", "overview"],
                    ["--stage-saved", "--format", "overview"],
                    ["--compare-staged", "--format", "overview",
                     "--confirm-local-eq-stage"],
                    ["--compare-staged", "--format", "overview",
                     "--if-preview-revision", "v1-" + "a" * 64],
                    ["--compare-staged", "--format", "OVERVIEW"],
                ):
                    with (self.subTest(args=args),
                          redirect_stdout(StringIO()) as out,
                          redirect_stderr(StringIO())):
                        with self.assertRaises(SystemExit) as failed:
                            eq_setup.main(args)
                        self.assertEqual(failed.exception.code, 2)
                        self.assertEqual(out.getvalue(), "")
                self.assertFalse(self.config(home).parent.exists())
                self.assertEqual(settings.read_bytes(), raw)

    def test_saved_eq_preview_and_operator_guarded_staging_no_live_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({
                "master": 32, "music": {"bass": 8, "mid": -2},
                "tablet": {"treble": -5}, "laptop": {"volume": 27}
            }, path=settings, confirmed=True)
            original = settings.read_bytes()
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                eq_setup.main()
                target = self.config(home)
                default_eq = target.read_bytes()
                self.assertNotIn(b"gain = 8", default_eq)
                with redirect_stdout(StringIO()) as output:
                    eq_setup.main(["--preview-saved"])
                plan = json.loads(output.getvalue())
                self.assertEqual(plan["mode"], "eq-preview-only")
                self.assertEqual(plan["equalizer"]["music"],
                                 {"bass": 8, "mid": -2, "treble": 0})
                self.assertEqual(plan["equalizer"]["tablet"]["treble"], -5)
                self.assertFalse(plan["configuration_staged"])
                self.assertFalse(plan["pipewire_restarted"])
                self.assertFalse(plan["live_eq_applied"])
                self.assertFalse(plan["hardware_audio_verified"])
                self.assertEqual(target.read_bytes(), default_eq)
                self.assertEqual(settings.read_bytes(), original)
                with redirect_stdout(StringIO()) as output:
                    eq_setup.main(["--stage-saved", "--confirm-local-eq-stage",
                                   "--if-preview-revision", plan["revision"]])
                staged = json.loads(output.getvalue())
                self.assertEqual(staged["mode"], "eq-staged-for-manual-pipewire-restart")
                self.assertTrue(staged["configuration_staged"])
                self.assertFalse(staged["pipewire_restarted"])
                self.assertFalse(staged["live_eq_applied"])
                self.assertEqual(staged["revision"], plan["revision"])
                self.assertEqual(staged["configuration_sha256"],
                                 plan["configuration_sha256"])
                payload = target.read_bytes()
                self.assertIn(b"gain = 8", payload)
                self.assertIn(b"gain = -2", payload)
                self.assertIn(b"gain = -5", payload)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(settings.read_bytes(), original)
                self.assertEqual(len(list(target.parent.iterdir())), 1)

    def test_saved_eq_staging_refuses_stale_or_unconfirmed_without_replacing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"bass": 3}},
                                 path=settings, confirmed=True)
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                eq_setup.main()
                target = self.config(home)
                prior = target.read_bytes()
                preview = eq_setup.preview_saved_eq()
                for args in (
                    ["--stage-saved"],
                    ["--stage-saved", "--if-preview-revision", preview["revision"]],
                    ["--stage-saved", "--confirm-local-eq-stage"],
                    ["--preview-saved", "--confirm-local-eq-stage"],
                    ["--preview-saved", "--if-preview-revision", preview["revision"]],
                    ["--if-preview-revision", preview["revision"]],
                    ["--confirm-local-eq-stage"],
                ):
                    with (self.subTest(args=args),
                          redirect_stdout(StringIO()) as out,
                          redirect_stderr(StringIO())):
                        with self.assertRaises(SystemExit) as exc:
                            eq_setup.main(args)
                        self.assertEqual(exc.exception.code, 2)
                        self.assertEqual(out.getvalue(), "")
                        self.assertEqual(target.read_bytes(), prior)
                mixer_control.change({"master": 34}, path=settings,
                                     confirmed=True)
                mixer_control.change({"master": 70}, path=settings,
                                     confirmed=True)
                with (redirect_stdout(StringIO()) as out,
                      redirect_stderr(StringIO()) as err):
                    with self.assertRaises(SystemExit) as exc:
                        eq_setup.main([
                            "--stage-saved", "--confirm-local-eq-stage",
                            "--if-preview-revision", preview["revision"],
                        ])
                self.assertEqual(exc.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(target.read_bytes(), prior)
                self.assertNotIn("gain = 3", target.read_text())
                self.assertNotIn(str(settings), err.getvalue())

    def test_saved_eq_staging_refuses_symlinked_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            settings = home / "private" / "settings.json"
            mixer_control.change({"music": {"mid": 6}},
                                 path=settings, confirmed=True)
            target = self.config(home)
            target.parent.mkdir(parents=True, mode=0o700)
            victim = home / "protected.txt"
            victim.write_text("DO NOT OVERWRITE")
            target.symlink_to(victim)
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "SETTINGS", settings)):
                preview = eq_setup.preview_saved_eq()
                with (redirect_stdout(StringIO()) as out,
                      redirect_stderr(StringIO())):
                    with self.assertRaises(SystemExit) as exc:
                        eq_setup.main([
                            "--stage-saved", "--confirm-local-eq-stage",
                            "--if-preview-revision", preview["revision"],
                        ])
                self.assertEqual(exc.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(victim.read_text(), "DO NOT OVERWRITE")
                self.assertTrue(target.is_symlink())

    def test_eq_config_creation_and_atomic_repeat_private_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            with mock.patch.object(Path, "home", return_value=home):
                eq_setup.main()
                target = self.config(home)
                self.assertTrue(target.is_file())
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
                content = target.read_text()
                self.assertIn('node.name = "audiohub.music"', content)
                self.assertIn('node.name = "audiohub.laptop"', content)
                self.assertIn('node.name = "audiohub.tablet"', content)
                eq_setup.main()
                self.assertEqual(target.read_text(), content)
                self.assertEqual(list(target.parent.iterdir()), [target])


    def test_eq_setup_tolerates_a_concurrent_private_directory_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            original_mkdir = os.mkdir
            collided = []

            def other_instance_creates_dir(path, mode=0o777, *, dir_fd=None):
                if dir_fd is not None and not collided:
                    original_mkdir(path, mode=mode, dir_fd=dir_fd)
                    collided.append(path)
                    raise FileExistsError("created concurrently")
                return original_mkdir(path, mode=mode, dir_fd=dir_fd)

            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup.os, "mkdir",
                                    side_effect=other_instance_creates_dir)):
                eq_setup.main()
            self.assertEqual(len(collided), 1)
            self.assertTrue(self.config(home).is_file())

    def test_eq_setup_raced_symlink_directory_stays_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            outside = Path(tmp) / "not-a-pipewire-config"
            outside.mkdir(mode=0o700)

            def another_process_inserts_symlink(path, mode=0o777, *, dir_fd=None):
                os.symlink(str(outside), path, dir_fd=dir_fd)
                raise FileExistsError("symlink created concurrently")

            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup.os, "mkdir",
                                    side_effect=another_process_inserts_symlink)):
                with self.assertRaises(OSError):
                    eq_setup.main()
            self.assertEqual(list(outside.iterdir()), [])

    def test_eq_failed_write_preserves_old_eq_file_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            with mock.patch.object(Path, "home", return_value=home):
                eq_setup.main()
                path = self.config(home)
                prior = path.read_bytes()
                with mock.patch.object(eq_setup.os, "write",
                                       side_effect=OSError("EQ write interrupted")):
                    with self.assertRaisesRegex(OSError, "EQ write interrupted"):
                        eq_setup.main()
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_eq_cleanup_failure_never_masks_write_error_or_leaks_dir_fd(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            opened = []
            original_open = eq_setup._safe_eq_parent_fd

            def track_dir_fd(target):
                fd = original_open(target)
                opened.append(fd)
                return fd

            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "_safe_eq_parent_fd",
                                    side_effect=track_dir_fd),
                  mock.patch.object(eq_setup.os, "write",
                                    side_effect=OSError("original write failure")),
                  mock.patch.object(eq_setup.os, "unlink",
                                    side_effect=PermissionError("cleanup failed"))):
                with self.assertRaisesRegex(OSError, "original write failure"):
                    eq_setup.main()
            self.assertEqual(len(opened), 1)
            with self.assertRaises(OSError):
                os.fstat(opened[0])

    def test_eq_setup_refuses_final_symlink_without_clobbering_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            target = self.config(home)
            target.parent.mkdir(parents=True, mode=0o700)
            secret = home / "private-settings.json"
            secret.write_text("must stay intact")
            target.symlink_to(secret)
            with mock.patch.object(Path, "home", return_value=home):
                with self.assertRaises(OSError):
                    eq_setup.main()
            self.assertEqual(secret.read_text(), "must stay intact")
            self.assertTrue(target.is_symlink())

    def test_eq_setup_refuses_symlinked_directory_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            outside = Path(tmp) / "other-directory"
            outside.mkdir(mode=0o700)
            (home / ".config").symlink_to(outside, target_is_directory=True)
            with mock.patch.object(Path, "home", return_value=home):
                with self.assertRaises(OSError):
                    eq_setup.main()
            self.assertEqual(list(outside.iterdir()), [])

    def test_eq_setup_refuses_hardlinked_or_public_destination(self):
        for kind in ("hardlink", "public"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                home = self.home(tmp)
                target = self.config(home)
                target.parent.mkdir(parents=True, mode=0o700)
                original = home / "protected"
                original.write_text("preserve me")
                if kind == "hardlink":
                    os.link(original, target)
                else:
                    target.write_text("preserve me")
                    target.chmod(0o644)
                with mock.patch.object(Path, "home", return_value=home):
                    with self.assertRaises(PermissionError):
                        eq_setup.main()
                self.assertEqual(original.read_text(), "preserve me")
                self.assertEqual(target.read_text(), "preserve me")

    def test_eq_setup_rejects_excessive_generated_config_before_file_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self.home(tmp)
            with (mock.patch.object(Path, "home", return_value=home),
                  mock.patch.object(eq_setup, "pipewire_filter_config",
                                    return_value="X" * (eq_setup.MAX_EQ_CONFIG_BYTES + 1))):
                with self.assertRaises(ValueError):
                    eq_setup.main()
            self.assertFalse(self.config(home).exists())

if __name__ == "__main__":
    unittest.main()
