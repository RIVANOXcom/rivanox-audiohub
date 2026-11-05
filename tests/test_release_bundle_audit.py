"""Release preflight refuses forged and unverified distribution artifacts."""
import hashlib
import json
import lzma
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_bundle_audit import inspect, REPORT_SCHEMA, MISSING_GATES
from scripts.rootfs_package_inventory import write_inventory
from scripts.verify_package_inventory import verify as verify_inventory


class ReleaseBundlePreflightTests(unittest.TestCase):
    SHA = "a" * 40
    PIN = "b" * 40
    RUN = "42086909475"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dist = Path(tmp.name)
        self.image = self.dist / "image_2026-11-05-AudioHub-Pi4-UNVERIFIED.img.xz"
        self.image.write_bytes(lzma.compress(b"offline sample, not a real pi image"))
        self.meta_path = self.dist / "PREVIEW-MANIFEST.json"
        self.checksum_path = self.dist / "SHA256SUMS.txt"
        self.make_inventory()
        self.write_manifest()

    def make_inventory(self):
        rootfs = self.dist / "_temp-rootfs"
        db = rootfs / "var/lib/dpkg/status"
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_text("Package: bluez\\nStatus: install ok installed\\nVersion: 1.0\\nArchitecture: arm64\\n")
        write_inventory(rootfs, self.dist / "ROOTFS-PACKAGES.json")
        import shutil
        shutil.rmtree(rootfs)

    def write_manifest(self):
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.meta = {
            "schema": "rivanox-audiohub-preview-bundle/2",
            "package_inventory": {"file": "ROOTFS-PACKAGES.json", **verify_inventory(self.dist / "ROOTFS-PACKAGES.json")},
            "image": self.image.name,
            "image_bytes": self.image.stat().st_size,
            "image_sha256": digest,
            "source_commit_sha": self.SHA,
            "pi_gen_commit_sha": self.PIN,
            "github_actions_run_id": self.RUN,
            "hardware_verified": False,
            "release_approved": False,
            "supports_phone_wifi_setup": False,
            "scope": "Temporary development artifact only; not a release",
        }
        self.meta_path.write_text(json.dumps(self.meta))
        self.checksum_path.write_text(f"{digest}  {self.image.name}\n")

    def audit(self):
        return inspect(self.dist, expected_source_sha=self.SHA)

    def test_valid_archive_integrity_never_authorizes_release(self):
        result = self.audit()
        self.assertEqual(result["bundle_integrity"], "passed")
        self.assertEqual(result["schema"], REPORT_SCHEMA)
        self.assertFalse(result["public_release_ready"])
        self.assertFalse(result["hardware_verified"])
        self.assertEqual(result["source_sha"], self.SHA)
        self.assertEqual(result["image_sha256"], self.meta["image_sha256"])
        self.assertEqual(result["installed_packages"], 1)
        self.assertEqual(result["missing_human_gates"], list(MISSING_GATES))

    def test_rejects_changed_source_ref(self):
        with self.assertRaisesRegex(ValueError, "Source revision"):
            inspect(self.dist, expected_source_sha="c" * 40)

    def test_rejects_fake_hardware_approval(self):
        for flag in ("hardware_verified", "release_approved", "supports_phone_wifi_setup"):
            self.write_manifest()
            self.meta[flag] = True
            self.meta_path.write_text(json.dumps(self.meta))
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "may not claim"):
                self.audit()

    def test_rejects_bad_release_scope(self):
        self.meta["scope"] = "OFFICIAL RELEASE"
        self.meta_path.write_text(json.dumps(self.meta))
        with self.assertRaisesRegex(ValueError, "may not claim"):
            self.audit()

    def test_no_secret_or_sidecar_attachments_in_bundle(self):
        (self.dist / "wifi-credentials.txt").write_text("SHOULD NEVER LEAK")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.audit()

    def test_image_tampering_rejected_even_if_manifest_is_unchanged(self):
        self.image.write_bytes(lzma.compress(b"changed after checksum"))
        with self.assertRaisesRegex(ValueError, "Image identity/size|Image checksum"):
            self.audit()

    def test_rejects_replaced_package_inventory(self):
        path = self.dist / "ROOTFS-PACKAGES.json"
        data = json.loads(path.read_text())
        data["packages"][0]["version"] = "2.0"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.audit()

    def test_rejects_leaked_credentials_in_package_inventory(self):
        path = self.dist / "ROOTFS-PACKAGES.json"
        data = json.loads(path.read_text())
        data["wifi_password"] = "secret"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            self.audit()

    def test_rejects_forged_legal_signoff(self):
        path = self.dist / "ROOTFS-PACKAGES.json"
        data = json.loads(path.read_text())
        data["legal_review_approved"] = True
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "forged legal approval"):
            self.audit()

    def test_rejects_symlinked_package_inventory(self):
        path = self.dist / "ROOTFS-PACKAGES.json"
        outside = self.dist.parent / (self.dist.name + "-pkg.json")
        outside.write_bytes(path.read_bytes())
        self.addCleanup(outside.unlink)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "link"):
            self.audit()

    def test_checksum_file_with_extra_lines_rejected(self):
        with self.checksum_path.open("a") as stream:
            stream.write("c" * 64 + "  ./another.img\n")
        with self.assertRaisesRegex(ValueError, "Checksum line"):
            self.audit()

    def test_corrupted_xz_rejected_despite_consistent_hashes(self):
        self.image.write_bytes(b"NOT_AN_XZ_STREAM")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "XZ decompression"):
            self.audit()

    def test_manifest_source_sha_is_strict(self):
        self.meta["source_commit_sha"] = "main"
        self.meta_path.write_text(json.dumps(self.meta))
        with self.assertRaisesRegex(ValueError, "Invalid artifact"):
            self.audit()

    def test_symlink_manifest_is_refused(self):
        outside = self.dist.parent / (self.dist.name + "-manifest.json")
        outside.write_text(self.meta_path.read_text())
        self.addCleanup(outside.unlink)
        self.meta_path.unlink()
        self.meta_path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "regular"):
            self.audit()

    def test_symlink_image_is_refused(self):
        outside = self.dist.parent / (self.dist.name + "-image.img.xz")
        outside.write_bytes(self.image.read_bytes())
        self.addCleanup(outside.unlink)
        self.image.unlink()
        self.image.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "regular"):
            self.audit()

    def test_image_bundle_missing_checksum_is_refused(self):
        self.checksum_path.unlink()
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.audit()

    def test_empty_or_unexpected_image_name_is_refused(self):
        self.image.rename(self.dist / "UNVERIFIED.img.xz")
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            self.audit()

    def test_forged_multiple_images_refused(self):
        (self.dist / "another-UNVERIFIED.img.xz").write_bytes(self.image.read_bytes())
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            self.audit()

    def test_policy_does_not_expose_public_release_step(self):
        workflow = (ROOT / ".github/workflows/publish-image.yml").read_text()
        self.assertIn("No hardware-verified Pi image", workflow)
        self.assertIn("exit 1", workflow)
        self.assertNotIn("contents: write", workflow)
        script = (ROOT / "scripts/release_bundle_audit.py").read_text()
        self.assertNotIn("gh release create", script)
        self.assertNotIn("subprocess.run", script)


if __name__ == "__main__":
    unittest.main()
