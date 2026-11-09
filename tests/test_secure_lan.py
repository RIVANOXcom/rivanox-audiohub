"""Offline tests for manually opted-in authenticated Windows LAN audio.

No Internet, real audio hardware, Windows driver, published cert or static
project credentials are needed. These are not physical acceptance tests.
"""
import hashlib
import hmac
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import secure_lan as lan


class SecureLanTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.secret = b"a" * 32
        self.secret_path = Path(self.folder.name) / "private-key"
        self.secret_path.write_bytes(self.secret)
        if os.name == "posix":
            self.secret_path.chmod(0o600)

    def test_private_secret_must_be_exact_regular_not_linked_and_private(self):
        self.assertEqual(lan.read_private_key(self.secret_path), self.secret)
        self.secret_path.write_bytes(b"a" * 33)
        with self.assertRaises(ValueError):
            lan.read_private_key(self.secret_path)
        self.secret_path.write_bytes(self.secret)
        if os.name == "posix":
            self.secret_path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "mode 0600"):
                lan.read_private_key(self.secret_path)
            self.secret_path.chmod(0o600)
        link = Path(self.folder.name) / "link"
        try:
            link.symlink_to(self.secret_path)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaisesRegex(ValueError, "Linked"):
                lan.read_private_key(link)

    def test_tls_pin_and_key_validation_fail_closed(self):
        good = hashlib.sha256(b"test certificate").hexdigest()
        self.assertEqual(lan.validate_pin(good), good)
        for value in ("", "A" * 64, "z" * 64, "f" * 63, 123, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lan.validate_pin(value)
        for value in (b"short", "a" * 32, bytearray(32), None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lan.validate_key_bytes(value)

    def test_fresh_challenge_authenticates_only_correct_secret(self):
        for client_key in (self.secret, b"b" * 32):
            with self.subTest(match=client_key == self.secret):
                left, right = socket.socketpair()
                self.addCleanup(left.close)
                self.addCleanup(right.close)
                result = []
                def server():
                    try:
                        lan.authenticate_server(left, self.secret)
                        result.append("accepted")
                    except PermissionError:
                        result.append("denied")
                thread = threading.Thread(target=server)
                thread.start()
                try:
                    if client_key == self.secret:
                        self.assertTrue(lan.authenticate_client(right, client_key))
                    else:
                        with self.assertRaises(PermissionError):
                            lan.authenticate_client(right, client_key)
                finally:
                    thread.join(timeout=4)
                self.assertFalse(thread.is_alive())
                self.assertEqual(result, ["accepted" if client_key == self.secret else "denied"])

    def test_auth_proof_is_bound_to_random_nonce_and_domain(self):
        token = b"x" * 32
        one = hmac.new(self.secret, lan.DOMAIN + token, hashlib.sha256).digest()
        two = hmac.new(self.secret, lan.DOMAIN + b"y" * 32, hashlib.sha256).digest()
        wrong_domain = hmac.new(self.secret, token, hashlib.sha256).digest()
        self.assertNotEqual(one, two)
        self.assertNotEqual(one, wrong_domain)

    def test_both_modes_refuse_to_open_port_without_explicit_optin(self):
        with mock.patch.object(lan.socket, "socket") as make_sock:
            with self.assertRaisesRegex(ValueError, "opt-in"):
                lan.run_server(bind_ip="127.0.0.1", sender_ip="127.0.0.1",
                               port=4044, key_file=self.secret_path, cert_file="none",
                               private_key_file="none")
            make_sock.assert_not_called()
        with mock.patch.object(lan.socket, "create_connection") as connect:
            with self.assertRaisesRegex(ValueError, "opt-in"):
                lan.run_bridge(server_ip="127.0.0.1", port=4044,
                               udp_port=4010, key_file=self.secret_path,
                               pin_sha256="a" * 64)
            connect.assert_not_called()

    def test_only_exact_private_remote_host_and_local_udp_loopback(self):
        with mock.patch.object(lan.socket, "create_connection") as connect:
            for target in ("0.0.0.0", "8.8.8.8", "239.255.77.77"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    lan.run_bridge(server_ip=target, port=4044, udp_port=4010,
                                   key_file=self.secret_path, pin_sha256="a" * 64,
                                   isolated_lab=True)
            connect.assert_not_called()

    def test_forwarder_discards_wrong_peer_and_unsupported_pcm(self):
        udp = mock.Mock()
        udp.recvfrom.side_effect = [
            (bytes((1, 16, 2, 3, 0)) + b"ABCD", ("127.0.0.2", 4010)),
            (bytes((1, 24, 2, 3, 0)) + b"ABCD", ("127.0.0.1", 4010)),
            (bytes((1, 16, 2, 3, 0)) + b"ABCD", ("127.0.0.1", 4010)),
        ]
        stream = mock.Mock()
        with mock.patch.object(lan.time, "monotonic", side_effect=[100., 100., 100., 101.]):
            count = lan.forward_loopback_pcm(udp, stream, 100.5)
        self.assertEqual(count, 1)
        stream.sendall.assert_called_once_with(b"\x00\x04ABCD")
        udp.settimeout.assert_called_once_with(0.2)

    def test_frames_reject_oversized_or_non_stereo_before_spawn(self):
        for length in (0, 3, 5, 1153, 65535):
            with self.subTest(length=length), mock.patch.object(lan, "check_audio_target",
                    return_value=(3, 9)), mock.patch.object(lan, "lan_target",
                    return_value="audiohub.laptop"), mock.patch.object(
                    lan.subprocess, "Popen") as popen:
                stream = mock.Mock()
                stream.recv.side_effect = [int(length).to_bytes(2, "big")]
                with self.assertRaises(ValueError):
                    lan.consume_authenticated_pcm(stream, "audiohub.laptop",
                                                  lan.time.monotonic() + 10)
                popen.assert_not_called()

    def test_valid_authenticated_frame_targets_only_private_sink(self):
        stream = mock.Mock()
        stream.recv.side_effect = [b"\x00\x04", b"ABCD", b""]
        process = mock.Mock()
        process.stdin.fileno.return_value = 42
        process.poll.return_value = None
        with mock.patch.object(lan, "check_audio_target", return_value=(3, 9)), \
             mock.patch.object(lan, "lan_target", return_value="audiohub.laptop"), \
             mock.patch.object(lan.subprocess, "Popen", return_value=process) as popen, \
             mock.patch.object(lan, "close_player") as close, \
             mock.patch.object(lan.os, "set_blocking"), \
             mock.patch.object(lan.os, "write", return_value=4) as write:
            with self.assertRaises(ConnectionError):
                lan.consume_authenticated_pcm(stream, "audiohub.laptop", time.monotonic() + 10)
            cmd = popen.call_args.args[0]
            self.assertIn("--target=audiohub.laptop", cmd)
            write.assert_called_once_with(42, b"ABCD")
            close.assert_called_once_with(process)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL command required for live TLS probe")
    def test_real_tls13_certificate_pin_accepts_only_exact_cert(self):
        certificate = Path(self.folder.name) / "device.crt"
        private = Path(self.folder.name) / "device.key"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "ec",
             "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
             "-keyout", str(private), "-out", str(certificate),
             "-subj", "/CN=isolated-test-only", "-days", "1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=12)
        der = ssl.PEM_cert_to_DER_cert(certificate.read_text())
        expected_pin = hashlib.sha256(der).hexdigest()
        for pin in (expected_pin, "0" * 64):
            with self.subTest(pin_ok=pin == expected_pin):
                left, right = socket.socketpair()
                server_ctx = lan.make_server_context(str(certificate), str(private))
                errors = []
                def srv():
                    try:
                        with server_ctx.wrap_socket(left, server_side=True) as s:
                            lan.authenticate_server(s, self.secret)
                    except (OSError, PermissionError) as exc:
                        errors.append(type(exc).__name__)
                thread = threading.Thread(target=srv)
                thread.start()
                try:
                    if pin == expected_pin:
                        with lan.make_client_tls(right, pin) as stream:
                            self.assertTrue(lan.authenticate_client(stream, self.secret))
                    else:
                        with self.assertRaises(PermissionError):
                            lan.make_client_tls(right, pin)
                finally:
                    thread.join(timeout=5)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
