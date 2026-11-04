"""Offline filesystem tests for fail-closed, never-auto-enabling owner records."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.owner_record_store import (
    MAX_RECORD_BYTES, OwnerRecordStore, OwnerStoreError, RECORD_NAME,
)

KEY = bytes(range(32))


class OwnerRecordStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.vault = self.parent / "owner"
        self.vault.mkdir(mode=0o700)
        self.store = OwnerRecordStore(self.vault)

    def approve(self, public_key=KEY):
        return self.store.seal(
            public_key, trusted_physical_approval=True,
            trusted_factory_unowned=True,
        )

    def write_record(self, content):
        target = self.vault / RECORD_NAME
        target.write_bytes(content if type(content) is bytes else content.encode())
        target.chmod(0o600)
        return target

    def test_missing_record_is_not_factory_unowned_authorization(self):
        result = self.store.inspect()
        self.assertEqual(result["record_condition"], "missing_untrusted")
        self.assertFalse(result["durable_owner_verified"])
        self.assertFalse(result["network_onboarding_enabled"])
        self.assertFalse(result["release_ready"])

    def test_both_trusted_preconditions_are_required(self):
        for p, u in ((False, False), (True, False), (False, True),
                     (1, True), ("yes", True), (True, 1)):
            with self.subTest(physical=p, factory=u), self.assertRaises(OwnerStoreError):
                self.store.seal(KEY, trusted_physical_approval=p,
                                trusted_factory_unowned=u)
        self.assertFalse((self.vault / RECORD_NAME).exists())

    def test_valid_record_is_durable_but_never_authenticated(self):
        self.assertEqual(self.approve()["record_condition"],
                         "record_present_unverified")
        same_after_restart = OwnerRecordStore(self.vault).inspect()
        self.assertEqual(same_after_restart["record_condition"],
                         "record_present_unverified")
        for status in (self.store.inspect(), same_after_restart):
            self.assertFalse(status["durable_owner_verified"])
            self.assertFalse(status["network_onboarding_enabled"])
            self.assertFalse(status["release_ready"])
        raw = (self.vault / RECORD_NAME).read_text()
        self.assertIn(hashlib.sha256(KEY).hexdigest(), raw)
        self.assertNotIn(KEY.hex(), raw)
        self.assertEqual(stat.S_IMODE((self.vault / RECORD_NAME).stat().st_mode), 0o600)

    def test_owner_record_never_overwritten_by_second_claim(self):
        self.approve()
        before = (self.vault / RECORD_NAME).read_bytes()
        with self.assertRaises(OwnerStoreError):
            OwnerRecordStore(self.vault).seal(bytes([42]) * 32,
                trusted_physical_approval=True, trusted_factory_unowned=True)
        self.assertEqual((self.vault / RECORD_NAME).read_bytes(), before)

    def test_invalid_existing_file_remains_and_blocks_claim(self):
        self.write_record('{"schema_version":1,"state":"bad"}')
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")
        with self.assertRaises(OwnerStoreError):
            self.approve()
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")

    def test_symlink_owner_record_not_followed_or_modified(self):
        secret_file = self.parent / "outside"
        secret_file.write_text("sensitive")
        (self.vault / RECORD_NAME).symlink_to(secret_file)
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")
        with self.assertRaises(OwnerStoreError):
            self.approve()
        self.assertEqual(secret_file.read_text(), "sensitive")

    def test_directory_symlink_and_wrong_permissions_are_denied(self):
        symlink = self.parent / "redirect"
        symlink.symlink_to(self.vault, target_is_directory=True)
        self.assertEqual(OwnerRecordStore(symlink).inspect()["record_condition"],
                         "invalid")
        with self.assertRaises(OwnerStoreError):
            OwnerRecordStore(symlink).seal(
                KEY, trusted_physical_approval=True, trusted_factory_unowned=True)
        self.vault.chmod(0o755)
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")
        with self.assertRaises(OwnerStoreError):
            self.approve()

    def test_world_readable_record_is_invalid(self):
        self.approve()
        (self.vault / RECORD_NAME).chmod(0o644)
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")

    def test_multiple_hardlinks_are_not_trusted(self):
        self.approve()
        os.link(self.vault / RECORD_NAME, self.parent / "other-link")
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")

    def test_duplicate_keys_and_schema_errors_are_invalid(self):
        good_hash = hashlib.sha256(KEY).hexdigest()
        cases = [
            '{"schema_version":1,"schema_version":1,"state":"claimed","owner_key_sha256":"'+good_hash+'"}',
            '{"schema_version":true,"state":"claimed","owner_key_sha256":"'+good_hash+'"}',
            '{"schema_version":2,"state":"claimed","owner_key_sha256":"'+good_hash+'"}',
            '{"schema_version":1,"state":"claimed","owner_key_sha256":"'+good_hash+'","extra":1}',
            '{"schema_version":1,"state":"claimed","owner_key_sha256":"'+good_hash.upper()+'"}',
            '{"schema_version":1,"state":"claimed","owner_key_sha256":"short"}',
            '{"schema_version":1,"state":"unowned","owner_key_sha256":"'+good_hash+'"}',
            "[]", "null", "{", b"\xff\xfe"
        ]
        for data in cases:
            with self.subTest(data=str(data)[:38]):
                record = self.write_record(data)
                self.assertEqual(self.store.inspect()["record_condition"], "invalid")
                record.unlink()

    def test_oversize_record_rejected_without_reading_as_owner(self):
        self.write_record(b"0" * (MAX_RECORD_BYTES + 1))
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")

    def test_public_status_never_contains_key_digest_or_raw_key(self):
        self.approve()
        output = json.dumps(self.store.inspect())
        self.assertNotIn(hashlib.sha256(KEY).hexdigest(), output)
        self.assertNotIn(KEY.hex(), output)

    def test_missing_directory_and_relative_path_fail_closed(self):
        with self.assertRaises(ValueError):
            OwnerRecordStore("relative/owner")
        unknown = OwnerRecordStore(self.parent / "never-created")
        self.assertEqual(unknown.inspect()["record_condition"], "invalid")
        with self.assertRaises(OwnerStoreError):
            unknown.seal(KEY, trusted_physical_approval=True,
                         trusted_factory_unowned=True)

    def test_key_bytes_must_be_exact_length(self):
        for data in (None, "0" * 32, b"x", b"x" * 31, b"x" * 33, bytearray(KEY)):
            with self.subTest(data=str(data)[:18]), self.assertRaises(OwnerStoreError):
                self.approve(public_key=data)
        self.assertEqual(self.store.inspect()["record_condition"], "missing_untrusted")

    def test_failed_write_keeps_record_untrusted_and_never_reopens_claim(self):
        with mock.patch("audiohub.owner_record_store.os.write", return_value=0):
            with self.assertRaises(OwnerStoreError):
                self.approve()
        self.assertEqual(self.store.inspect()["record_condition"], "invalid")
        with self.assertRaises(OwnerStoreError):
            self.approve()

    def test_no_network_install_or_automatic_owner_authorization(self):
        code = (ROOT / "src/audiohub/owner_record_store.py").read_text()
        for marker in ("ThreadingHTTPServer", "dbus.SystemBus", "subprocess.run",
                       "socket.socket", "nmcli", "AUDIOHUB_UNSAFE_STATUS_LAN"):
            self.assertNotIn(marker, code)
        for target in ("src/audiohub/webserver.py", "src/audiohub/pairing.py",
                       "image/stage-audiohub/01-install/00-run.sh"):
            self.assertNotIn("owner_record_store", (ROOT / target).read_text())


if __name__ == "__main__":
    unittest.main()
