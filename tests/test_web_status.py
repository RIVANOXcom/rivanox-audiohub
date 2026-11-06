"""Read-only web API and deployment safety tests."""
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from unittest import mock
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.webserver import (ALLOWED, PUBLIC_FIELDS, Handler,
                                BoundedStatusHTTPServer, MAX_STATUS_CLIENTS,
                                CLIENT_READ_TIMEOUT_SECONDS,
                                STATIC_MAX_BYTES, STATUS_MAX_BYTES,
                                _bounded_regular_bytes, public_status,
                                read_public_status)


class WebStatusTests(unittest.TestCase):
    def test_live_health_is_anonymized_and_bounded(self):
        raw = {
            "updated_at": 100, "usb_output": True, "active_routes": 999,
            "bluetooth_source_count": 999,
            "virtual_channels": ["music", "music", "tablet", "../secret"],
            "address": "AA:BB:CC:DD:EE:FF", "ssid": "PrivateWifi",
            "password": "never-disclose",
        }
        status = public_status(raw, now=109)
        self.assertEqual(set(status), PUBLIC_FIELDS)
        self.assertEqual(status["active_routes"], 3)
        self.assertEqual(status["bluetooth_sources"], 2)
        self.assertEqual(status["virtual_channel_count"], 2)
        self.assertTrue(status["usb_connected"])
        self.assertNotIn("AA:BB", str(status))
        self.assertNotIn("PrivateWifi", str(status))

    def test_stale_or_wrong_status_is_not_trusted(self):
        for value in ({}, "bad", {"updated_at": 1, "usb_output": True}):
            with self.subTest(value=value):
                self.assertFalse(public_status(value, now=100)["fresh"])
                self.assertFalse(public_status(value, now=100)["usb_connected"])

    def test_time_must_not_be_in_future(self):
        self.assertFalse(public_status({"updated_at": 200}, now=100)["fresh"])

    def test_assets_are_explicitly_allowlisted(self):
        self.assertIn("/", ALLOWED)
        for code in ("en", "de", "es", "fr", "it"):
            self.assertIn("/locales/" + code + ".json", ALLOWED)
        for hidden in ("/etc/passwd", "/.env", "/../secrets", "/locales/../../etc/passwd"):
            self.assertNotIn(hidden, ALLOWED)

    def test_web_service_does_not_expose_mutating_api(self):
        script = (ROOT / "src/audiohub/webserver.py").read_text()
        self.assertIn("def do_POST(self):", script)
        self.assertIn("Read-only preview", script)
        self.assertNotIn("shell=True", script)

    def test_image_contains_web_and_service(self):
        builder = (ROOT / "build-image.sh").read_text()
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text()
        self.assertIn('cp -a "$ROOT/web/."', builder)
        self.assertIn("files/web/.", installer)
        self.assertIn("audiohub-status-web.service", installer)


class ReadonlyWebFileBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "www"
        self.root.mkdir()
        self.status = Path(temp.name) / "runtime-status.json"
        self.ok_asset = self.root / "app.js"
        self.ok_asset.write_bytes(b"// local prototype")

    def _request(self, path):
        """Exercise actual GET dispatch without binding a network port."""
        handler = object.__new__(Handler)
        handler.path = path
        result = []
        handler.respond = lambda code, data, mime: result.append((code, data, mime))
        with patch("audiohub.webserver.WEBROOT", self.root), patch(
            "audiohub.webserver.STATE", self.status
        ):
            Handler.do_GET(handler)
        self.assertEqual(len(result), 1)
        return result[0]

    def test_local_allowlisted_asset_is_served_exactly(self):
        status, content, mime = self._request("/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(content, b"// local prototype")
        self.assertIn("javascript", mime)

    def test_path_traversal_never_reads_host_file(self):
        secret = self.root.parent / "private.txt"
        secret.write_text("LOCAL-PRIVATE-MATERIAL")
        for route in ("/../private.txt", "/%2e%2e/private.txt",
                      "/locales/../../private.txt", "/.git/config"):
            code, body, _ = self._request(route)
            self.assertEqual(code, 404)
            self.assertNotIn(b"PRIVATE", body)

    def test_static_leaf_symlink_never_reads_private_file(self):
        hidden = self.root.parent / "private.txt"
        hidden.write_text("PRIVATE DEVICE CREDENTIAL")
        self.ok_asset.unlink()
        self.ok_asset.symlink_to(hidden)
        code, body, _ = self._request("/app.js")
        self.assertEqual(code, 503)
        self.assertNotIn(b"PRIVATE", body)

    def test_static_intermediate_directory_symlink_is_refused(self):
        private = self.root.parent / "private"
        private.mkdir()
        (private / "en.json").write_text("PRIVATE")
        (self.root / "locales").symlink_to(private, target_is_directory=True)
        code, body, _ = self._request("/locales/en.json")
        self.assertEqual(code, 503)
        self.assertNotIn(b"PRIVATE", body)

    def test_webroot_symlink_is_refused(self):
        real = self.root.parent / "real"
        real.mkdir()
        (real / "app.js").write_text("hidden")
        with patch("audiohub.webserver.WEBROOT", self.root.parent / "linked"):
            (self.root.parent / "linked").symlink_to(real, target_is_directory=True)
            handler = object.__new__(Handler)
            handler.path = "/app.js"
            result = []
            handler.respond = lambda status, body, mime: result.append((status, body))
            Handler.do_GET(handler)
        self.assertEqual(result[0][0], 503)

    def test_non_regular_fifo_does_not_block_or_serve(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("Linux-only FIFO")
        self.ok_asset.unlink()
        os.mkfifo(self.ok_asset)
        code, _, _ = self._request("/app.js")
        self.assertEqual(code, 503)

    def test_oversized_asset_is_refused(self):
        self.ok_asset.write_bytes(b"a" * (STATIC_MAX_BYTES + 1))
        code, _, _ = self._request("/app.js")
        self.assertEqual(code, 503)

    def test_empty_asset_is_refused(self):
        self.ok_asset.write_bytes(b"")
        code, _, _ = self._request("/app.js")
        self.assertEqual(code, 503)

    def test_bounded_reader_rejects_relative_and_parent_paths(self):
        self.assertIsNone(_bounded_regular_bytes(Path("app.js"), STATIC_MAX_BYTES))
        self.assertIsNone(_bounded_regular_bytes(self.root / ".." / "app.js",
                                                 STATIC_MAX_BYTES))
        self.assertIsNone(_bounded_regular_bytes(self.ok_asset, 0))
        self.assertIsNone(_bounded_regular_bytes(self.ok_asset, True))

    def test_valid_status_has_only_public_counts(self):
        self.status.write_text(json.dumps({
            "updated_at": 123, "usb_output": True, "active_routes": 2,
            "bluetooth_source_count": 1, "virtual_channels": ["music"],
            "mac": "A1:B2:C3:D4:E5:F6", "password": "NEVER-LEAK"
        }))
        self.status.chmod(0o600)
        result = read_public_status(path=self.status, now=124)
        self.assertEqual(set(result), PUBLIC_FIELDS)
        self.assertEqual(result["active_routes"], 2)
        self.assertTrue(result["usb_connected"])
        self.assertNotIn("NEVER-LEAK", str(result))
        self.assertNotIn("A1:B2", str(result))

    def test_get_status_dispatch_redacts_secrets(self):
        self.status.write_text(json.dumps({
            "updated_at": int(__import__("time").time()),
            "usb_output": True, "active_routes": 1,
            "bluetooth_source_count": 1, "ssid": "PRIVATE-SSID",
            "password": "PRIVATE-PASSWORD"
        }))
        self.status.chmod(0o600)
        code, body, _ = self._request("/api/status")
        self.assertEqual(code, 200)
        self.assertEqual(set(json.loads(body)), PUBLIC_FIELDS)
        self.assertNotIn(b"PRIVATE", body)

    def test_status_symlink_or_bad_json_is_stale(self):
        protected = self.root.parent / "secret"
        protected.write_text('{"updated_at":123,"usb_output":true,"password":"private"}')
        self.status.symlink_to(protected)
        self.assertFalse(read_public_status(path=self.status, now=124)["fresh"])
        self.status.unlink()
        self.status.write_text("{malformed")
        self.assertFalse(read_public_status(path=self.status, now=124)["fresh"])

    def test_status_too_large_is_stale(self):
        self.status.write_bytes(b"x" * (STATUS_MAX_BYTES + 1))
        data = read_public_status(path=self.status, now=124)
        self.assertFalse(data["fresh"])
        self.assertEqual(data["active_routes"], 0)

    def test_status_nonregular_is_stale(self):
        self.status.mkdir()
        self.assertFalse(read_public_status(path=self.status)["fresh"])


    def test_private_status_file_with_correct_owner_reports_health(self):
        self.status.write_text('{"updated_at":100,"usb_output":true}')
        self.status.chmod(0o600)
        self.assertTrue(read_public_status(path=self.status, now=101)["fresh"])

    def test_world_or_group_readable_runtime_status_is_stale(self):
        self.status.write_text('{"updated_at":100,"usb_output":true}')
        for mode in (0o644, 0o640, 0o604, 0o666):
            with self.subTest(mode=oct(mode)):
                self.status.chmod(mode)
                report = read_public_status(path=self.status, now=101)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["usb_connected"])

    def test_hardlinked_runtime_status_cannot_report_healthy(self):
        self.status.write_text('{"updated_at":100,"usb_output":true}')
        self.status.chmod(0o600)
        outside = self.root.parent / "other-hardlink"
        os.link(self.status, outside)
        self.assertFalse(read_public_status(path=self.status, now=101)["fresh"])

    def test_status_owned_by_different_uid_is_not_trusted(self):
        self.status.write_text('{"updated_at":100,"usb_output":true}')
        self.status.chmod(0o600)
        wrong = os.geteuid() + 1
        with patch("audiohub.webserver.os.geteuid", return_value=wrong):
            self.assertFalse(read_public_status(path=self.status, now=101)["fresh"])

    def test_world_readable_status_directory_is_rejected(self):
        self.status.write_text('{"updated_at":100,"usb_output":true}')
        self.status.chmod(0o600)
        parent = self.status.parent
        parent.chmod(0o755)
        self.assertFalse(read_public_status(path=self.status, now=101)["fresh"])
        parent.chmod(0o700)
        self.assertTrue(read_public_status(path=self.status, now=101)["fresh"])

    def test_static_asset_world_readability_stays_allowed(self):
        self.ok_asset.chmod(0o644)
        code, content, _ = self._request("/app.js")
        self.assertEqual(code, 200)
        self.assertEqual(content, b"// local prototype")

    def test_private_status_owner_argument_rejects_bad_types(self):
        self.status.write_text('{"updated_at":100,"usb_output":true}')
        self.status.chmod(0o600)
        for bad in (True, -1, "audiohub", [], {}):
            with self.subTest(owner=repr(bad)):
                self.assertIsNone(_bounded_regular_bytes(
                    self.status, STATUS_MAX_BYTES, private_owner=bad
                ))

    def test_a_public_status_file_cannot_create_false_usb_health(self):
        self.status.write_text(json.dumps({
            "updated_at": 100, "usb_output": True, "active_routes": 2,
            "password": "PRIVATE_WIFI_PASSWORD",
        }))
        self.status.chmod(0o644)
        result = read_public_status(path=self.status, now=101)
        self.assertEqual(result["active_routes"], 0)
        self.assertFalse(result["usb_connected"])
        self.assertNotIn("PRIVATE_WIFI_PASSWORD", json.dumps(result))

    def test_deep_nested_runtime_json_is_stale_not_a_handler_crash(self):
        # Under STATUS_MAX_BYTES, but beyond the JSON decoder recursion cap.
        documents = (
            "[" * 5000 + "0" + "]" * 5000,
            '{"k":' * 3000 + "0" + "}" * 3000,
        )
        for document in documents:
            with self.subTest(kind=document[0]):
                self.status.write_text(document)
                self.status.chmod(0o600)
                report = read_public_status(path=self.status, now=101)
                self.assertEqual(set(report), PUBLIC_FIELDS)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["usb_connected"])
                self.assertEqual(report["active_routes"], 0)

    def test_malformed_absolute_http_targets_are_safe_404(self):
        for target in ("http://[broken/path", "http://[::1"):
            with self.subTest(target=target):
                code, body, mime = self._request(target)
                self.assertEqual(code, 404)
                self.assertEqual(body, b"Not found")
                self.assertIn("text/plain", mime)

    def test_missing_status_is_stale(self):
        self.assertFalse(read_public_status(path=self.status)["fresh"])



class BoundedStatusHTTPResourceTests(unittest.TestCase):
    """No listening port, external network or production server needed."""

    def server(self, cap=1):
        instance = object.__new__(BoundedStatusHTTPServer)
        instance._client_slots = threading.BoundedSemaphore(cap)
        instance.shutdown_request = mock.Mock()
        return instance

    def test_worker_and_read_limits_are_small_and_fixed(self):
        self.assertEqual(MAX_STATUS_CLIENTS, 8)
        self.assertEqual(CLIENT_READ_TIMEOUT_SECONDS, 5)
        self.assertEqual(BoundedStatusHTTPServer.request_queue_size, 8)
        self.assertTrue(BoundedStatusHTTPServer.daemon_threads)

    def test_extra_connection_is_closed_without_new_thread(self):
        server = self.server()
        socket = mock.Mock()
        peer = ("127.0.0.1", 12345)
        with mock.patch.object(ThreadingHTTPServer, "process_request") as parent:
            server.process_request(socket, peer)
            server.process_request(socket, peer)
            parent.assert_called_once_with(socket, peer)
        server.shutdown_request.assert_called_once_with(socket)

    def test_completed_request_releases_worker_slot(self):
        server = self.server()
        peer = ("127.0.0.1", 23456)
        socket = mock.Mock()
        with mock.patch.object(ThreadingHTTPServer, "process_request"):
            server.process_request(socket, peer)
        self.assertFalse(server._client_slots.acquire(blocking=False))
        with mock.patch.object(ThreadingHTTPServer, "process_request_thread") as worker:
            server.process_request_thread(socket, peer)
            worker.assert_called_once_with(socket, peer)
        self.assertTrue(server._client_slots.acquire(blocking=False))

    def test_worker_exception_also_releases_slot(self):
        server = self.server()
        peer = ("127.0.0.1", 23456)
        socket = mock.Mock()
        with mock.patch.object(ThreadingHTTPServer, "process_request"):
            server.process_request(socket, peer)
        with mock.patch.object(ThreadingHTTPServer, "process_request_thread",
                               side_effect=RuntimeError("private request data")):
            with self.assertRaisesRegex(RuntimeError, "private request"):
                server.process_request_thread(socket, peer)
        self.assertTrue(server._client_slots.acquire(blocking=False))

    def test_thread_start_error_releases_slot(self):
        server = self.server()
        peer = ("127.0.0.1", 23456)
        socket = mock.Mock()
        with mock.patch.object(ThreadingHTTPServer, "process_request",
                               side_effect=OSError("thread creation denied")):
            with self.assertRaises(OSError):
                server.process_request(socket, peer)
        self.assertTrue(server._client_slots.acquire(blocking=False))

    def test_accepted_socket_has_finite_read_timeout(self):
        server = self.server()
        sock = mock.Mock()
        peer = ("127.0.0.1", 8765)
        with mock.patch.object(ThreadingHTTPServer, "get_request",
                               return_value=(sock, peer)):
            actual = server.get_request()
        self.assertEqual(actual, (sock, peer))
        sock.settimeout.assert_called_once_with(5)

    def test_rejected_socket_timeout_setup_closes_socket(self):
        server = self.server()
        sock = mock.Mock()
        sock.settimeout.side_effect = OSError("bad socket")
        with mock.patch.object(ThreadingHTTPServer, "get_request",
                               return_value=(sock, ("127.0.0.1", 8765))):
            with self.assertRaises(OSError):
                server.get_request()
        sock.close.assert_called_once()

    def test_raw_http_queries_cannot_enter_access_logs(self):
        handler = object.__new__(Handler)
        with mock.patch("sys.stderr") as sink:
            handler.log_message('%s GET /api/status?token=%s',
                                "CLIENT_MAC_AA_BB_CC_DD_EE_FF", "TOP-SECRET")
        sink.write.assert_not_called()

    def test_existing_readonly_handler_routes_are_unmodified(self):
        self.assertIn("/api/status", Handler.do_GET.__code__.co_consts)
        self.assertTrue(callable(Handler.do_POST))
        self.assertIs(Handler.do_DELETE, Handler.do_POST)


if __name__ == "__main__":
    unittest.main()
