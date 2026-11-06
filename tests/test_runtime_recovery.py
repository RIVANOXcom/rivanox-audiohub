"""AudioHub runtime recovery tests without requiring Bluetooth or USB hardware."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.runtime import STATE, Supervisor, MAX_RUNTIME_JSON_BYTES, atomic_json, read_json
from audiohub.mixer import defaults as mixer_defaults
from audiohub.source_routes import defaults as route_defaults


class FakeProcess:
    def __init__(self):
        self.alive = True
        self.terminated = False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout=2):
        return 0

    def kill(self):
        self.alive = False


class RecoveryTests(unittest.TestCase):
    def supervisor(self):
        obj = Supervisor.__new__(Supervisor)
        obj.assignments = {"AA:BB:CC:DD:EE:FF": "music"}
        obj.loopbacks = {}
        obj.last_default = None
        return obj

    def source(self, name):
        return [{"address": "AA:BB:CC:DD:EE:FF", "name": name}]

    def test_status_stored_in_volatile_runtime_directory(self):
        expected = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self.assertTrue(str(STATE).startswith(expected + "/audiohub/"))

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_new_audio_source_replaces_old_route(self, popen):
        one, two = FakeProcess(), FakeProcess()
        popen.side_effect = [one, two]
        s = self.supervisor()
        s._route(self.source("bluez_input.first"), {"audiohub.music": 7})
        self.assertEqual(popen.call_count, 1)
        s._route(self.source("bluez_input.first"), {"audiohub.music": 7})
        self.assertEqual(popen.call_count, 1, "unchanged routes must not restart")
        s._route(self.source("bluez_input.second"), {"audiohub.music": 7})
        self.assertTrue(one.terminated)
        self.assertEqual(popen.call_count, 2)
        self.assertFalse(two.terminated)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_duplicate_virtual_sinks_stop_existing_managed_route(self, popen):
        from audiohub.discovery import virtual_sinks
        process = FakeProcess()
        popen.return_value = process
        supervisor = self.supervisor()
        source = self.source("bluez_input.first")
        supervisor._route(source, {"audiohub.music": 20})
        self.assertEqual(popen.call_count, 1)
        ambiguous = [
            {"id": 20, "type": "PipeWire:Interface:Node",
             "info": {"props": {"node.name": "audiohub.music",
                                 "media.class": "Audio/Sink"}}},
            {"id": 21, "type": "PipeWire:Interface:Node",
             "info": {"props": {"node.name": "audiohub.music",
                                 "media.class": "Audio/Sink"}}},
        ]
        self.assertEqual(virtual_sinks(ambiguous), {})
        supervisor._route(source, virtual_sinks(ambiguous))
        self.assertTrue(process.terminated)
        self.assertEqual(supervisor.loopbacks, {})
        self.assertEqual(popen.call_count, 1)

    @mock.patch("audiohub.runtime.subprocess.Popen")
    def test_disconnected_sink_stops_managed_routes(self, popen):
        proc = FakeProcess()
        popen.return_value = proc
        s = self.supervisor()
        s._route(self.source("bluez_input.first"), {"audiohub.music": 7})
        s._route(self.source("bluez_input.first"), {})
        self.assertTrue(proc.terminated)
        self.assertEqual(s.loopbacks, {})


class PrivateRuntimeStateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.private = self.base / "private"
        self.private.mkdir(mode=0o700)
        self.path = self.private / "runtime-status.json"

    def test_private_status_roundtrip_and_permissions(self):
        payload = {"usb_output": True, "routes": {"music": 1}}
        atomic_json(self.path, payload)
        self.assertEqual(read_json(self.path, {}), payload)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)

    def test_two_updates_are_atomic_and_leave_no_tmp(self):
        atomic_json(self.path, {"first": True})
        atomic_json(self.path, {"second": True})
        self.assertEqual(read_json(self.path, {}), {"second": True})
        self.assertEqual(sorted(p.name for p in self.private.iterdir()),
                         ["runtime-status.json"])

    def test_existing_symlink_destination_refused_without_touching_target(self):
        protected = self.base / "protected"
        protected.write_text("DO NOT MODIFY")
        self.path.symlink_to(protected)
        with self.assertRaises((OSError, PermissionError)):
            atomic_json(self.path, {"tried": True})
        self.assertEqual(protected.read_text(), "DO NOT MODIFY")
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(read_json(self.path, {"ok": False}), {"ok": False})

    def test_legacy_predictable_tmp_symlink_is_not_used(self):
        protected = self.base / "protected"
        protected.write_text("PRIVATE OWNER DATA")
        old_tmp = self.path.with_suffix(".tmp")
        old_tmp.symlink_to(protected)
        atomic_json(self.path, {"a": 1})
        self.assertEqual(protected.read_text(), "PRIVATE OWNER DATA")
        self.assertTrue(old_tmp.is_symlink())
        self.assertEqual(read_json(self.path, {}), {"a": 1})

    def test_symlinked_parent_directory_is_denied(self):
        external = self.base / "linked"
        external.symlink_to(self.private, target_is_directory=True)
        malicious_path = external / "state.json"
        with self.assertRaises(OSError):
            atomic_json(malicious_path, {"secret": "no"})
        self.assertFalse((self.private / "state.json").exists())
        self.assertEqual(read_json(malicious_path, {"safe": True}),
                         {"safe": True})

    def test_world_readable_storage_directory_rejected(self):
        os.chmod(self.private, 0o755)
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"secret": "never"})
        self.assertFalse(self.path.exists())
        self.assertEqual(read_json(self.path, {}), {})

    def test_overlarge_state_read_returns_default(self):
        self.path.write_bytes(b"x" * (MAX_RUNTIME_JSON_BYTES + 1))
        os.chmod(self.path, 0o600)
        self.assertEqual(read_json(self.path, {"safe": True}), {"safe": True})

    def test_overlarge_state_write_is_refused_untouched(self):
        atomic_json(self.path, {"first": 1})
        old = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "storage limit"):
            atomic_json(self.path, {"data": "x" * MAX_RUNTIME_JSON_BYTES})
        self.assertEqual(self.path.read_bytes(), old)

    def test_corrupt_json_returns_fallback_without_leak(self):
        self.path.write_text("{{SECRET{")
        os.chmod(self.path, 0o600)
        self.assertEqual(read_json(self.path, {"fresh": False}), {"fresh": False})

    def test_duplicate_private_assignment_keys_fail_closed_without_rewriting(self):
        bad = '{"AA:BB:CC:DD:EE:FF":"music","AA:BB:CC:DD:EE:FF":"tablet"}'
        self.path.write_text(bad)
        self.path.chmod(0o600)
        self.assertEqual(read_json(self.path, {"safe": True}), {"safe": True})
        self.assertEqual(self.path.read_text(), bad)

    def test_nested_duplicate_private_settings_fail_closed(self):
        bad = '{"mix":{"music":{"gain":0.4,"gain":0.9}}}'
        self.path.write_text(bad)
        self.path.chmod(0o600)
        self.assertEqual(read_json(self.path, {"safe": False}), {"safe": False})

    def test_nonfinite_private_state_constants_are_refused(self):
        for number in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(number=number):
                self.path.write_text('{"private":' + number + "}")
                self.path.chmod(0o600)
                self.assertEqual(read_json(self.path, {"blocked": True}), {"blocked": True})

    def test_float_exponent_overflow_is_refused_in_unknown_settings(self):
        for number in ("1e999", "-1e999"):
            with self.subTest(number=number):
                self.path.write_text('{"untrusted":' + number + "}")
                self.path.chmod(0o600)
                self.assertEqual(read_json(self.path, {"blocked": True}), {"blocked": True})

    def test_valid_but_deep_private_settings_cannot_crash_supervisor(self):
        records = (
            '{"next":' * 120 + '0' + '}' * 120,
            '[' * 1300 + '0' + ']' * 1300,
        )
        for body in records:
            with self.subTest(prefix=body[:10]):
                self.assertLess(len(body), MAX_RUNTIME_JSON_BYTES)
                self.path.write_text(body)
                self.path.chmod(0o600)
                self.assertEqual(read_json(self.path, {"fallback": True}),
                                 {"fallback": True})

    def test_finite_numeric_private_state_still_roundtrips(self):
        source = '{"usb_output":true,"ignored":1.25e2}'
        self.path.write_text(source)
        self.path.chmod(0o600)
        self.assertEqual(read_json(self.path, {}), {
            "usb_output": True, "ignored": 125.0,
        })

    def test_malformed_type_returns_fallback(self):
        self.path.write_text("[1,2,3]")
        os.chmod(self.path, 0o600)
        self.assertEqual(read_json(self.path, {}), {})

    def test_symlinked_file_read_returns_fallback(self):
        hidden = self.base / "hidden"
        hidden.write_text('{"secret":"do not read"}')
        self.path.symlink_to(hidden)
        self.assertEqual(read_json(self.path, {"blocked": True}),
                         {"blocked": True})

    def test_fifo_file_is_refused_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("Linux-only")
        os.mkfifo(self.path)
        self.assertEqual(read_json(self.path, {"blocked": True}),
                         {"blocked": True})
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"data": 1})

    def test_hardlinked_destination_is_refused(self):
        original = self.base / "original"
        original.write_text('{"old":1}')
        os.chmod(original, 0o600)
        os.link(original, self.path)
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"old": 2})
        self.assertEqual(json.loads(original.read_text()), {"old": 1})
        self.assertEqual(read_json(self.path, {"no": True}), {"no": True})

    def test_destination_with_unsafe_file_permissions_is_refused(self):
        self.path.write_text('{"old":1}')
        os.chmod(self.path, 0o644)
        with self.assertRaises(PermissionError):
            atomic_json(self.path, {"old": 2})
        self.assertEqual(read_json(self.path, {"safe": True}), {"safe": True})

    def test_nonjson_nan_is_refused_before_file_creation(self):
        with self.assertRaises(ValueError):
            atomic_json(self.path, {"number": float("nan")})
        self.assertFalse(self.path.exists())

    def test_create_missing_private_intermediate_directory(self):
        dest = self.private / "inner" / "runtime-status.json"
        atomic_json(dest, {"ok": True})
        self.assertEqual(read_json(dest, {}), {"ok": True})
        self.assertEqual(stat.S_IMODE(dest.parent.stat().st_mode), 0o700)

    def test_reject_relative_and_traversal_state_paths(self):
        for invalid in (Path("state.json"), self.private / ".." / "secret.json"):
            with self.subTest(path=str(invalid)):
                with self.assertRaises(ValueError):
                    atomic_json(invalid, {"value": 1})
                self.assertEqual(read_json(invalid, {"blocked": True}),
                                 {"blocked": True})


class SupervisorFailClosedTests(unittest.TestCase):
    def instance(self):
        s = Supervisor.__new__(Supervisor)
        s.loopbacks = {}
        s.retry_state = {"first": ("node", 123, 2)}
        return s

    def _poll_mixer_case(self, supervisor, outcome, events, stored=None):
        """No PipeWire, audio process or real hardware is accessed."""
        from contextlib import ExitStack

        def simulated_run(*args, **kwargs):
            events.append(("command", args))
            if args[:2] == ("wpctl", "set-volume") and args[2] == "10":
                if outcome == "master_missing":
                    return None
            if args[:2] == ("wpctl", "set-mute") and outcome == "mute_rejected":
                return subprocess.CompletedProcess(args, 9, "", "")
            return subprocess.CompletedProcess(args, 0, "[]", "")

        supervisor.settings = mixer_defaults()
        supervisor.route_plan = route_defaults()
        supervisor.assignments = {}
        supervisor.route_policy_valid = True
        supervisor.last_default = None
        with ExitStack() as stack:
            stack.enter_context(mock.patch("audiohub.runtime.run", side_effect=simulated_run))
            stack.enter_context(mock.patch("audiohub.runtime.pipewire_nodes", return_value=[]))
            stack.enter_context(mock.patch("audiohub.runtime.choose_usb_output", return_value={"id": 10}))
            stack.enter_context(mock.patch("audiohub.runtime.bluetooth_sources", return_value=[]))
            stack.enter_context(mock.patch("audiohub.runtime.virtual_sinks", return_value={
                "audiohub.music": 20, "audiohub.laptop": 21, "audiohub.tablet": 22,
            }))
            stack.enter_context(mock.patch("audiohub.runtime.summarize_links", return_value={
                "links_inspected": 0,
                "eq_output_to_usb_direct_link": {
                    "music": False, "laptop": False, "tablet": False,
                },
            }))
            stack.enter_context(mock.patch("audiohub.runtime.load_routes", return_value=route_defaults()))
            stack.enter_context(mock.patch(
                "audiohub.runtime.read_json",
                return_value=mixer_defaults() if stored is None else stored,
            ))
            persistence = stack.enter_context(mock.patch("audiohub.runtime.atomic_json"))
            routing = stack.enter_context(mock.patch.object(
                supervisor, "_route", side_effect=lambda *_: events.append(("route",)),
            ))
            completed = supervisor.poll_safely()
        return completed, routing, persistence

    def test_master_volume_failure_stops_existing_audio_and_never_routes(self):
        supervisor = self.instance()
        active = FakeProcess()
        supervisor.loopbacks = {
            "PRIVATE": ("bluez_input.known", "audiohub.music", active)
        }
        events = []
        ok, routing, saved = self._poll_mixer_case(supervisor, "master_missing", events)
        self.assertFalse(ok)
        self.assertTrue(active.terminated)
        self.assertEqual(supervisor.loopbacks, {})
        routing.assert_not_called()
        saved.assert_not_called()
        self.assertIn(("command", ("wpctl", "set-default", "10")), events)
        self.assertTrue(any(e[0] == "command" and e[1][:3] ==
                            ("wpctl", "set-volume", "10") for e in events))

    def test_rejected_per_input_mute_fails_closed_and_stops_routes(self):
        supervisor = self.instance()
        active = FakeProcess()
        supervisor.loopbacks = {
            "PRIVATE": ("bluez_input.known", "audiohub.music", active)
        }
        events = []
        ok, routing, saved = self._poll_mixer_case(supervisor, "mute_rejected", events)
        self.assertFalse(ok)
        self.assertTrue(active.terminated)
        routing.assert_not_called()
        saved.assert_not_called()
        master_index = next(i for i, e in enumerate(events)
                            if e[0] == "command" and e[1][:3] ==
                            ("wpctl", "set-volume", "10"))
        mute_index = next(i for i, e in enumerate(events)
                          if e[0] == "command" and e[1][:2] ==
                          ("wpctl", "set-mute"))
        self.assertLess(master_index, mute_index)

    def test_mixer_commands_complete_before_new_sources_are_routed(self):
        supervisor = self.instance()
        events = []
        ok, routing, saved = self._poll_mixer_case(supervisor, "ok", events)
        self.assertTrue(ok)
        routing.assert_called_once()
        saved.assert_called_once()
        master_index = next(i for i, e in enumerate(events)
                            if e[0] == "command" and e[1][:3] ==
                            ("wpctl", "set-volume", "10"))
        route_index = next(i for i, e in enumerate(events) if e[0] == "route")
        self.assertLess(master_index, route_index)
        self.assertTrue(all(e[0] != "command" for e in events[route_index + 1:]))

    def test_invalid_mixer_setting_cannot_leave_active_audio_running(self):
        supervisor = self.instance()
        active = FakeProcess()
        supervisor.loopbacks = {
            "PRIVATE": ("bluez_input.known", "audiohub.music", active)
        }
        events = []
        ok, routing, saved = self._poll_mixer_case(
            supervisor, "ok", events, stored={"master": float("nan")},
        )
        self.assertFalse(ok)
        self.assertTrue(active.terminated)
        routing.assert_not_called()
        saved.assert_not_called()
        self.assertFalse(any(e[0] == "command" and
                             e[1][:2] == ("wpctl", "set-volume") for e in events))

    def test_failed_cycle_terminates_each_active_audio_route(self):
        s = self.instance()
        a = FakeProcess()
        b = FakeProcess()
        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", a),
                       "B": ("bluez_input.b", "audiohub.tablet", b)}
        with mock.patch.object(s, "poll", side_effect=OSError("untrusted state")):
            self.assertFalse(s.poll_safely())
        self.assertTrue(a.terminated)
        self.assertTrue(b.terminated)
        self.assertEqual(s.loopbacks, {})
        self.assertEqual(s.retry_state, {})

    def test_successful_cycle_preserves_current_routes(self):
        s = self.instance()
        proc = FakeProcess()
        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", proc)}
        with mock.patch.object(s, "poll", return_value=None):
            self.assertTrue(s.poll_safely())
        self.assertFalse(proc.terminated)
        self.assertIn("A", s.loopbacks)

    def test_unwritable_runtime_status_cannot_leave_routes_running(self):
        s = self.instance()
        proc = FakeProcess()
        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", proc)}
        with mock.patch.object(s, "poll", side_effect=PermissionError("status")):
            self.assertFalse(s.poll_safely())
        self.assertTrue(proc.terminated)

    def test_cleanup_failure_escalates_to_service_restart_without_secrets(self):
        s = self.instance()

        class Unkillable:
            def poll(self):
                return None

            def terminate(self):
                raise OSError("Sensitive Bluetooth address 11:22:33:44:55:66")

        s.loopbacks = {"SENSITIVE": ("private", "audiohub.music", Unkillable())}
        with mock.patch.object(s, "poll", side_effect=ValueError("private")):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed") as thrown:
                s.poll_safely()
        self.assertNotIn("11:22", str(thrown.exception))
        self.assertNotIn("SENSITIVE", str(thrown.exception))
        self.assertEqual(s.loopbacks, {})

    def test_one_cleanup_failure_does_not_skip_other_route(self):
        s = self.instance()
        good = FakeProcess()

        class FailedProcess:
            def poll(self):
                return None

            def terminate(self):
                raise OSError("fail")

        s.loopbacks = {
            "A": ("bluez_input.a", "audiohub.music", FailedProcess()),
            "B": ("bluez_input.b", "audiohub.tablet", good),
        }
        with mock.patch.object(s, "poll", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                s.poll_safely()
        self.assertTrue(good.terminated)
        self.assertEqual(s.loopbacks, {})

    def test_termination_timeout_forces_kill(self):
        s = self.instance()

        class SlowProcess:
            def __init__(self):
                self.killed = False

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=2):
                if not self.killed:
                    raise subprocess.TimeoutExpired("pw-loopback", timeout)
                return 0

            def kill(self):
                self.killed = True

        proc = SlowProcess()
        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", proc)}
        with mock.patch.object(s, "poll", side_effect=RuntimeError("failure")):
            self.assertFalse(s.poll_safely())
        self.assertTrue(proc.killed)
        self.assertEqual(s.loopbacks, {})

    def test_after_safe_failure_later_cycle_can_retry(self):
        s = self.instance()
        proc = FakeProcess()
        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", proc)}
        with mock.patch.object(s, "poll", side_effect=[ValueError("bad"), None]):
            self.assertFalse(s.poll_safely())
            self.assertTrue(s.poll_safely())
        self.assertTrue(proc.terminated)
        self.assertEqual(s.loopbacks, {})

    def test_serve_keyboard_interrupt_cleans_managed_routes(self):
        s = self.instance()
        proc = FakeProcess()
        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", proc)}
        with mock.patch.object(s, "poll", return_value=None), mock.patch(
            "audiohub.runtime.time.sleep", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                s.serve()
        self.assertTrue(proc.terminated)
        self.assertEqual(s.loopbacks, {})

    def test_serve_keyboard_interrupt_propagates_failed_cleanup(self):
        s = self.instance()

        class BadProcess:
            def poll(self):
                return None

            def terminate(self):
                raise OSError("bad route")

        s.loopbacks = {"A": ("bluez_input.a", "audiohub.music", BadProcess())}
        with mock.patch.object(s, "poll", return_value=None), mock.patch(
            "audiohub.runtime.time.sleep", side_effect=KeyboardInterrupt
        ):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                s.serve()


if __name__ == "__main__":
    unittest.main()
