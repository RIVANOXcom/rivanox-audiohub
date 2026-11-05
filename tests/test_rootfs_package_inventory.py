"""Offline tests for reproducible, redacted rootfs package inventory."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rootfs_package_inventory import inventory, write_inventory, SCHEMA


class RootfsPackageInventoryTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / "rootfs"
        (self.root / "var/lib/dpkg").mkdir(parents=True)
        self.status = self.root / "var/lib/dpkg/status"
        self.status.write_text(
            "Package: pipewire\nStatus: install ok installed\n"
            "Version: 1.2.3-1+deb13u1\nArchitecture: arm64\n"
            "Maintainer: Private Person <private@example.invalid>\n\n"
            "Package: bluez\nStatus: install ok installed\n"
            "Version: 5.81-1\nArchitecture: arm64\n\n"
            "Package: notinstalled\nStatus: deinstall ok config-files\n"
            "Version: 1.0\nArchitecture: arm64\n"
        )
        doc = self.root / "usr/share/doc/pipewire"
        doc.mkdir(parents=True)
        (doc / "copyright").write_text("Copyright 2026 Sample; License: MIT\n")
        self.dest = self.root / "usr/share/doc/audiohub/ROOTFS-PACKAGES.json"

    def test_deterministic_filtered_inventory(self):
        result = inventory(self.root)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertIs(result["legal_review_approved"], False)
        self.assertEqual(result["summary"], {
            "installed_packages": 2,
            "copyright_files_available": 1,
            "copyright_files_missing": 1,
        })
        self.assertEqual([p["name"] for p in result["packages"]], ["bluez", "pipewire"])
        self.assertIsNone(result["packages"][0]["copyright_sha256"])
        self.assertEqual(
            result["packages"][1]["copyright_sha256"],
            hashlib.sha256(b"Copyright 2026 Sample; License: MIT\n").hexdigest(),
        )
        self.assertNotIn("private@", json.dumps(result))
        self.assertNotIn("Maintainer", json.dumps(result))
        self.assertNotIn("notinstalled", json.dumps(result))

    def test_persistent_deterministic_output(self):
        first = write_inventory(self.root, self.dest)
        content = self.dest.read_bytes()
        second = write_inventory(self.root, self.dest)
        self.assertEqual(first, second)
        self.assertEqual(content, self.dest.read_bytes())
        self.assertEqual(json.loads(content), first)

    def test_rejects_missing_or_empty_database(self):
        self.status.unlink()
        with self.assertRaises(ValueError):
            inventory(self.root)
        self.status.write_text("Package: foo\nStatus: deinstall ok config-files\n")
        with self.assertRaisesRegex(ValueError, "No installed"):
            inventory(self.root)

    def test_rejects_path_traversal_package(self):
        self.status.write_text(
            "Package: ../../etc\nStatus: install ok installed\n"
            "Version: 1\nArchitecture: arm64\n"
        )
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            inventory(self.root)

    def test_rejects_duplicated_package(self):
        content = self.status.read_text()
        self.status.write_text(content + "\nPackage: bluez\nStatus: install ok installed\n"
                               "Version: 1\nArchitecture: arm64\n")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            inventory(self.root)

    def test_rejects_duplicated_control_field(self):
        self.status.write_text(
            "Package: pipewire\nPackage: bluez\nStatus: install ok installed\n"
            "Version: 1\nArchitecture: arm64\n"
        )
        with self.assertRaisesRegex(ValueError, "repeated"):
            inventory(self.root)

    def test_refuses_symlinked_copyright_without_host_data_leak(self):
        outside = self.root.parent / "private-data"
        outside.write_text("PRIVATE SECRET")
        doc = self.root / "usr/share/doc/pipewire/copyright"
        doc.unlink()
        doc.symlink_to(outside)
        result = inventory(self.root)
        self.assertIsNone(result["packages"][1]["copyright_sha256"])
        self.assertNotIn("PRIVATE SECRET", json.dumps(result))

    def test_refuses_symlinked_status_or_output(self):
        external = self.root.parent / "status-backup"
        external.write_text(self.status.read_text())
        self.status.unlink()
        self.status.symlink_to(external)
        with self.assertRaises(ValueError):
            inventory(self.root)
        self.status.unlink()
        self.status.write_text(external.read_text())
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "Unsafe inventory"):
            write_inventory(self.root, self.dest)

    def test_no_fake_license_assertions(self):
        result = inventory(self.root)
        self.assertNotIn("license", result["packages"][0])
        self.assertNotIn("compliant", json.dumps(result))
        self.assertFalse(result["legal_review_approved"])


if __name__ == "__main__":
    unittest.main()
