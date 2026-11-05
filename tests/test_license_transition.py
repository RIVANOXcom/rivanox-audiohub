"""Verify Model C policy cannot silently relicense existing AGPL code."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from scripts.license_transition_audit import inspect, REQUIRED_FALSE, STATE


class ModelCTransitionReviewTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / "source"
        paths = (
            "LICENSE", "LICENSE-C-DRAFT.md", "README.md",
            "docs/COMMERCIAL-LICENSING.md",
            ".github/workflows/source-checks.yml",
            ".github/workflows/publish-image.yml", STATE,
        )
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def state(self):
        return json.loads((self.root / STATE).read_text())

    def change_state(self, callback):
        value = self.state()
        callback(value)
        (self.root / STATE).write_text(json.dumps(value))

    def test_current_draft_is_explicitly_not_operative(self):
        report = inspect(self.root)
        self.assertEqual(report["current_effective_license"], "AGPL-3.0-only")
        self.assertEqual(report["planned_license"], "LicenseRef-RIVANOX-Community-1.0")
        self.assertTrue(report["historical_agpl_preserved"])
        self.assertFalse(report["commercial_license_active"])
        self.assertFalse(report["legal_review_complete"])
        self.assertFalse(report["public_release_authorized"])

    def test_all_missing_approval_gates_are_immutable_false(self):
        for field in REQUIRED_FALSE:
            with self.subTest(field=field):
                self.change_state(lambda x: x.update({field: True}))
                with self.assertRaisesRegex(ValueError, "falsely recorded"):
                    inspect(self.root)
                self.change_state(lambda x: x.update({field: False}))

    def test_forged_effective_release_is_refused(self):
        self.change_state(lambda x: x.update({"effective_release_tag": "v1.0.0"}))
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            inspect(self.root)

    def test_forged_change_to_current_license_is_refused(self):
        self.change_state(lambda x: x.update({
            "current_effective_source_license": "LicenseRef-RIVANOX-Community-1.0"
        }))
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            inspect(self.root)

    def test_historical_agpl_remains_preserved(self):
        self.change_state(lambda x: x.update({"historical_agpl_rights_preserved": False}))
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            inspect(self.root)

    def test_draft_cannot_change_existing_agpl_license_file(self):
        (self.root / "LICENSE").write_text("RIVANOX license — all use requires payment")
        with self.assertRaisesRegex(ValueError, "AGPL"):
            inspect(self.root)

    def test_draft_must_be_clearly_nonoperative(self):
        draft = self.root / "LICENSE-C-DRAFT.md"
        draft.write_text(draft.read_text().replace("NOT EFFECTIVE", "EFFECTIVE"))
        with self.assertRaisesRegex(ValueError, "essential"):
            inspect(self.root)

    def test_forged_extra_approval_key_is_refused(self):
        self.change_state(lambda x: x.update({"rivanox_approved": True}))
        with self.assertRaisesRegex(ValueError, "unexpected keys"):
            inspect(self.root)

    def test_state_symlink_is_refused(self):
        state = self.root / STATE
        external = self.root / "state-copy.json"
        shutil.copyfile(state, external)
        state.unlink()
        state.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            inspect(self.root)

    def test_cannot_remove_ci_guard(self):
        path = self.root / ".github/workflows/source-checks.yml"
        path.write_text(path.read_text().replace(
            "scripts/license_transition_audit.py", "echo skipped"))
        with self.assertRaisesRegex(ValueError, "does not enforce"):
            inspect(self.root)

    def test_cannot_enable_unsafe_image_release(self):
        path = self.root / ".github/workflows/publish-image.yml"
        path.write_text(path.read_text().replace("exit 1", "exit 0"))
        with self.assertRaisesRegex(ValueError, "image release"):
            inspect(self.root)

    def test_readme_must_disclose_planned_license_not_effective(self):
        path = self.root / "README.md"
        path.write_text(path.read_text().replace("Model C", "Model B"))
        with self.assertRaisesRegex(ValueError, "disclosures"):
            inspect(self.root)


if __name__ == "__main__":
    unittest.main()
