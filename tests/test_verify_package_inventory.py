"""Reject false legal, privacy and provenance claims in public ZIP inventories."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rootfs_package_inventory import write_inventory
from scripts.verify_package_inventory import verify


class InventoryExportSafetyTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / "root"
        status = self.root / "var/lib/dpkg/status"
        status.parent.mkdir(parents=True)
        status.write_text(
            "Package: bluez\nStatus: install ok installed\n"
            "Version: 5.80-1\nArchitecture: arm64\n"
        )
        self.bundle = Path(holder.name) / "ROOTFS-PACKAGES.json"
        write_inventory(self.root, self.bundle)

    def edit(self, change):
        obj = json.loads(self.bundle.read_text())
        change(obj)
        self.bundle.write_text(json.dumps(obj))

    def test_good_public_inventory_is_strictly_counted(self):
        proof = verify(self.bundle)
        self.assertEqual(proof["installed_packages"], 1)
        self.assertEqual(proof["copyright_files_missing"], 1)
        self.assertRegex(proof["package_inventory_sha256"], r"^[a-f0-9]{64}$")

    def test_refuses_unexpected_metadata_or_secrets(self):
        self.edit(lambda data: data.update({"hostname": "owner-private-host"}))
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            verify(self.bundle)

    def test_refuses_fake_legal_approval(self):
        self.edit(lambda data: data.update({"legal_review_approved": True}))
        with self.assertRaisesRegex(ValueError, "forged legal approval"):
            verify(self.bundle)

    def test_refuses_missing_count_forgery(self):
        self.edit(lambda data: data["summary"].update({"copyright_files_missing": 0}))
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            verify(self.bundle)

    def test_refuses_unexpected_package_fields(self):
        self.edit(lambda data: data["packages"][0].update({"maintainer": "someone@private.invalid"}))
        with self.assertRaisesRegex(ValueError, "secret-bearing"):
            verify(self.bundle)

    def test_refuses_unsorted_duplicate_package(self):
        self.edit(lambda data: data["packages"].append(data["packages"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify(self.bundle)

    def test_refuses_bad_package_version(self):
        self.edit(lambda data: data["packages"][0].update({"version": "../../secret"}))
        with self.assertRaisesRegex(ValueError, "identity"):
            verify(self.bundle)

    def test_refuses_symlink_to_arbitrary_host_file(self):
        second = self.bundle.parent / "external"
        second.write_bytes(self.bundle.read_bytes())
        self.bundle.unlink()
        self.bundle.symlink_to(second)
        with self.assertRaisesRegex(ValueError, "link"):
            verify(self.bundle)

    def test_build_pipeline_is_read_only_preview_and_contains_inventory(self):
        image_builder = (ROOT / "build-image.sh").read_text()
        stage = (ROOT / "image/stage-audiohub/02-audit/00-run.sh").read_text()
        preview = (ROOT / ".github/workflows/build-image-preview.yml").read_text()
        publisher = (ROOT / ".github/workflows/publish-image.yml").read_text()
        self.assertIn("rootfs_package_inventory.py", image_builder)
        self.assertIn("rootfs_package_inventory.py", stage)
        self.assertIn("ROOTFS-PACKAGES.json", preview)
        self.assertIn("scripts/release_bundle_audit.py", preview)
        self.assertIn("contents: read", preview)
        self.assertIn("exit 1", publisher)
        self.assertNotIn("contents: write", publisher)


if __name__ == "__main__":
    unittest.main()
