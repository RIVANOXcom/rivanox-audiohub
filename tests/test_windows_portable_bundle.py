"""Reproducible, credential-free offline Windows alpha ZIP tests."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import package_windows_bridge as package

SHA = "b" * 40


class WindowsPortableBundleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = Path(self.folder.name)
        self.prefix = "AudioHub-Windows-TLS-Bridge-ALPHA-" + SHA[:12]

    def _build(self, folder=None):
        folder = self.out if folder is None else folder
        record = package.build(ROOT, folder, SHA)
        return record, folder / record["file"]

    def test_package_contains_only_owned_source_docs_not_secrets_or_drivers(self):
        record, archive_path = self._build()
        self.assertEqual(record["source_sha"], SHA)
        self.assertEqual(record["classification"], "UNVERIFIED_ALPHA_TEST_ONLY")
        self.assertTrue(zipfile.is_zipfile(archive_path))
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIsNone(archive.testzip())
            paths = archive.namelist()
            allowed = {dest for source, dest in package.FILES}
            self.assertEqual(
                {p.split("/", 1)[1] for p in paths},
                allowed | {"SOURCE-MANIFEST.json"})
            self.assertEqual(len(paths), len(set(paths)))
            self.assertTrue(all(p.startswith(self.prefix + "/") for p in paths))
            self.assertFalse(any(p.endswith((".key", ".crt", ".pfx", ".exe", ".dll"))
                                 for p in paths))
            manifest = json.loads(
                archive.read(self.prefix + "/SOURCE-MANIFEST.json"))
            self.assertEqual(manifest["source_sha"], SHA)
            self.assertFalse(manifest["credentials_included"])
            self.assertTrue(manifest["offline_certificate_sha256_verification"])
            self.assertFalse(manifest["trust_on_first_use"])
            self.assertTrue(manifest["offline_psk_copy_comparison_available"])
            self.assertTrue(manifest["offline_key_code_not_authentication"])
            self.assertIn(self.prefix + "/audiohub/key_onboarding.py", paths)
            self.assertIn(self.prefix + "/audiohub/certificate_onboarding.py", paths)
            self.assertFalse(manifest["driver_included"])
            self.assertTrue(manifest["driverless_speaker_soundcheck_available"])
            self.assertEqual(manifest["speaker_channel_soundcheck"],
                             ["both", "left", "right", "sequence"])
            self.assertFalse(manifest["windows_scream_driver_required_for_soundcheck"])
            self.assertFalse(manifest["hardware_verified"])
            self.assertFalse(manifest["public_release_ready"])
            self.assertTrue(manifest["local_operator_observation_json"])
            self.assertTrue(manifest["manual_observation_not_hardware_approval"])
            self.assertIn(self.prefix + "/audiohub/hardware_observation.py", paths)
            self.assertIn(self.prefix + "/audiohub/windows_bridge_gui.py", paths)
            for name, item in manifest["source_files"].items():
                payload = archive.read(self.prefix + "/" + name)
                self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())
        expected_sums = record["sha256"] + "  " + archive_path.name + "\n"
        self.assertEqual((self.out / "SHA256SUMS-WINDOWS.txt").read_text(),
                         expected_sums)

    def test_same_source_and_sha_produce_bit_identical_zip(self):
        first, _ = self._build()
        second_dir = self.out / "second"
        second, _ = self._build(second_dir)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["files"], second["files"])

    def test_extracted_starter_runs_offline_without_linux_fcntl(self):
        _, archive = self._build()
        with zipfile.ZipFile(archive) as z:
            z.extractall(self.out / "extracted")
        root = self.out / "extracted" / self.prefix
        code = (
            'import sys, runpy; sys.modules["fcntl"] = None; '
            'sys.argv = ["START-WINDOWS-BRIDGE.py", "--self-check"]; '
            'runpy.run_path("START-WINDOWS-BRIDGE.py", run_name="__main__")'
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No keys, driver, network", proc.stdout)

    def test_crlf_windows_checkout_yields_exact_same_sha_as_lf(self):
        linux, _ = self._build()
        root = self.out / "windows-crlf-fixture"
        for source, _ in package.FILES:
            target = root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (ROOT / source).read_bytes().replace(b"\r\n", b"\n")
            target.write_bytes(data.replace(b"\n", b"\r\n"))
        windows_dir = self.out / "windows-artifact"
        win = package.build(root, windows_dir, SHA)
        self.assertEqual(linux["sha256"], win["sha256"])

    def test_refuses_bad_sha_and_overwrite(self):
        for value in ("main", "B" * 40, "a" * 39, "a" * 41, "../a"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                package.validate_source_sha(value)
        self._build()
        with self.assertRaises(FileExistsError):
            self._build()

    def test_symlinked_source_file_fails_closed(self):
        root = self.out / "fixture"
        for source, _ in package.FILES:
            dest = root / source
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, dest)
        victim = root / "src/audiohub/secure_lan.py"
        victim.unlink()
        try:
            victim.symlink_to(ROOT / "src/audiohub/secure_lan.py")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "symlink"):
            package.build(root, self.out / "symlinked", SHA)


if __name__ == "__main__":
    unittest.main()
