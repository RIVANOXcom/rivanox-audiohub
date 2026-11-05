"""Adversarial source dependency detection; NOT third-party legal approval."""
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.source_dependency_audit import inspect


class ThirdPartySourceObservationTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        shutil.copytree(ROOT / "src/audiohub", self.root / "src/audiohub")
        shutil.copytree(ROOT / "web", self.root / "web")

    def test_current_source_dependencies_bounded(self):
        result = inspect(self.root)
        self.assertEqual(result["schema"], "rivanox-audiohub-source-dependency-observation/1")
        self.assertGreaterEqual(result["python_production_files_inspected"], 10)
        self.assertEqual(result["third_party_runtime_imports"], ["dbus", "gi"])
        self.assertFalse(result["manual_code_origin_review_complete"])
        self.assertFalse(result["third_party_image_license_review_complete"])
        self.assertFalse(result["model_c_relicense_approved"])

    def test_new_external_python_dependency_requires_review(self):
        path = self.root / "src/audiohub/pairing.py"
        path.write_text(path.read_text() + "\nimport unknown_vendor_lib\n")
        with self.assertRaisesRegex(ValueError, "Unreviewed external"):
            inspect(self.root)

    def test_hidden_new_vendor_python_file_fails(self):
        (self.root / "src/audiohub/copy_of_vendor.py").write_text("import requests\n")
        with self.assertRaisesRegex(ValueError, "Missing reviewable SPDX"):
            inspect(self.root)

    def test_unreviewed_remote_browser_script_fails(self):
        path = self.root / "web/index.html"
        path.write_text(path.read_text() + '<script src="https://cdn.invalid/framework.js"></script>')
        with self.assertRaisesRegex(ValueError, "remote executable"):
            inspect(self.root)

    def test_unreviewed_remote_css_import_fails(self):
        path = self.root / "web/styles.css"
        path.write_text(path.read_text() + '@import "https://cdn.invalid/style.css";')
        with self.assertRaisesRegex(ValueError, "remote executable"):
            inspect(self.root)

    def test_missing_local_javascript_spdx_fails(self):
        path = self.root / "web/app.js"
        path.write_text(path.read_text().replace(
            "// SPDX-License-Identifier: AGPL-3.0-only", "/* unknown rights */"))
        with self.assertRaisesRegex(ValueError, "SPDX"):
            inspect(self.root)

    def test_missing_live_source_fails(self):
        (self.root / "src/audiohub").rename(self.root / "source-hidden")
        with self.assertRaisesRegex(ValueError, "missing"):
            inspect(self.root)

    def test_source_symlink_fails(self):
        target = self.root / "src/audiohub/pairing.py"
        outside = self.root / "external-pairing.py"
        outside.write_text(target.read_text())
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            inspect(self.root)


if __name__ == "__main__":
    unittest.main()
