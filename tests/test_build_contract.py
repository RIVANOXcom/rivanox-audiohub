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

    def test_current_operator_download_is_not_historical_or_four_file_only(self):
        readme = (ROOT / "README.md").read_text()
        download = readme.split("## Downloads and development status", 1)[1].split(
            "### Engineering priorities", 1
        )[0]
        distribution = (ROOT / "docs/RELEASE-DISTRIBUTION.md").read_text()
        current = distribution.split("## What exists now", 1)[1].split(
            "## Separate owner-controlled public Release process", 1
        )[0]
        status = (ROOT / "docs/STATUS.md").read_text()
        self.assertIn("https://github.com/RIVANOXcom/rivanox-audiohub/pull/304", download)
        self.assertIn("completed/success", download)
        self.assertIn("AUDIOHUB-OFFLINE-REPORT-VIEWER.html", download)
        self.assertIn("safe shutdown method", download)
        self.assertIn("original SD", download)
        self.assertIn("all** owned", download)
        self.assertNotIn("latest CI-validated experimental Pi4 image", download)
        self.assertNotIn("PR #30", download)
        self.assertIn("five allowlisted flat files", current)
        self.assertIn("four legacy or five current", current)
        self.assertIn("ROOTFS-PACKAGES.json", current)
        self.assertIn("AUDIOHUB-OFFLINE-REPORT-VIEWER.html", current)
        self.assertNotIn("Only four expected flat entries", current)
        self.assertIn("four legacy or five current", status)
        self.assertNotIn("latest prior-to-renaming run", status)

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
