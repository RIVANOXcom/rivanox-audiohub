"""CI-level contract tests for temporary, deliberately unverified Pi images."""
import hashlib
import json
import lzma
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.preview_manifest import manifest


class PreviewBundleTests(unittest.TestCase):
    SHA = "a" * 40
    PIN = "b" * 40
    RUN = "41800000001"

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.path = Path(self.work.name)
        self.dist = self.path / "dist"
        self.dist.mkdir()
        self.build_script = self.path / "build-image.sh"
        self.build_script.write_text('#!/bin/bash\nPIN="' + self.PIN + '"\n')
        self.image = self.dist / "test-AudioHub-Pi4-UNVERIFIED.img.xz"
        self.image.write_bytes(lzma.compress(b"test image only"))
        self.checksum = self.dist / "SHA256SUMS.txt"
        self.write_checksum()

    def write_checksum(self):
        self.checksum.write_text(
            hashlib.sha256(self.image.read_bytes()).hexdigest() + "  " +
            self.image.name + "\n"
        )

    def create(self):
        return manifest(self.dist, self.SHA, self.RUN, self.build_script)

    def test_manifest_records_exact_source_pin_and_verifiable_checksum(self):
        data = self.create()
        self.assertEqual(data["schema"], "rivanox-audiohub-preview-bundle/1")
        self.assertEqual(data["source_commit_sha"], self.SHA)
        self.assertEqual(data["pi_gen_commit_sha"], self.PIN)
        self.assertEqual(data["github_actions_run_id"], self.RUN)
        self.assertEqual(data["image"], self.image.name)
        self.assertEqual(data["image_sha256"],
                         hashlib.sha256(self.image.read_bytes()).hexdigest())
        self.assertEqual(data["image_bytes"], self.image.stat().st_size)
        self.assertEqual(json.loads((self.dist / "PREVIEW-MANIFEST.json").read_text()), data)

    def test_never_marks_release_hardware_or_wifi_setup_ready(self):
        data = self.create()
        self.assertIs(data["hardware_verified"], False)
        self.assertIs(data["release_approved"], False)
        self.assertIs(data["supports_phone_wifi_setup"], False)
        self.assertIn("not a release", data["scope"])

    def test_rejects_mismatching_digest(self):
        self.image.write_bytes(lzma.compress(b"modified after hash"))
        with self.assertRaisesRegex(ValueError, "digest"):
            self.create()
        self.assertFalse((self.dist / "PREVIEW-MANIFEST.json").exists())

    def test_rejects_missing_or_multiple_image(self):
        second = self.dist / "another.img.xz"
        second.write_bytes(b"not compressed")
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            self.create()
        second.unlink()
        self.image.unlink()
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            self.create()

    def test_rejects_image_symlink(self):
        original = self.path / "external.img.xz"
        original.write_bytes(self.image.read_bytes())
        self.image.unlink()
        self.image.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "regular compressed"):
            self.create()

    def test_rejects_invalid_sha_or_run_id(self):
        for sha, run in (("branch", self.RUN), (self.SHA, "NaN"),
                         ("c" * 39, self.RUN), (self.SHA, "-1")):
            with self.subTest(sha=sha, run=run), self.assertRaisesRegex(
                ValueError, "Invalid source"
            ):
                manifest(self.dist, sha, run, self.build_script)

    def test_rejects_unpinned_pi_gen_builder(self):
        self.build_script.write_text('#!/bin/bash\nPIN="main"\n')
        with self.assertRaisesRegex(ValueError, "Pinned"):
            self.create()

    def test_rejects_existing_manifest_instead_of_overwriting(self):
        self.create()
        original = (self.dist / "PREVIEW-MANIFEST.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.create()
        self.assertEqual(original, (self.dist / "PREVIEW-MANIFEST.json").read_bytes())

    def test_rejects_missing_or_symlinked_checksum(self):
        self.checksum.unlink()
        with self.assertRaisesRegex(ValueError, "Missing checksum"):
            self.create()
        external = self.path / "external-checksum"
        external.write_text("not valid")
        self.checksum.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "Missing checksum"):
            self.create()

    def test_workflow_contract_is_artifact_not_github_release(self):
        workflow = (ROOT / ".github/workflows/build-image-preview.yml").read_text()
        self.assertIn("retention-days: 30", workflow)
        self.assertIn("id: preview_artifact", workflow)
        self.assertIn("artifact-url", workflow)
        self.assertIn("dist/PREVIEW-MANIFEST.json", workflow)
        self.assertIn("scripts/preview_manifest.py", workflow)
        self.assertIn("UNVERIFIED", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("softprops/action-gh-release", workflow)
        self.assertNotIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
