"""Offline operator observations are not release or legal approval."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import manual_acceptance as manual

READY = {
    "schema_version": 1,
    "assessment": "topology_only_not_hardware_acceptance",
    "topology_preflight": "ready_for_manual_test",
    "release_ready": False,
    "checks": {
        "pipewire_inspection_succeeded": True,
        "edifier_usb_sink_unique": True,
        "virtual_sink_unique": {"music": True, "laptop": True, "tablet": True},
        "bluetooth_source_count": 1,
    },
    "hardware_gates": {
        "speaker_audible": "unverified",
        "three_simultaneous_sources": "unverified",
        "per_channel_isolation": "unverified",
        "mix_clipping": "unverified",
        "wifi_owner_security": "unverified",
        "endurance_24h": "unverified",
    },
}
INCOMPLETE = {"topology_preflight": "incomplete", "release_ready": False}


class OfflineHardwareAcceptanceTests(unittest.TestCase):
    def test_all_real_operator_yes_answers_are_still_unverified(self):
        asked = []
        result = manual.observe(READY, ask=lambda prompt: (asked.append(prompt), "yes")[1])
        self.assertEqual(len(asked), len(manual.GATES))
        self.assertTrue(result["all_questions_answered_observed"])
        self.assertFalse(result["hardware_accepted"])
        self.assertFalse(result["ownership_authenticated"])
        self.assertFalse(result["legal_redistribution_approved"])
        self.assertFalse(result["model_c_license_effective"])
        self.assertFalse(result["release_ready"])
        self.assertFalse(result["persisted"])

    def test_failures_are_retained_only_as_fixed_categories(self):
        result = manual.observe(READY, ask=lambda prompt: "no")
        self.assertEqual(set(result["operator_observations"].values()), {"failed"})
        self.assertFalse(result["all_questions_answered_observed"])

    def test_skip_never_implies_observation(self):
        result = manual.observe(READY, ask=lambda prompt: "")
        self.assertEqual(set(result["operator_observations"].values()), {"not_tested"})
        self.assertFalse(result["all_questions_answered_observed"])

    def test_observer_free_text_cannot_leak_password_or_mac(self):
        text = "OWNER-PASSWORD / AA:BB:CC:DD:EE:FF"
        result = manual.observe(READY, ask=lambda prompt: text)
        rendered = json.dumps(result)
        self.assertNotIn("OWNER-PASSWORD", rendered)
        self.assertNotIn("AA:BB", rendered)
        self.assertEqual(set(result["operator_observations"].values()), {"not_tested"})

    def test_invalid_answers_are_bounded_to_three_attempts(self):
        called = 0

        def invalid(prompt):
            nonlocal called
            called += 1
            return "maybe"

        result = manual.observe(READY, ask=invalid)
        self.assertEqual(called, len(manual.GATES) * manual.MAX_INPUT_ATTEMPTS)
        self.assertFalse(result["all_questions_answered_observed"])

    def test_invalid_then_valid_is_accepted_without_echoing_raw_input(self):
        choices = iter(["MAC:AA:BB", "  YES  "] * len(manual.GATES))
        result = manual.observe(READY, ask=lambda prompt: next(choices))
        self.assertTrue(result["all_questions_answered_observed"])
        self.assertNotIn("MAC:", json.dumps(result))

    def test_eof_aborts_each_question_as_not_tested(self):
        def closed(prompt):
            raise EOFError()

        result = manual.observe(READY, ask=closed)
        self.assertEqual(set(result["operator_observations"].values()), {"not_tested"})

    def test_keyboard_interrupt_cannot_mark_manual_success(self):
        def interrupted(prompt):
            raise KeyboardInterrupt()

        result = manual.observe(READY, ask=interrupted)
        self.assertFalse(result["all_questions_answered_observed"])

    def test_unexpected_answer_type_is_not_interpreted_as_yes(self):
        result = manual.observe(READY, ask=lambda prompt: True)
        self.assertFalse(result["all_questions_answered_observed"])

    def test_unavailable_topology_never_prompts_for_fake_sound(self):
        question = mock.Mock(side_effect=AssertionError("asked operator"))
        result = manual.observe(INCOMPLETE, ask=question)
        question.assert_not_called()
        self.assertEqual(result["preflight"], "incomplete")
        self.assertFalse(result["all_questions_answered_observed"])

    def test_malformed_preflight_never_prompts(self):
        question = mock.Mock(side_effect=AssertionError("asked operator"))
        for preflight in (None, [], {}, "ready", {"topology_preflight": "ready_for_manual_test",
                                                  "release_ready": True}):
            with self.subTest(value=repr(preflight)):
                self.assertEqual(manual.observe(preflight, ask=question)["preflight"],
                                 "incomplete")
        question.assert_not_called()


    def test_bare_ready_flag_without_real_prerequisites_never_prompts(self):
        question = mock.Mock(side_effect=AssertionError("prompted without proof"))
        result = manual.observe({
            "topology_preflight": "ready_for_manual_test",
            "release_ready": False,
        }, ask=question)
        question.assert_not_called()
        self.assertEqual(result["preflight"], "incomplete")
        self.assertFalse(result["all_questions_answered_observed"])

    def test_contradictory_topology_checks_never_prompt(self):
        question = mock.Mock(side_effect=AssertionError("prompted despite contradiction"))
        for key, field, value in (
            ("checks", "pipewire_inspection_succeeded", False),
            ("checks", "edifier_usb_sink_unique", False),
            ("checks", "virtual_sink_unique", {"music": True, "laptop": False,
                                                "tablet": True}),
            ("checks", "virtual_sink_unique", {"music": True, "laptop": True,
                                                "tablet": True, "extra": True}),
        ):
            import copy
            report = copy.deepcopy(READY)
            report[key][field] = value
            with self.subTest(field=field, value=repr(value)):
                self.assertEqual(
                    manual.observe(report, ask=question)["preflight"], "incomplete"
                )
        question.assert_not_called()

    def test_invalid_preflight_schema_and_claimed_hardware_success_fail_closed(self):
        question = mock.Mock(side_effect=AssertionError("prompted despite bad schema"))
        for edit in (
            {"schema_version": True},
            {"schema_version": 2},
            {"assessment": "hardware_accepted"},
            {"hardware_gates": {"speaker_audible": "observed"}},
            {"release_ready": True},
            {"checks": []},
        ):
            import copy
            report = copy.deepcopy(READY)
            report.update(edit)
            with self.subTest(edit=repr(edit)):
                self.assertEqual(
                    manual.observe(report, ask=question)["preflight"], "incomplete"
                )
        question.assert_not_called()

    def test_consistent_real_preflight_report_allows_prompts_but_never_signoff(self):
        from audiohub import hardware_preflight
        def n(number, name, kind, **other):
            return {"id": number, "type": "PipeWire:Interface:Node",
                    "info": {"props": {"node.name": name,
                                       "media.class": kind, **other}}}
        topology = [
            n(1, "alsa_output.usb-Edifier_R600USB", "Audio/Sink"),
            n(2, "audiohub.music", "Audio/Sink"),
            n(3, "audiohub.laptop", "Audio/Sink"),
            n(4, "audiohub.tablet", "Audio/Sink"),
        ]
        report = hardware_preflight.inspect_topology(topology)
        self.assertEqual(report["topology_preflight"], "ready_for_manual_test")
        answers = manual.observe(report, ask=lambda _: "yes")
        self.assertTrue(answers["all_questions_answered_observed"])
        self.assertFalse(answers["hardware_accepted"])
        self.assertFalse(answers["release_ready"])

    def test_all_observation_fields_have_fixed_nonidentifying_names(self):
        result = manual.observe(READY, ask=lambda prompt: "skip")
        self.assertEqual(set(result["operator_observations"]),
                         {gate for gate, _ in manual.GATES})
        self.assertNotIn("edifier", json.dumps(result).lower())

    def test_main_success_means_report_only_not_product_signoff(self):
        emitted = []
        code = manual.main(check=lambda: READY, ask=lambda prompt: "y",
                           output=emitted.append)
        self.assertEqual(code, 0)
        result = json.loads(emitted[0])
        self.assertTrue(result["all_questions_answered_observed"])
        self.assertFalse(result["hardware_accepted"])
        self.assertFalse(result["release_ready"])

    def test_main_incomplete_returns_code_two_and_private_json(self):
        emitted = []
        code = manual.main(check=lambda: INCOMPLETE, output=emitted.append)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(emitted[0])["preflight"], "incomplete")

    def test_failed_probe_cannot_force_hardware_success(self):
        emitted = []

        def fail():
            raise OSError("device serial OWNER-SECRET")

        code = manual.main(check=fail, output=emitted.append)
        self.assertEqual(code, 2)
        self.assertNotIn("OWNER-SECRET", emitted[0])
        self.assertFalse(json.loads(emitted[0])["release_ready"])

    def test_review_gates_are_false_for_every_possible_manual_answer(self):
        for choice in ("yes", "no", "skip"):
            report = manual.observe(READY, ask=lambda prompt: choice)
            self.assertFalse(report["ownership_authenticated"])
            self.assertFalse(report["legal_redistribution_approved"])
            self.assertFalse(report["model_c_license_effective"])
            self.assertFalse(report["release_ready"])
            self.assertEqual(report["wifi_owner_security"], "unverified")

    def test_cli_module_does_not_write_or_open_network_sockets(self):
        source = (Path(__file__).resolve().parents[1] /
                  "src/audiohub/manual_acceptance.py").read_text()
        self.assertNotIn("import socket", source)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("subprocess.", source)


if __name__ == "__main__":
    unittest.main()
