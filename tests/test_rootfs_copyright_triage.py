"""Tests for real-rootfs copyright gap triage and Debian shared-doc metadata."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rootfs_copyright_triage import analyze
from scripts.rootfs_package_inventory import write_inventory


class CopyrightTriageTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "rootfs"
        self.status = self.root / "var/lib/dpkg/status"
        self.status.parent.mkdir(parents=True)
        self.status.write_text(
            "Package: liba\nStatus: install ok installed\n"
            "Version: 1\nArchitecture: arm64\n"
            "Source: librarysuite (1)\nDepends: libb (>= 1)\n\n"
            "Package: libb\nStatus: install ok installed\n"
            "Version: 1\nArchitecture: arm64\n"
            "Source: librarysuite (1)\n\n"
            "Package: misc\nStatus: install ok installed\n"
            "Version: 2\nArchitecture: arm64\n"
        )
        docs = self.root / "usr/share/doc"
        (docs / "libb").mkdir(parents=True)
        (docs / "libb/copyright").write_text("License: MIT\n")
        (docs / "liba").symlink_to("libb", target_is_directory=True)
        self.report = self.root / "usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
        self.make_inventory()

    def make_inventory(self):
        write_inventory(self.root, self.report)

    def refresh(self):
        self.report.unlink()
        self.make_inventory()

    def test_detects_missing_document_and_valid_metadata_evidence(self):
        result = analyze(self.root, self.report)
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(result["unresolved"], [
            {"package": "misc", "reason": "doc_directory_missing"}])
        self.assertEqual(result["alias_relationship_counts"][
            "same_source_and_direct_dependency_declared"], 1)
        self.assertEqual(result["documented_directory_aliases"][0]["package"], "liba")
        self.assertFalse(result["all_aliases_proven_policy_compliant"])
        self.assertFalse(result["commercial_redistribution_approved"])

    def test_same_source_without_dep_is_not_assumed_policy_compliant(self):
        self.status.write_text(self.status.read_text().replace(
            "Depends: libb (>= 1)\n", "Depends: unrelated\n"))
        result = analyze(self.root, self.report)
        self.assertEqual(result["alias_relationship_counts"]["direct_dependency_not_verified"], 1)

    def test_foreign_source_alias_is_flagged(self):
        self.status.write_text(self.status.read_text().replace(
            "Source: librarysuite (1)\n\nPackage: misc",
            "Source: unrelated-package (1)\n\nPackage: misc"))
        result = analyze(self.root, self.report)
        self.assertEqual(result["alias_relationship_counts"]["source_mismatch"], 1)

    def test_missing_copyright_in_real_dir_is_explicit(self):
        path = self.root / "usr/share/doc/libb/copyright"
        path.unlink()
        self.refresh()
        result = analyze(self.root, self.report)
        self.assertEqual(result["unresolved_count"], 3)
        self.assertEqual(result["unresolved_reason_counts"]["copyright_file_missing"], 2)
        self.assertEqual(result["unresolved_reason_counts"]["doc_directory_missing"], 1)

    def test_symlinked_copyright_file_is_not_followed(self):
        real = self.root / "outside"
        real.write_text("private")
        doc = self.root / "usr/share/doc/libb/copyright"
        doc.unlink()
        doc.symlink_to(real)
        self.refresh()
        result = analyze(self.root, self.report)
        self.assertEqual(result["unresolved_reason_counts"]["copyright_file_symlink"], 2)
        self.assertNotIn("private", json.dumps(result))

    def test_host_escaping_alias_is_reported_without_target_leak(self):
        alias = self.root / "usr/share/doc/liba"
        alias.unlink()
        alias.symlink_to("/tmp/private-data")
        self.refresh()
        result = analyze(self.root, self.report)
        self.assertIn({"package": "liba", "reason": "unsafe_doc_directory_link"},
                      result["unresolved"])
        self.assertNotIn("/tmp/private-data", json.dumps(result))

    def test_malicious_hash_is_caught(self):
        obj = json.loads(self.report.read_text())
        for p in obj["packages"]:
            if p["name"] == "libb":
                p["copyright_sha256"] = "a" * 64
        self.report.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "hash differs"):
            analyze(self.root, self.report)

    def test_stale_inventory_after_copyright_file_change_fails(self):
        (self.root / "usr/share/doc/libb/copyright").write_text(
            "different upstream copyright\n")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            analyze(self.root, self.report)

    def test_forged_license_approval_is_refused(self):
        obj = json.loads(self.report.read_text())
        obj["legal_review_approved"] = True
        self.report.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "forged legal approval"):
            analyze(self.root, self.report)

    def test_alias_unknown_target_is_not_a_proven_relationship(self):
        self.status.write_text(
            "Package: liba\nStatus: install ok installed\n"
            "Version: 1\nArchitecture: arm64\n"
            "Depends: libb (>= 1)\n\n"
            "Package: misc\nStatus: install ok installed\n"
            "Version: 2\nArchitecture: arm64\n"
        )
        self.refresh()
        result = analyze(self.root, self.report)
        self.assertEqual(result["alias_relationship_counts"]["source_metadata_unavailable"], 1)

    def test_does_not_report_untrusted_stat_fields(self):
        result = analyze(self.root, self.report)
        text = json.dumps(result)
        self.assertNotIn("Maintainer", text)
        self.assertNotIn("Device", text)
        self.assertNotIn("Email", text)

    def test_exporter_carries_triage_without_new_public_bundle_file(self):
        from scripts.export_rootfs_inventory import export
        pi = self.root.parent / "pi-gen"
        final = pi / "work/123/stage-audiohub/rootfs"
        final.parent.mkdir(parents=True)
        shutil.copytree(self.root, final)
        (pi / "deploy").mkdir()
        out = export(pi)
        self.assertEqual(out["copyright_triage"]["unresolved_count"], 1)
        self.assertEqual(out["inventory_file"], "ROOTFS-PACKAGES.json")
        self.assertFalse(out["third_party_license_review_approved"])
        self.assertEqual(
            (pi / "deploy/ROOTFS-PACKAGES.json").read_bytes(),
            (final / "usr/share/doc/audiohub/ROOTFS-PACKAGES.json").read_bytes()
        )

    def test_stale_package_version_is_refused(self):
        self.status.write_text(self.status.read_text().replace(
            "Version: 2\\nArchitecture: arm64",
            "Version: 3\\nArchitecture: arm64"))
        with self.assertRaisesRegex(ValueError, "version differs"):
            analyze(self.root, self.report)

    def test_forged_inventory_package_version_is_refused(self):
        data = json.loads(self.report.read_text())
        data["packages"][-1]["version"] = "999.0"
        self.report.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "version differs"):
            analyze(self.root, self.report)

    def test_forged_inventory_architecture_is_refused(self):
        data = json.loads(self.report.read_text())
        data["packages"][-1]["architecture"] = "armhf"
        self.report.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "identities"):
            analyze(self.root, self.report)

    def test_unreported_installed_package_is_refused(self):
        self.status.write_text(self.status.read_text() +
            "\\nPackage: unreported\\nStatus: install ok installed\\n"
            "Version: 1\\nArchitecture: arm64\\n")
        with self.assertRaisesRegex(ValueError, "identities"):
            analyze(self.root, self.report)

    def test_removed_installed_package_is_refused(self):
        self.status.write_text(self.status.read_text().replace(
            "Package: misc\\nStatus: install ok installed\\n"
            "Version: 2\\nArchitecture: arm64\\n", ""))
        with self.assertRaisesRegex(ValueError, "identities"):
            analyze(self.root, self.report)

    def test_duplicate_same_architecture_package_is_refused(self):
        self.status.write_text(self.status.read_text() +
            "\\nPackage: libb\\nStatus: install ok installed\\n"
            "Version: 1\\nArchitecture: arm64\\n")
        with self.assertRaisesRegex(ValueError, "Duplicate package/architecture"):
            analyze(self.root, self.report)

    def test_same_binary_name_different_architecture_is_supported(self):
        self.status.write_text(self.status.read_text() +
            "\\nPackage: libb\\nStatus: install ok installed\\n"
            "Version: 1\\nArchitecture: armhf\\n"
            "Source: librarysuite (1)\\n")
        self.refresh()
        result = analyze(self.root, self.report)
        self.assertEqual(result["installed_packages"], 4)
        self.assertEqual(result["unresolved_count"], 1)

    def test_shared_doc_target_architecture_all_is_resolved(self):
        self.status.write_text(self.status.read_text().replace(
            "Package: libb\\nStatus: install ok installed\\n"
            "Version: 1\\nArchitecture: arm64",
            "Package: libb\\nStatus: install ok installed\\n"
            "Version: 1\\nArchitecture: all"))
        self.refresh()
        result = analyze(self.root, self.report)
        self.assertEqual(result["alias_relationship_counts"][
            "same_source_and_direct_dependency_declared"], 1)


if __name__ == "__main__":
    unittest.main()
