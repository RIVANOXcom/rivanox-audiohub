"""Check that a preview build matches the pinned pi-gen external contract."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ImageBuildContractTests(unittest.TestCase):
    def test_host_toolchain_uses_pi_gen_compatible_qemu_command(self):
        script=(ROOT / "build-image.sh").read_text()
        workflow=(ROOT / ".github/workflows/build-image-preview.yml").read_text()
        self.assertIn("qemu-aarch64 parted",script)
        self.assertIn("qemu-user-binfmt",workflow)
        self.assertNotIn("qemu-user-static debootstrap",workflow)

    def test_custom_stage_package_and_install_runners(self):
        stage=ROOT/"image"/"stage-audiohub"
        self.assertTrue((stage/"00-packages"/"00-packages-nr").is_file())
        self.assertTrue((stage/"01-install"/"00-run.sh").is_file())
        self.assertTrue((stage/"prerun.sh").is_file())
        self.assertTrue((stage/"EXPORT_IMAGE").is_file())
        self.assertIn("stage-audiohub", (ROOT / "build-image.sh").read_text())

    def test_public_stable_release_remains_blocked(self):
        workflow=(ROOT/".github/workflows/publish-image.yml").read_text()
        self.assertIn("No hardware-verified Pi image",workflow)
        self.assertIn("exit 1",workflow)

    def test_rootfs_license_inventory_is_exported_from_real_final_stage(self):
        image_builder = (ROOT / "build-image.sh").read_text()
        exporter = (ROOT / "scripts/export_rootfs_inventory.py").read_text()
        workflow = (ROOT / ".github/workflows/build-image-preview.yml").read_text()
        self.assertIn('scripts/export_rootfs_inventory.py', image_builder)
        self.assertIn('--pi-gen-root "$WORK/pi-gen"', image_builder)
        self.assertIn('ROOTFS-PACKAGES.json', exporter)
        self.assertIn('stage-audiohub', exporter)
        self.assertIn('dist/ROOTFS-PACKAGES.json', workflow)
        self.assertIn('scripts/release_bundle_audit.py', workflow)
        self.assertNotIn("gh release create", workflow)

if __name__ == "__main__":
    unittest.main()
