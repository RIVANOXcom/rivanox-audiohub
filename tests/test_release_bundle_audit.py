"""Release preflight refuses forged and unverified distribution artifacts."""
import hashlib
import json
import lzma
import stat
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_bundle_audit import inspect, inspect_zip, main, REPORT_SCHEMA, MISSING_GATES
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
        db.write_text("Package: bluez\nStatus: install ok installed\nVersion: 1.0\nArchitecture: arm64\n")
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


    def make_operator_zip(self, *, extra=None, duplicate=False,
                          image_type=None, oversized=False):
        # An independent ZIP working folder; don't place the archive inside
        # the four-file fixture being checked by the original CI auditor.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "downloaded-operator.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for member in (self.image, self.checksum_path, self.meta_path,
                           self.dist / "ROOTFS-PACKAGES.json"):
                if member == self.image and image_type is not None:
                    info = zipfile.ZipInfo(member.name)
                    info.create_system = 3
                    info.external_attr = (image_type | 0o644) << 16
                    zf.writestr(info, member.read_bytes())
                elif member == self.meta_path and oversized:
                    zf.writestr(member.name, b"x" * 8193)
                else:
                    zf.write(member, arcname=member.name)
            if duplicate:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    zf.writestr("SHA256SUMS.txt", b"fake duplicate")
            if extra is not None:
                zf.writestr(extra, b"forbidden")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return path, digest

    def test_direct_downloaded_zip_verifies_outer_and_inner_then_no_go(self):
        path, digest = self.make_operator_zip()
        original = path.read_bytes()
        result = inspect_zip(path, expected_zip_sha256=digest,
                             expected_source_sha=self.SHA)
        self.assertEqual(result["bundle_integrity"], "passed")
        self.assertFalse(result["public_release_ready"])
        self.assertFalse(result["hardware_verified"])
        self.assertEqual(result["download_zip_sha256"], digest)
        self.assertEqual(result["verified_zip_entries"], 4)
        self.assertEqual(result["image_sha256"], self.meta["image_sha256"])
        self.assertEqual(path.read_bytes(), original)

    def test_zip_requires_both_explicit_exact_expected_hashes(self):
        path, digest = self.make_operator_zip()
        for bad in (None, "", "bad", digest.upper(), "a" * 63):
            with self.subTest(bad=bad), self.assertRaisesRegex(
                    ValueError, "ZIP SHA256"):
                inspect_zip(path, expected_zip_sha256=bad,
                            expected_source_sha=self.SHA)
        for bad in (None, "", "wrong", "a" * 39):
            with self.subTest(source=bad), self.assertRaisesRegex(
                    ValueError, "source SHA"):
                inspect_zip(path, expected_zip_sha256=digest,
                            expected_source_sha=bad)

    def test_wrong_zip_digest_is_refused_before_any_extraction(self):
        path, digest = self.make_operator_zip()
        with self.assertRaisesRegex(ValueError, "ZIP SHA256 mismatch"):
            inspect_zip(path, expected_zip_sha256="f" * 64,
                        expected_source_sha=self.SHA)
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "ZIP SHA256 mismatch"):
            inspect_zip(path, expected_zip_sha256=digest,
                        expected_source_sha=self.SHA)

    def test_matching_zip_but_wrong_source_head_is_rejected(self):
        path, digest = self.make_operator_zip()
        with self.assertRaisesRegex(ValueError, "Source revision mismatch"):
            inspect_zip(path, expected_zip_sha256=digest,
                        expected_source_sha="c" * 40)

    def test_zip_rejects_extra_traversal_and_nested_paths_even_if_sha_matches(self):
        for extra in ("../private-file", "inner/forbidden",
                      "/absolute", "unexpected-credentials.txt"):
            with self.subTest(extra=extra):
                path, digest = self.make_operator_zip(extra=extra)
                with self.assertRaisesRegex(ValueError, "exactly four"):
                    inspect_zip(path, expected_zip_sha256=digest,
                                expected_source_sha=self.SHA)

    def test_zip_rejects_duplicate_member_names_without_extraction(self):
        path, digest = self.make_operator_zip(duplicate=True)
        with self.assertRaisesRegex(ValueError, "exactly four"):
            inspect_zip(path, expected_zip_sha256=digest,
                        expected_source_sha=self.SHA)

    def test_zip_rejects_symlink_member_and_oversized_metadata(self):
        for kwargs in ({"image_type": stat.S_IFLNK}, {"oversized": True}):
            with self.subTest(kwargs=kwargs):
                path, digest = self.make_operator_zip(**kwargs)
                with self.assertRaisesRegex(ValueError, "Unsafe ZIP member"):
                    inspect_zip(path, expected_zip_sha256=digest,
                                expected_source_sha=self.SHA)

    def test_zip_rejects_symlinked_archive_without_following(self):
        path, digest = self.make_operator_zip()
        link = path.parent / "untrusted.zip"
        link.symlink_to(path)
        with self.assertRaisesRegex(ValueError, "regular files"):
            inspect_zip(link, expected_zip_sha256=digest,
                        expected_source_sha=self.SHA)

    def test_one_command_cli_accepts_valid_zip_and_outputs_explicit_no_go(self):
        path, digest = self.make_operator_zip()
        out = StringIO()
        with redirect_stdout(out):
            code = main(["--zip", str(path),
                         "--expected-zip-sha256", digest,
                         "--expected-source-sha", self.SHA])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["download_zip_sha256"], digest)
        self.assertFalse(result["public_release_ready"])
        self.assertEqual(result["classification"], "UNVERIFIED_ALPHA_TEST_ONLY")
        self.assertEqual(result["verified_zip_entries"], 4)

    def test_original_ci_extracted_bundle_mode_stays_unchanged(self):
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--directory", str(self.dist),
                                   "--expected-source-sha", self.SHA]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["bundle_integrity"], "passed")
        self.assertNotIn("download_zip_sha256", result)


if __name__ == "__main__":
    unittest.main()
