"""Offline AudioHub mixer controls: private atomic file only, never actual audio."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import mixer_control
from audiohub.mixer import defaults, requested_mix_controls
from audiohub import runtime


class LocalMixerControlsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.settings = self.root / "audiohub" / "settings.json"

    def test_read_only_show_is_default_and_creates_nothing(self):
        current = mixer_control.show(path=self.settings)
        self.assertEqual(current, defaults())
        self.assertFalse(self.settings.parent.exists())

    def test_explicit_change_writes_private_atomic_file_and_keeps_other_channels(self):
        self.assertEqual(mixer_control.change({"master": 35}, path=self.settings,
                                              confirmed=True)["master"], 35)
        self.assertEqual(mixer_control.change(
            {"music": {"volume": 12}}, path=self.settings, confirmed=True
        )["music"]["volume"], 12)
        latest = mixer_control.change({"tablet": {"mute": True}},
                                      path=self.settings, confirmed=True)
        self.assertEqual(latest["master"], 35)
        self.assertEqual(latest["music"]["volume"], 12)
        self.assertTrue(latest["tablet"]["mute"])
        self.assertFalse(latest["laptop"]["mute"])
        self.assertEqual(mixer_control.show(path=self.settings), latest)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.settings.parent.stat().st_mode), 0o700)
        self.assertEqual(self.settings.stat().st_nlink, 1)
        self.assertEqual(stat.S_IMODE(
            (self.settings.parent / mixer_control.LOCK_NAME).stat().st_mode
        ), 0o600)
        self.assertEqual(set(self.settings.parent.iterdir()),
                         {self.settings, self.settings.parent / mixer_control.LOCK_NAME})

    def test_no_confirmation_or_root_cannot_create_files(self):
        with self.assertRaisesRegex(mixer_control.MixerControlUnavailable, "confirmation"):
            mixer_control.change({"master": 80}, path=self.settings)
        with mock.patch("audiohub.mixer_control.os.geteuid", return_value=0):
            with self.assertRaisesRegex(mixer_control.MixerControlUnavailable,
                                        "unprivileged"):
                mixer_control.change({"master": 80}, path=self.settings, confirmed=True)
            with self.assertRaisesRegex(mixer_control.MixerControlUnavailable,
                                        "unprivileged"):
                mixer_control.show(path=self.settings)
        self.assertFalse(self.settings.parent.exists())

    def test_invalid_value_cannot_replace_valid_setting(self):
        mixer_control.change({"master": 57}, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        for patch in ({"master": -1}, {"master": 101}, {"master": True},
                      {"music": {"volume": 200}}, {"tablet": {"mute": "yes"}},
                      {"wifi_password": "PRIVATE-SECRET"},
                      {"music": {"bass": float("nan")}}):
            with self.subTest(patch=repr(patch)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change(patch, path=self.settings, confirmed=True)
                self.assertEqual(self.settings.read_bytes(), before)
        self.assertNotIn(b"PRIVATE-SECRET", before)

    def test_corrupt_or_unreviewed_state_never_replaced_by_defaults(self):
        self.settings.parent.mkdir(mode=0o700)
        for payload in (
            b"{", b'{"master": 25, "master": 80}',
            b'{"master": 31, "unexpected": "SECRET"}',
            b'{"master": 80, "music": {"mute": "heard"}}',
        ):
            with self.subTest(payload=payload[:40]):
                self.settings.write_bytes(payload)
                self.settings.chmod(0o600)
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
                self.assertEqual(self.settings.read_bytes(), payload)

    def test_untrusted_symlinks_and_permissions_do_not_destroy_target(self):
        other = self.root / "protected.json"
        other.write_text("PRIVATE-OWNER")
        self.settings.parent.mkdir(mode=0o700)
        self.settings.symlink_to(other)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"master": 25}, path=self.settings, confirmed=True)
        self.assertEqual(other.read_text(), "PRIVATE-OWNER")
        self.settings.unlink()
        self.settings.write_text(json.dumps(defaults()))
        self.settings.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"master": 25}, path=self.settings, confirmed=True)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o644)

    def test_raced_lock_symlink_is_rejected_before_writing(self):
        self.settings.parent.mkdir(mode=0o700)
        other = self.root / "outside"
        other.write_text("PRIVATE-PROTECTED")
        (self.settings.parent / mixer_control.LOCK_NAME).symlink_to(other)
        with self.assertRaises(OSError):
            mixer_control.change({"master": 60}, path=self.settings, confirmed=True)
        self.assertEqual(other.read_text(), "PRIVATE-PROTECTED")
        self.assertFalse(self.settings.exists())

    def test_two_concurrent_local_writers_keep_both_user_changes(self):
        def update(request):
            return mixer_control.change(request, path=self.settings, confirmed=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [
                pool.submit(update, {"music": {"volume": 33}}),
                pool.submit(update, {"tablet": {"mute": True}}),
            ]
            for future in tasks:
                future.result(timeout=8)
        result = mixer_control.show(path=self.settings)
        self.assertEqual(result["music"]["volume"], 33)
        self.assertTrue(result["tablet"]["mute"])
        self.assertEqual(result["master"], defaults()["master"])

    def test_cli_defaults_are_read_only_and_mutation_needs_flag(self):
        with mock.patch("audiohub.mixer_control.show", return_value=defaults()) as show:
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["show"])
            self.assertIn('"master": 70', output.getvalue())
            show.assert_called_once_with()
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["set-master", "40"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with({"master": 40}, confirmed=False)
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-volume", "laptop", "45"
                ])
            change.assert_called_once_with({"laptop": {"volume": 45}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "mute", "tablet", "on"
                ])
            change.assert_called_once_with({"tablet": {"mute": True}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change") as change:
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-volume", "unknown", "50"
                ])
            change.assert_not_called()

    def test_atomic_mix_changes_all_four_levels_preserving_mutes_and_eq(self):
        mixer_control.change({"tablet": {"mute": True, "bass": 4},
                              "music": {"treble": -3}},
                             path=self.settings, confirmed=True)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            state = mixer_control.change(
                {"master": 20, "music": {"volume": 15},
                 "laptop": {"volume": 35}, "tablet": {"volume": 0}},
                path=self.settings, confirmed=True)
            atomic.assert_called_once()
        self.assertEqual(state["master"], 20)
        self.assertEqual([state[c]["volume"] for c in ("music", "laptop", "tablet")],
                         [15, 35, 0])
        self.assertTrue(state["tablet"]["mute"])
        self.assertEqual(state["tablet"]["bass"], 4)
        self.assertEqual(state["music"]["treble"], -3)
        self.assertEqual(mixer_control.show(path=self.settings), state)

    def test_invalid_mix_rejects_whole_update_without_changing_existing_state(self):
        mixer_control.change({"master": 45}, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change(
                {"master": 10, "music": {"volume": 20},
                 "laptop": {"volume": 101}, "tablet": {"volume": 30}},
                path=self.settings, confirmed=True)
        self.assertEqual(self.settings.read_bytes(), before)

    def test_set_mix_cli_is_gated_and_sends_one_validated_patch(self):
        expected = {"master": 20, "music": {"volume": 15},
                    "laptop": {"volume": 35}, "tablet": {"volume": 0}}
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-mix", "20", "15", "35", "0"
                ])
            change.assert_called_once_with(expected, confirmed=True)
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["set-mix", "20", "15", "35", "0"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with(expected, confirmed=False)
        with mock.patch("audiohub.mixer_control.change") as change:
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-mix", "20", "15", "35"
                ])
            change.assert_not_called()

    def test_local_application_status_accepts_only_current_complete_ack(self):
        runtime_path = self.root / "runtime" / "status.json"
        expected = requested_mix_controls(defaults())
        self.assertEqual(mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )["supervisor"], "unavailable")
        runtime.atomic_json(runtime_path, {
            "updated_at": 995, "usb_route_ready": True,
            "mixer_controls_accepted": expected,
        })
        accepted = mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )
        self.assertEqual(accepted["supervisor"], "accepted")
        self.assertFalse(accepted["audible_playback_verified"])
        self.assertEqual(accepted["requested"], expected)
        self.assertFalse(self.settings.exists())  # status is read-only
        mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
        pending = mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )
        self.assertEqual(pending["supervisor"], "pending")
        self.assertEqual(pending["requested"]["master"], 30)
        self.assertFalse(pending["audible_playback_verified"])

    def test_local_status_refuses_stale_untrusted_or_incomplete_claim(self):
        runtime_path = self.root / "runtime" / "status.json"
        expected = requested_mix_controls(defaults())
        snapshot = {"updated_at": 1000, "usb_route_ready": True,
                    "mixer_controls_accepted": expected}
        def check(status, now=1000):
            runtime.atomic_json(runtime_path, status)
            return mixer_control.application_status(
                path=self.settings, runtime_path=runtime_path, now=now
            )["supervisor"]
        self.assertEqual(check(snapshot), "accepted")
        self.assertEqual(check(snapshot, now=1016), "unavailable")
        self.assertEqual(check(snapshot, now=999), "unavailable")
        self.assertEqual(check({**snapshot, "updated_at": True}), "unavailable")
        self.assertEqual(check({**snapshot, "usb_route_ready": False}), "unavailable")
        self.assertEqual(check({**snapshot, "mixer_controls_accepted": None}), "unavailable")
        self.assertEqual(check({
            **snapshot, "mixer_controls_accepted": {"master": 70}
        }), "unavailable")
        # bool compares equal to 1 in Python: never accept type confusion.
        forged = dict(expected)
        forged["master"] = True
        self.assertEqual(check({
            **snapshot, "mixer_controls_accepted": forged
        }), "unavailable")
        target = self.root / "untrusted-status.json"
        target.write_text(json.dumps(snapshot))
        runtime_path.unlink()
        runtime_path.symlink_to(target)
        self.assertEqual(mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )["supervisor"], "unavailable")

    def test_local_status_cli_does_not_mutate_or_claim_audio_proof(self):
        payload = {"requested": requested_mix_controls(defaults()),
                   "supervisor": "accepted", "audible_playback_verified": False}
        with mock.patch("audiohub.mixer_control.application_status",
                        return_value=payload) as status:
            with mock.patch("audiohub.mixer_control.change") as change:
                with redirect_stdout(StringIO()) as stdout:
                    mixer_control.main(["status"])
                self.assertIn('"supervisor": "accepted"', stdout.getvalue())
                self.assertIn("no hardware audio was measured", stdout.getvalue())
                status.assert_called_once_with()
                change.assert_not_called()

    def test_supervisor_ack_requires_usb_and_all_three_eq_sinks(self):
        from types import SimpleNamespace
        supervisor = object.__new__(runtime.Supervisor)
        supervisor.settings = defaults()
        supervisor.route_plan = runtime.default_routes()
        supervisor.assignments = {}
        supervisor.loopbacks = {}
        supervisor.retry_state = {}
        supervisor.route_failures_total = 0
        supervisor.output_switch_failures = 0
        self.assertIsNotNone(requested_mix_controls(defaults()))
        graph = {"links_inspected": True,
                 "eq_output_to_usb_direct_link": {c: False for c in ("music", "laptop", "tablet")}}
        captured = []
        ids = {"audiohub.music": 11, "audiohub.laptop": 12, "audiohub.tablet": 13}
        result = SimpleNamespace(returncode=0, stdout=b"[]")
        with (mock.patch("audiohub.runtime.run", return_value=result) as pipe,
              mock.patch("audiohub.runtime.pipewire_nodes", return_value=[]),
              mock.patch("audiohub.runtime.summarize_links", return_value=graph),
              mock.patch("audiohub.runtime.choose_usb_output", return_value={"id": 99}),
              mock.patch("audiohub.runtime.bluetooth_sources", return_value=[]),
              mock.patch("audiohub.runtime.virtual_sinks", return_value=ids),
              mock.patch("audiohub.runtime.load_routes", return_value=runtime.default_routes()),
              mock.patch("audiohub.runtime.read_json", return_value=defaults()),
              mock.patch("audiohub.runtime.atomic_json", side_effect=lambda p, s: captured.append(s)),
              mock.patch.object(supervisor, "_route")):
            supervisor.poll()
            self.assertEqual(captured[-1]["mixer_controls_accepted"],
                             requested_mix_controls(defaults()))
            self.assertTrue(captured[-1]["usb_route_ready"])
            self.assertTrue(any(x.args[0] == "wpctl" for x in pipe.call_args_list))
        captured.clear()
        with (mock.patch("audiohub.runtime.run", return_value=result),
              mock.patch("audiohub.runtime.pipewire_nodes", return_value=[]),
              mock.patch("audiohub.runtime.summarize_links", return_value=graph),
              mock.patch("audiohub.runtime.choose_usb_output", return_value={"id": 99}),
              mock.patch("audiohub.runtime.bluetooth_sources", return_value=[]),
              mock.patch("audiohub.runtime.virtual_sinks", return_value={
                  "audiohub.music": 11, "audiohub.laptop": 12,
              }),
              mock.patch("audiohub.runtime.load_routes", return_value=runtime.default_routes()),
              mock.patch("audiohub.runtime.read_json", return_value=defaults()),
              mock.patch("audiohub.runtime.atomic_json", side_effect=lambda p, s: captured.append(s)),
              mock.patch.object(supervisor, "_route")):
            supervisor.poll()
        self.assertIsNone(captured[-1]["mixer_controls_accepted"])

    def test_computed_supervisor_commands_reflect_saved_levels_and_mutes(self):
        from audiohub.mixer import volume_commands
        mixer_control.change({"master": 20, "music": {"volume": 14},
                              "tablet": {"mute": True}},
                             path=self.settings, confirmed=True)
        current = mixer_control.show(path=self.settings)
        commands = volume_commands(current, {"music": 31, "tablet": 33}, 11)
        self.assertEqual(commands[0][:3], ["wpctl", "set-volume", "11"])
        self.assertIn(["wpctl", "set-volume", "31", "0.14"], commands)
        self.assertIn(["wpctl", "set-mute", "33", "1"], commands)
        self.assertTrue(all(isinstance(a, list) for a in commands))


if __name__ == "__main__":
    unittest.main()
