"""Offline privacy and operator-evidence rules. No Pi/audio hardware required."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import hardware_observation as report

UTC = "2026-11-09T12:00:00+00:00"
SOURCE_SHA = "a" * 40


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def record(self, **updates):
        args = dict(
            channel="sequence", outcome="completed", frames=500,
            left="heard_expected", right="heard_expected", listened=True,
            source_sha=SOURCE_SHA, recorded_utc=UTC,
        )
        args.update(updates)
        return report.build_observation(**args)

    def test_real_human_inputs_remain_unverified_even_when_both_heard(self):
        result = self.record()
        self.assertEqual(result["classification"], "UNVERIFIED_HUMAN_OBSERVATION")
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["release_ready"])
        self.assertTrue(result["review_required"])
        self.assertTrue(result["operator_physically_listened"])
        self.assertEqual(result["test_channel"], "sequence")
        self.assertEqual(result["left_speaker_observation"], "heard_expected")
        self.assertEqual(result["right_speaker_observation"], "heard_expected")
        self.assertEqual(result["source_commit_from_local_manifest_unverified"], SOURCE_SHA)
        self.assertFalse(any(k in result for k in (
            "ip", "ip_address", "pin", "key_path", "certificate", "hostname",
            "operator_name", "windows_username", "physical_serial_number")))

    def test_failed_connection_may_be_recorded_without_false_sound_claims(self):
        result = self.record(
            channel="left", outcome="connection_failed", frames=0,
            left="not_checked", right="not_checked", listened=False,
            source_sha=None,
        )
        self.assertFalse(result["operator_physically_listened"])
        self.assertIsNone(result["source_commit_from_local_manifest_unverified"])
        self.assertEqual(result["session_outcome"], "connection_failed")
        self.assertEqual(result["client_pcm_frames_sent_not_sound_proof"], 0)

    def test_wrong_side_silence_and_distortion_are_valid_real_observations(self):
        for field in ("heard_opposite", "silent", "distorted", "uncertain"):
            with self.subTest(observation=field):
                data = self.record(left=field, right="not_checked")
                self.assertEqual(data["left_speaker_observation"], field)
                self.assertFalse(data["hardware_verified"])

    def test_cannot_claim_hearing_without_explicit_personal_confirmation(self):
        with self.assertRaisesRegex(ValueError, "without listening"):
            self.record(listened=False)
        with self.assertRaisesRegex(ValueError, "explicit"):
            self.record(listened="true")

    def test_invalid_fields_are_rejected_before_any_file(self):
        invalids = (
            {"channel": "surround"}, {"channel": ["sequence"]},
            {"outcome": "hardware_verified"}, {"outcome": None},
            {"frames": -1}, {"frames": True}, {"frames": 360001},
            {"frames": "5"}, {"left": "actual audio perfect"},
            {"right": {"ip": "192.168.0.1"}},
            {"source_sha": "invalid sha"},
            {"recorded_utc": "tomorrow"},
            {"recorded_utc": 3},
        )
        for fields in invalids:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.record(**fields)

    def test_local_export_is_exclusive_and_contains_no_secrets(self):
        record = self.record()
        target = self.directory / "evidence.json"
        size = report.save_observation(target, record)
        self.assertGreater(size, 100)
        self.assertLess(size, report.MAX_REPORT_BYTES)
        text = target.read_text(encoding="ascii")
        self.assertEqual(json.loads(text), record)
        self.assertNotIn("192.168.", text)
        self.assertNotIn("private.bin", text)
        self.assertNotIn("pinned", text.lower())
        self.assertNotIn("operator_name", text)
        self.assertNotIn("key_path", text)
        with self.assertRaises(FileExistsError):
            report.save_observation(target, record)
        self.assertEqual(target.read_text(encoding="ascii"), text)
        if os.name == "posix":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_rejects_symlink_destination(self):
        victim = self.directory / "victim.json"
        victim.write_text("original", encoding="utf-8")
        link = self.directory / "linked.json"
        try:
            link.symlink_to(victim)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            report.save_observation(link, self.record())
        self.assertEqual(victim.read_text(), "original")

    def test_export_refuses_injected_extra_identifiers_or_false_hardware_pass(self):
        for changes in (
            {"device_ip": "192.168.10.30"},
            {"private_key_path": "C:\\Users\\Operator\\secret"},
            {"hardware_verified": True},
            {"release_ready": True},
            {"classification": "APPROVED"},
            {"review_required": False},
        ):
            with self.subTest(changes=changes):
                changed = self.record()
                changed.update(changes)
                target = self.directory / ("bad" + str(len(list(self.directory.iterdir()))) + ".json")
                with self.assertRaises(ValueError):
                    report.save_observation(target, changed)
                self.assertFalse(target.exists())

    def test_read_provenance_only_from_matching_local_alpha_manifest(self):
        manifest = self.directory / "SOURCE-MANIFEST.json"
        self.assertIsNone(report.package_source_sha(self.directory))
        manifest.write_text(json.dumps({
            "source_sha": SOURCE_SHA,
            "classification": "UNVERIFIED_ALPHA_TEST_ONLY",
        }))
        self.assertEqual(report.package_source_sha(self.directory), SOURCE_SHA)
        manifest.write_text(json.dumps({
            "source_sha": SOURCE_SHA, "classification": "OFFICIAL_RELEASE"
        }))
        self.assertIsNone(report.package_source_sha(self.directory))
        manifest.write_text("bad JSON", encoding="utf-8")
        self.assertIsNone(report.package_source_sha(self.directory))

    def test_provenance_refuses_linked_or_oversized_local_manifest(self):
        manifest = self.directory / "SOURCE-MANIFEST.json"
        target = self.directory / "example"
        target.write_text(json.dumps({
            "source_sha": SOURCE_SHA,
            "classification": "UNVERIFIED_ALPHA_TEST_ONLY",
        }), encoding="utf-8")
        try:
            manifest.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertIsNone(report.package_source_sha(self.directory))
        manifest.unlink()
        manifest.write_text("x" * (128 * 1024 + 1), encoding="ascii")
        self.assertIsNone(report.package_source_sha(self.directory))


if __name__ == "__main__":
    unittest.main()
