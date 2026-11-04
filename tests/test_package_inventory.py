"""Regression tests for source-only package inventory and license holds."""
import io
import contextlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import package_inventory as inv


class PackageInventoryTests(unittest.TestCase):
    def test_all_current_source_packages_reported_not_licensed(self):
        report = inv.probe_repo(ROOT)
        self.assertEqual(report["package_count"], 15)
        self.assertEqual(len({p["package"] for p in report["packages"]}), 15)
        self.assertTrue(report["source_inventory_consistent"])
        self.assertEqual(len(report["pi_gen_source_pin"]), 40)
        self.assertFalse(report["license_audit_accepted"])
        self.assertFalse(report["release_ready"])
        self.assertTrue(all(p["resolved_version"] is None for p in report["packages"]))
        self.assertTrue(all(not p["license_verified"] for p in report["packages"]))

    def test_unknown_extra_dependency_never_counts_as_reviewed(self):
        source = "bluez\nnew-package\n"
        notices = "| BlueZ | Bluetooth stack | details |"
        build = 'PIN="' + "a" * 40 + '"'
        report = inv.inspect_source(source, notices, build)
        self.assertFalse(report["source_inventory_consistent"])
        self.assertEqual(report["missing_notice_reference"], ["new-package"])
        self.assertFalse(report["release_ready"])

    def test_absent_upstream_notice_not_silently_accepted(self):
        report = inv.inspect_source("bluez\npipewire", "| BlueZ | stack | link |",
                                    'PIN="' + "a" * 40 + '"')
        self.assertEqual(report["missing_notice_reference"], ["pipewire"])
        self.assertFalse(report["source_inventory_consistent"])

    def test_missing_or_ambiguous_pi_gen_pin_blocks_inventory(self):
        for line in ("PIN=latest", "", 'PIN="' + "a" * 40 + '"\nPIN="' + "b" * 40 + '"'):
            with self.subTest(line=line):
                report = inv.inspect_source("bluez", "| BlueZ | x | x |", line)
                self.assertIsNone(report["pi_gen_source_pin"])
                self.assertFalse(report["source_inventory_consistent"])

    def test_source_package_parser_rejects_shell_and_duplicate_entries(self):
        for text in ("", "  # only comments\n", "bluez\nbluez\n",
                     "bluez $(uname -a)", "bluez;rm -rf /", "Foo_Bar\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                inv.package_names(text)

    def test_sorted_comments_and_empty_lines(self):
        self.assertEqual(inv.package_names("jq\n\n# comment\nbluez\n"),
                         ["bluez", "jq"])

    def test_source_level_report_does_not_infer_transitive_dependencies(self):
        report = inv.probe_repo(ROOT)
        self.assertEqual(report["assessment"], "source_declarations_only_not_sbom")
        self.assertIn("complete_transitive_dependencies", report["missing_release_evidence"])
        self.assertIn("installed_debian_copyright_files", report["missing_release_evidence"])

    def test_cli_never_approves_release_even_if_source_inventory_consistent(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(inv.main(), 0)
        parsed = json.loads(stdout.getvalue())
        self.assertFalse(parsed["license_audit_accepted"])
        self.assertFalse(parsed["release_ready"])

    @mock.patch("audiohub.package_inventory.probe_repo", side_effect=OSError("missing"))
    def test_cli_responds_to_missing_files_without_approval(self, probe):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(inv.main(), 2)
        self.assertFalse(json.loads(stdout.getvalue())["release_ready"])


if __name__ == "__main__":
    unittest.main()
