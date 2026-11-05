"""Verify the image's rootfs inventory reaches deploy, never as release approval."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.export_rootfs_inventory import export
from scripts.rootfs_package_inventory import write_inventory
from scripts.verify_package_inventory import verify


class RootfsExportTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.pi = Path(holder.name) / "pi-gen"
        self.work = self.pi / "work"
        self.deploy = self.pi / "deploy"
        self.deploy.mkdir(parents=True)
        self.stage = self.work / "2026-11-05" / "stage-audiohub" / "rootfs"
        self.stage.mkdir(parents=True)
        status = self.stage / "var/lib/dpkg/status"
        status.parent.mkdir(parents=True)
        status.write_text(
            "Package: bluez\nStatus: install ok installed\n"
            "Version: 5.80-1\nArchitecture: arm64\n\n"
            "Package: pipewire\nStatus: install ok installed\n"
            "Version: 1.3.3-2\nArchitecture: arm64\n"
        )
        local = self.stage / "usr/share/doc/pipewire"
        local.mkdir(parents=True)
        (local / "copyright").write_text("License: MIT\n")
        self.src = self.stage / "usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
        write_inventory(self.stage, self.src)

    def test_exports_exact_real_stage_inventory_with_sha(self):
        proof = export(self.pi)
        target = self.deploy / "ROOTFS-PACKAGES.json"
        self.assertEqual(target.read_bytes(), self.src.read_bytes())
        self.assertEqual(proof["inventory_sha256"],
                         verify(target)["package_inventory_sha256"])
        self.assertEqual(proof["installed_packages"], 2)
        self.assertEqual(proof["copyright_files_missing"], 1)
        self.assertEqual(proof["unresolved_copyright_packages"], ["bluez"])
        self.assertFalse(proof["third_party_license_review_approved"])
        self.assertFalse(proof["public_release_approved"])

    def test_missing_inventory_is_fail_closed(self):
        self.src.unlink()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            export(self.pi)
        self.assertFalse((self.deploy / "ROOTFS-PACKAGES.json").exists())

    def test_ambiguous_stage_build_is_fail_closed(self):
        duplicate = self.work / "old" / "stage-audiohub" / "rootfs/usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
        duplicate.parent.mkdir(parents=True)
        shutil.copyfile(self.src, duplicate)
        with self.assertRaisesRegex(ValueError, "found 2"):
            export(self.pi)
        self.assertFalse((self.deploy / "ROOTFS-PACKAGES.json").exists())

    def test_rejects_invalid_inventory_before_deploy(self):
        data = json.loads(self.src.read_text())
        data["legal_review_approved"] = True
        self.src.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "forged legal approval"):
            export(self.pi)
        self.assertFalse((self.deploy / "ROOTFS-PACKAGES.json").exists())

    def test_rejects_existing_deploy_without_overwrite(self):
        target = self.deploy / "ROOTFS-PACKAGES.json"
        target.write_text("do not overwrite")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            export(self.pi)
        self.assertEqual(target.read_text(), "do not overwrite")

    def test_rejects_symlinked_deploy(self):
        real = self.pi / "elsewhere"
        real.mkdir()
        self.deploy.rmdir()
        self.deploy.symlink_to(real)
        with self.assertRaisesRegex(ValueError, "Untrusted"):
            export(self.pi)
        self.assertFalse((real / "ROOTFS-PACKAGES.json").exists())

    def test_rejects_symlinked_stage_inventory(self):
        src_copy = self.stage / "source-copy"
        shutil.copyfile(self.src, src_copy)
        self.src.unlink()
        self.src.symlink_to(src_copy)
        with self.assertRaisesRegex(ValueError, "symlink"):
            export(self.pi)
        self.assertFalse((self.deploy / "ROOTFS-PACKAGES.json").exists())

    def test_rejects_symlinked_stage_directory(self):
        rootfs = self.work / "2026-11-05" / "stage-audiohub"
        real = self.work / "real-stage"
        rootfs.rename(real)
        rootfs.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            export(self.pi)

    def test_does_not_use_older_stage2_rootfs(self):
        self.src.unlink()
        wrong = self.work / "2026-11-05" / "stage2/rootfs/usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
        wrong.parent.mkdir(parents=True)
        wrong.write_text("unrelated")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            export(self.pi)

    def test_rejects_symlinked_existing_destination(self):
        target = self.deploy / "ROOTFS-PACKAGES.json"
        stolen = self.pi / "outside"
        stolen.write_text("sentinel")
        target.symlink_to(stolen)
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            export(self.pi)
        self.assertEqual(stolen.read_text(), "sentinel")


if __name__ == "__main__":
    unittest.main()
