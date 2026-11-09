"""Deterministic offline X.509 pin onboarding tests on Linux AND Windows.

Embedded certificate is a throwaway, expired/short-lived PUBLIC test-only
fixture, never a Pi identity. There is deliberately no private key.
"""
import hashlib
import os
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import certificate_onboarding as cert
from audiohub import windows_bridge_setup as setup
from audiohub import windows_bridge_gui as gui

FIXTURE_PUBLIC_PEM = """-----BEGIN CERTIFICATE-----
MIIDITCCAgmgAwIBAgIUCV9QypfFFZeIqXqL8lyICYCLs5QwDQYJKoZIhvcNAQEL
BQAwIDEeMBwGA1UEAwwVQXVkaW9IdWIgVGVzdCBGaXh0dXJlMB4XDTI2MTEwOTEx
NTEyM1oXDTI2MTExMDExNTEyM1owIDEeMBwGA1UEAwwVQXVkaW9IdWIgVGVzdCBG
aXh0dXJlMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAz9ugdQKygbxB
fsvK1S8FE6cC46tFE+K5pkKRK0swLnmAxgF9pODhPDEcLNQWMDxMGjKltoUHx135
PG4MizWAkqXLJuYuUmMP6gWfwruE9LTzV2zZub65Ag9MkXwkff97YnP2SWFacFGO
h+nCPhcfFDbukdHqsbLQw9qLGQsQ586GVxyl2unrLx6iRJ672uuCZmjvUhczwJVh
0hablES9HWbzMdAy+MxFSUT3rAiemKH8TAeQeBk9D7uFnCImjFZ4+S35YvnghrnR
vzzFLfBlWXNBLUIxew7goEJn+e1bSnmsPSealIqq62bU0uvLfV5zPtZ1itCXQZgH
glO6LWSZNQIDAQABo1MwUTAdBgNVHQ4EFgQUAhj05w5oi7JKhc4GhXCQZhdoZ5kw
HwYDVR0jBBgwFoAUAhj05w5oi7JKhc4GhXCQZhdoZ5kwDwYDVR0TAQH/BAUwAwEB
/zANBgkqhkiG9w0BAQsFAAOCAQEAEoWaLEZxRrPTBhN09nePD5WSSZ0yR4KVLdgZ
ewUa6cRhJbktbEasHhCBxC8o41vlSDXl3EZiaMF0PmJw8ZrQzN/MhAlAJIrBok40
+PxXpp5yjX2+eZu2MHVEXtyfqEi8VFycZ/mkN64pu5LSle1QoTLMG0F9Bo2nDNO1
tZ42srzNL+arISA4NW6GAq+kzHkS/NrmZ+Wm26WrNy3fyV765drS42Enm6m5jSLW
b6XGfyhBlSIN0cNWEFmzlcVrLQ+4doAMaYp76IbNBRFLVoJo/KGf3lG3XyIaunl8
pnYGoxIvFnw1YPmH0xl9guQZe8dLG7Nd4Yv49jM+Hlr90mbkow==
-----END CERTIFICATE-----
"""
FIXTURE_PIN = "fcde25cfeb992e61e9185844faede7a44e0669de5427549e577210e8609dfda8"


class OfflineCertificateOnboardingTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.directory = Path(td.name)
        self.cert = self.directory / "pi-public.pem"
        self.cert.write_text(FIXTURE_PUBLIC_PEM, encoding="ascii")
        self.der = self.directory / "pi-public.der"
        self.der.write_bytes(ssl.PEM_cert_to_DER_cert(FIXTURE_PUBLIC_PEM))
        self.key = self.directory / "private"
        self.key.write_bytes(os.urandom(32))
        if os.name == "posix":
            self.key.chmod(0o600)

    def test_der_and_pem_have_identical_pinned_certificate_hash(self):
        self.assertEqual(hashlib.sha256(self.der.read_bytes()).hexdigest(), FIXTURE_PIN)
        self.assertEqual(cert.certificate_sha256(self.cert), FIXTURE_PIN)
        self.assertEqual(cert.certificate_sha256(self.der), FIXTURE_PIN)
        self.assertTrue(cert.verify_public_certificate(self.cert, FIXTURE_PIN))
        self.assertTrue(cert.verify_public_certificate(self.der, FIXTURE_PIN))

    def test_untrusted_certificate_and_mistyped_pin_fail_closed(self):
        for value in ("f" * 64, "F" * 64, "", FIXTURE_PIN[:-1]):
            with self.subTest(pin=value), self.assertRaises(ValueError):
                cert.verify_public_certificate(self.cert, value)

    def test_only_single_valid_x509_no_private_key_or_arbitrary_file(self):
        cases = (
            b"", b"<html>not a cert</html>",
            FIXTURE_PUBLIC_PEM.encode("ascii") * 2,
            FIXTURE_PUBLIC_PEM.encode("ascii") + b"\nPRIVATE KEY",
            b"-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
            b"\x30\x03\x01\x01\xff",  # valid ASN.1 but not X.509
        )
        for idx, value in enumerate(cases):
            with self.subTest(idx=idx):
                path = self.directory / ("invalid" + str(idx))
                path.write_bytes(value)
                with self.assertRaises((ValueError, OSError)):
                    cert.certificate_sha256(path)

    def test_reject_overlarge_symlink_and_relative_file(self):
        oversized = self.directory / "oversized"
        oversized.write_bytes(b"x" * (cert.MAX_CERT_BYTES + 1))
        with self.assertRaises(ValueError):
            cert.read_public_cert_der(oversized)
        with self.assertRaises(ValueError):
            cert.read_public_cert_der("pi-public.pem")
        linked = self.directory / "linked.pem"
        try:
            linked.symlink_to(self.cert)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            cert.read_public_cert_der(linked)

    def test_cli_offline_preflight_rejects_wrong_cert_before_connection(self):
        args = ["192.168.10.30", FIXTURE_PIN, str(self.key), "10"]
        self.assertEqual(
            setup.validate_local_setup(*args, certificate_file=str(self.cert)),
            str(self.key),
        )
        with mock.patch.object(setup.secure_lan.socket, "create_connection") as dial:
            with self.assertRaises((ValueError, OSError)):
                setup.validate_local_setup(
                    *args, certificate_file=str(self.directory / "bad.cert"))
            dial.assert_not_called()
        with mock.patch.object(setup.secure_lan.socket, "create_connection") as dial:
            with self.assertRaises(ValueError):
                setup.validate_local_setup(
                    args[0], "0" * 64, args[2], 10,
                    certificate_file=str(self.cert))
            dial.assert_not_called()

    def test_cli_check_only_with_cert_never_starts_network_or_logs_secret(self):
        answers = iter(["192.168.10.30", FIXTURE_PIN, str(self.key), "10"])
        execute = mock.Mock()
        output = []
        result = setup.interactive_bridge(
            input_fn=lambda _: next(answers),
            output=output.append, execute=execute, check_only=True,
            certificate_file=str(self.cert))
        self.assertEqual(result, 0)
        execute.assert_not_called()
        joined = "\n".join(output)
        self.assertIn("MATCHES", joined)
        self.assertIn("INDEPENDENT", joined.upper())
        self.assertNotIn(str(self.key), joined)
        self.assertNotIn(FIXTURE_PIN, joined)

    def test_gui_offline_match_validates_without_connecting(self):
        args = ("192.168.10.30", FIXTURE_PIN, str(self.key), "10")
        self.assertEqual(gui.validate_fields(*args, certificate_file=str(self.cert)),
                         ("192.168.10.30", FIXTURE_PIN, str(self.key), 10))
        with mock.patch.object(setup.secure_lan.socket, "create_connection") as dial:
            with self.assertRaises(ValueError):
                gui.validate_fields(
                    "192.168.10.30", "f" * 64, str(self.key), "10",
                    certificate_file=str(self.cert))
            dial.assert_not_called()


if __name__ == "__main__":
    unittest.main()
