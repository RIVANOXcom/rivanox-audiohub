"""A fail-closed ledger of review PENDING for every checked-in AudioHub source."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.source_rights_ledger import LEDGER, audit


class SourceRightsLedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        src = json.loads((ROOT / LEDGER).read_text(encoding="utf-8"))
        self.ledger_path = self.root / LEDGER
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(src))
        license_path = self.root / "LICENSE"
        license_path.write_text("GNU AFFERO GENERAL PUBLIC LICENSE\n")
        for item in src["files"]:
            path = self.root / item["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("repo fixture\n")
        self.contents = src

    def update(self, func):
        content = json.loads(self.ledger_path.read_text())
        func(content)
        self.ledger_path.write_text(json.dumps(content))

    def test_current_actual_repository_is_completely_listed(self):
        result = audit(ROOT)
        self.assertGreater(result["files_covered"], 70)
        self.assertFalse(result["all_source_ownership_approved"])
        self.assertFalse(result["all_third_party_code_cleared"])
        self.assertFalse(result["model_c_license_effective"])

    def test_fixture_ledger_is_well_formed(self):
        self.assertEqual(audit(self.root)["files_covered"], len(self.contents["files"]))

    def test_new_unreviewed_source_file_fails(self):
        target = self.root / "src/audiohub/new_vendor.py"
        target.write_text("import something_unknown\n")
        with self.assertRaisesRegex(ValueError, "does not cover"):
            audit(self.root)

    def test_deleted_or_renamed_source_file_fails(self):
        (self.root / self.contents["files"][0]["path"]).unlink()
        with self.assertRaisesRegex(ValueError, "does not cover"):
            audit(self.root)

    def test_cannot_claim_ownership_verified_without_human_review(self):
        self.update(lambda v: v["review_flags"].update({"rights_holder_confirmed": True}))
        with self.assertRaisesRegex(ValueError, "MUST remain false"):
            audit(self.root)

    def test_cannot_claim_future_model_c_eligibility(self):
        self.update(lambda v: v["files"][0].update({"model_c_eligible": True}))
        with self.assertRaisesRegex(ValueError, "Unapproved"):
            audit(self.root)

    def test_cannot_hide_third_party_review_without_human_review(self):
        self.update(lambda v: v["files"][1].update({"third_party_origin_checked": True}))
        with self.assertRaisesRegex(ValueError, "Unapproved"):
            audit(self.root)

    def test_rejects_duplicate_or_non_sorted_paths(self):
        self.update(lambda v: v["files"].append(dict(v["files"][0])))
        with self.assertRaisesRegex(ValueError, "does not cover"):
            audit(self.root)

    def test_rejects_unapproved_new_license(self):
        self.update(lambda v: v.update({"effective_legacy_license": "LicenseRef-Model-C"}))
        with self.assertRaisesRegex(ValueError, "license policy invalid"):
            audit(self.root)

    def test_rejects_symlinked_ledger(self):
        backup = self.root / "backup-rights.json"
        backup.write_bytes(self.ledger_path.read_bytes())
        self.ledger_path.unlink()
        self.ledger_path.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "symlink"):
            audit(self.root)

    def test_rejects_symlinked_source(self):
        target = self.root / self.contents["files"][0]["path"]
        backup = self.root / "elsewhere"
        backup.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "symlink"):
            audit(self.root)

    def test_rejects_historical_license_removal(self):
        (self.root / "LICENSE").write_text("Model C effective license")
        with self.assertRaisesRegex(ValueError, "Historical AGPL"):
            audit(self.root)

    def test_bytecode_files_do_not_trigger_spurious_review(self):
        folder = self.root / "src/audiohub/__pycache__"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "sample.cpython-313.pyc").write_bytes(b"compiled")
        self.assertEqual(audit(self.root)["files_covered"], len(self.contents["files"]))

    def test_canonical_papa_handoff_documents_actual_authority(self):
        path = ROOT / "docs/PAPA_CANONICAL_RESUME_20261105.md"
        text = path.read_text(encoding="utf-8")
        for marker in (
            "RIVANOX AudioHub canonical resume",
            "AGPL-3.0-only", "NOT EFFECTIVE",
            "42106833667", "13453052359",
            "raspberrypi-net-mods", "SOURCE-RIGHTS-LEDGER.json",
            "Issue #37", "Issue #40",
            "copy/paste", "PAPA / RIVANOX AUDIOHUB WEITER",
        ):
            self.assertIn(marker.lower(), text.lower(), marker)

    def test_machine_checkpoint_matches_restricted_rights_ledger(self):
        state = json.loads(
            (ROOT / "docs/PAPA_AUDIOHUB_CHECKPOINT_20261105.json").read_text()
        )
        self.assertEqual(state["schema"], "rivanox-audiohub-papa-checkpoint/1")
        self.assertEqual(state["effective_license"], "AGPL-3.0-only")
        self.assertFalse(state["future_license_effective"])
        self.assertFalse(state["license_rightsholder_verified"])
        self.assertFalse(state["third_party_commercial_clearance"])
        self.assertFalse(state["model_c_private_repo_verified"])
        self.assertFalse(state["public_release_authorized"])
        self.assertFalse(state["hardware_accepted"])
        self.assertTrue(state["old_agpl_recipient_rights_preserved"])
        self.assertEqual(
            state["source_rights_ledger"]["file_count"],
            audit(ROOT)["files_covered"],
        )
        self.assertFalse(state["source_rights_ledger"]["all_reviewed"])
        self.assertFalse(state["latest_legacy_security_change"]["model_c_license_effective"])
        self.assertFalse(state["latest_legacy_security_change"]["physical_pi_security_accepted"])
        self.assertEqual(state["latest_legacy_security_change"]["static_file_cap_bytes"], 524288)
        self.assertEqual(state["latest_legacy_security_change"]["anonymized_status_json_cap_bytes"], 32768)
        self.assertTrue(state["latest_legacy_security_change"]["all_path_components_nofollow"])
        self.assertEqual(state["last_native_verified"]["rootfs_checks_passed"], 70)
        self.assertEqual(state["last_native_verified"]["run_id"], 42208440878)
        self.assertFalse(state["next_runtime_state_security_change"]["model_c_effective"])
        self.assertFalse(state["next_runtime_state_security_change"]["physical_device_accepted"])
        self.assertEqual(state["next_runtime_state_security_change"]["expected_rootfs_guard_count"], 58)
        self.assertTrue(state["next_runtime_state_security_change"]["random_exclusive_temporary_file"])
        self.assertEqual(state["next_supervisor_failclosed_change"]["pr"], 45)
        self.assertEqual(state["next_supervisor_failclosed_change"]["expected_rootfs_guard_count"], 59)
        self.assertTrue(state["next_supervisor_failclosed_change"]["managed_routes_stopped_on_failure"])
        self.assertTrue(state["next_supervisor_failclosed_change"]["cleanup_failure_escalates_to_systemd"])
        self.assertFalse(state["next_supervisor_failclosed_change"]["model_c_effective"])
        self.assertFalse(state["next_supervisor_failclosed_change"]["public_release_authorized"])
        self.assertFalse(state["next_supervisor_failclosed_change"]["hardware_audio_accepted"])
        self.assertEqual(state["next_bluetooth_agent_trust_security_change"]["pr"], 46)
        self.assertEqual(state["next_bluetooth_agent_trust_security_change"]["authorization_ttl_seconds"], 45)
        self.assertEqual(state["next_bluetooth_agent_trust_security_change"]["expected_rootfs_guard_count"], 61)
        self.assertTrue(state["next_bluetooth_agent_trust_security_change"]["bluez_paired_property_verified"])
        self.assertTrue(state["next_bluetooth_agent_trust_security_change"]["bluez_signal_sender_filtered"])
        self.assertFalse(state["next_bluetooth_agent_trust_security_change"]["authenticated_owner_claiming_complete"])
        self.assertFalse(state["next_bluetooth_agent_trust_security_change"]["hardware_acceptance"])
        self.assertFalse(state["next_bluetooth_agent_trust_security_change"]["model_c_effective"])
        self.assertFalse(state["next_bluetooth_agent_trust_security_change"]["public_release_authorized"])
        self.assertEqual(state["next_pipewire_stdout_security_change"]["pr"], 47)
        self.assertEqual(state["next_pipewire_stdout_security_change"]["max_stdout_bytes"], 4194304)
        self.assertEqual(state["next_pipewire_stdout_security_change"]["expected_rootfs_guard_count"], 63)
        self.assertTrue(state["next_pipewire_stdout_security_change"]["uses_incremental_selector_read"])
        self.assertFalse(state["next_pipewire_stdout_security_change"]["human_source_rights_approved"])
        self.assertFalse(state["next_pipewire_stdout_security_change"]["commercial_model_c_approved"])
        self.assertFalse(state["next_pipewire_stdout_security_change"]["hardware_accepted"])
        self.assertFalse(state["next_pipewire_stdout_security_change"]["public_release_authorized"])
        self.assertEqual(state["source_rights_ledger"]["file_count"], 83)
        self.assertEqual(state["next_manual_hardware_observation"]["pr"], 48)
        self.assertEqual(state["next_manual_hardware_observation"]["expected_native_rootfs_guard_count"], 65)
        self.assertEqual(state["next_manual_hardware_observation"]["operator_manual_prompt_count"], 6)
        self.assertFalse(state["next_manual_hardware_observation"]["hardware_accepted"])
        self.assertFalse(state["next_manual_hardware_observation"]["ownership_authenticated"])
        self.assertFalse(state["next_manual_hardware_observation"]["legal_redistribution_approved"])
        self.assertFalse(state["next_manual_hardware_observation"]["model_c_license_effective"])
        self.assertFalse(state["next_manual_hardware_observation"]["release_ready"])
        self.assertEqual(state["next_pipewire_identity_safety_change"]["pr"], 49)
        self.assertEqual(state["next_pipewire_identity_safety_change"]["expected_rootfs_guard_count"], 66)
        self.assertTrue(state["next_pipewire_identity_safety_change"]["global_node_ids_checked"])
        self.assertTrue(state["next_pipewire_identity_safety_change"]["duplicate_logical_sink_disables_all_routes"])
        self.assertTrue(state["next_pipewire_identity_safety_change"]["duplicate_bluetooth_mac_discarded"])
        self.assertFalse(state["next_pipewire_identity_safety_change"]["hardware_accepted"])
        self.assertFalse(state["next_pipewire_identity_safety_change"]["commercial_model_c_approved"])
        self.assertFalse(state["next_pipewire_identity_safety_change"]["public_release_ready"])
        self.assertEqual(state["next_offline_diagnostic_path_safety_change"]["pr"], 50)
        self.assertEqual(state["next_offline_diagnostic_path_safety_change"]["expected_rootfs_guard_count"], 67)
        self.assertEqual(state["next_offline_diagnostic_path_safety_change"]["max_runtime_status_bytes"], 4096)
        self.assertTrue(state["next_offline_diagnostic_path_safety_change"]["all_directory_components_nofollow"])
        self.assertTrue(state["next_offline_diagnostic_path_safety_change"]["hardlinked_status_refused"])
        self.assertFalse(state["next_offline_diagnostic_path_safety_change"]["public_release_ready"])
        self.assertFalse(state["next_offline_diagnostic_path_safety_change"]["model_c_license_effective"])
        self.assertFalse(state["next_offline_diagnostic_path_safety_change"]["hardware_accepted"])
        self.assertEqual(state["next_laptop_bounded_capture_security_change"]["pr"], 51)
        self.assertEqual(state["next_laptop_bounded_capture_security_change"]["max_stdout_bytes"], 4194304)
        self.assertEqual(state["next_laptop_bounded_capture_security_change"]["timeout_seconds_per_command"], 5)
        self.assertEqual(state["next_laptop_bounded_capture_security_change"]["expected_rootfs_guard_count"], 68)
        self.assertTrue(state["next_laptop_bounded_capture_security_change"]["bounded_capture_for_pw_dump"])
        self.assertTrue(state["next_laptop_bounded_capture_security_change"]["bounded_capture_for_wpctl"])
        self.assertTrue(state["next_laptop_bounded_capture_security_change"]["does_not_autoenable_lan_receiver"])
        self.assertFalse(state["next_laptop_bounded_capture_security_change"]["model_c_license_effective"])
        self.assertFalse(state["next_laptop_bounded_capture_security_change"]["public_release_ready"])
        self.assertFalse(state["next_laptop_bounded_capture_security_change"]["physical_edifier_accepted"])
        self.assertEqual(state["next_status_http_resource_privacy_change"]["pr"], 52)
        self.assertEqual(state["next_status_http_resource_privacy_change"]["max_concurrent_clients"], 8)
        self.assertEqual(state["next_status_http_resource_privacy_change"]["client_read_timeout_seconds"], 5)
        self.assertEqual(state["next_status_http_resource_privacy_change"]["expected_native_rootfs_guard_count"], 69)
        self.assertTrue(state["next_status_http_resource_privacy_change"]["nonblocking_overflow_closure"])
        self.assertTrue(state["next_status_http_resource_privacy_change"]["raw_request_logging_disabled"])
        self.assertTrue(state["next_status_http_resource_privacy_change"]["read_only_status_api_preserved"])
        self.assertTrue(state["next_status_http_resource_privacy_change"]["lan_bind_requires_explicit_unsafe_optin"])
        self.assertFalse(state["next_status_http_resource_privacy_change"]["model_c_license_effective"])
        self.assertFalse(state["next_status_http_resource_privacy_change"]["public_release_ready"])
        self.assertFalse(state["next_status_http_resource_privacy_change"]["hardware_accepted"])
        self.assertEqual(state["next_status_private_file_identity_change"]["pr"], 53)
        self.assertEqual(state["next_status_private_file_identity_change"]["expected_native_rootfs_guard_count"], 70)
        self.assertTrue(state["next_status_private_file_identity_change"]["private_owner_required"])
        self.assertTrue(state["next_status_private_file_identity_change"]["private_parent_directory_required"])
        self.assertTrue(state["next_status_private_file_identity_change"]["hardlink_count_must_equal_one"])
        self.assertTrue(state["next_status_private_file_identity_change"]["static_html_world_readability_preserved"])
        self.assertTrue(state["next_status_private_file_identity_change"]["stale_no_health_on_invalid_status"])
        self.assertFalse(state["next_status_private_file_identity_change"]["public_release_ready"])
        self.assertFalse(state["next_status_private_file_identity_change"]["model_c_license_effective"])
        self.assertFalse(state["next_status_private_file_identity_change"]["physical_edifier_accepted"])
        self.assertEqual(state["next_status_malformed_input_failclosed_change"]["pr"], 54)
        self.assertEqual(state["next_status_malformed_input_failclosed_change"]["parent_pr"], 53)
        self.assertEqual(state["next_status_malformed_input_failclosed_change"]["expected_native_rootfs_guard_count"], 71)
        self.assertTrue(state["next_status_malformed_input_failclosed_change"]["nested_json_fail_closed"])
        self.assertTrue(state["next_status_malformed_input_failclosed_change"]["malformed_request_target_returns_404"])
        self.assertFalse(state["next_status_malformed_input_failclosed_change"]["public_release_ready"])
        self.assertEqual(state["next_bluetooth_agent_trust_security_change"]["pairable_timeout_seconds"], 600)
        self.assertEqual(state["next_bluetooth_agent_trust_security_change"]["discoverable_timeout_seconds"], 600)
        self.assertTrue(state["next_bluetooth_agent_trust_security_change"]["initial_deadline_relative_to_linux_boot"])

        self.assertEqual(state["last_native_verified"]["installed_packages"], 689)
        self.assertEqual(state["last_native_verified"]["copyright_paths_unresolved"], 9)
        self.assertFalse(state["last_native_verified"]["public_release_ready"])
        self.assertEqual(
            [item["number"] for item in state["draft_pr_chain"]],
            [35, 36, 38, 39, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54],
        )

    def test_primary_handoff_points_to_authoritative_resume(self):
        docs = (ROOT / "docs/PROJECT-HANDOFF.md").read_text()
        self.assertIn("PAPA_CANONICAL_RESUME_20261105.md", docs)
        self.assertIn("PAPA_AUDIOHUB_CHECKPOINT_20261105.json", docs)

    def test_readme_licensing_notice_has_real_newlines(self):
        text = (ROOT / "README.md").read_text()
        self.assertNotIn("\\n> ", text)
        self.assertIn("PAPA_CANONICAL_RESUME_20261105.md", text)
        self.assertIn("AGPL-3.0-only", text)

    def test_declared_license_switch_has_not_occurred(self):
        state = json.loads(
            (ROOT / "docs/licensing/TRANSITION-STATE.json").read_text()
        )
        self.assertFalse(state["license_switch_effective"])
        self.assertFalse(state["public_release_authorized"])


if __name__ == "__main__":
    unittest.main()
