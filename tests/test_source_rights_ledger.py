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

        self.assertEqual(state["last_native_verified"]["installed_packages"], 689)
        self.assertEqual(state["last_native_verified"]["copyright_paths_unresolved"], 9)
        self.assertFalse(state["last_native_verified"]["public_release_ready"])
        self.assertEqual(
            [item["number"] for item in state["draft_pr_chain"]],
            [35, 36, 38, 39, 41, 42, 43],
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
