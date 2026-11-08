"""Read-only web API and deployment safety tests."""
import json
import shutil
import subprocess
import os
import socket
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
                                CLIENT_MAX_LIFETIME_SECONDS,
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

    def test_duplicate_top_level_status_fields_cannot_report_health(self):
        documents = (
            '{"updated_at":1,"updated_at":100,"usb_output":true}',
            '{"updated_at":100,"usb_output":false,"usb_output":true}',
            '{"updated_at":100,"active_routes":0,"active_routes":3}',
        )
        for document in documents:
            with self.subTest(document=document):
                self.status.write_text(document)
                self.status.chmod(0o600)
                report = read_public_status(path=self.status, now=101)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["usb_connected"])
                self.assertEqual(report["active_routes"], 0)

    def test_nested_duplicate_status_json_members_are_rejected(self):
        self.status.write_text(
            '{"updated_at":100,"usb_output":true,'
            '"extra":{"private":"a","private":"b"}}'
        )
        self.status.chmod(0o600)
        report = read_public_status(path=self.status, now=101)
        self.assertFalse(report["fresh"])
        self.assertFalse(report["usb_connected"])

    def test_nonfinite_status_json_numbers_cannot_report_healthy(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(literal=literal):
                self.status.write_text(
                    '{"updated_at":100,"usb_output":true,"extra":'
                    + literal + "}"
                )
                self.status.chmod(0o600)
                report = read_public_status(path=self.status, now=101)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["usb_connected"])
                self.assertEqual(report["active_routes"], 0)

    def test_overflowing_json_exponents_cannot_claim_fresh_web_status(self):
        for number in ("1e999", "-1e999", "9.99e9999"):
            with self.subTest(number=number):
                self.status.write_text(
                    '{"updated_at":100,"usb_output":true,"extra":' + number + "}"
                )
                self.status.chmod(0o600)
                report = read_public_status(path=self.status, now=101)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["usb_connected"])
                self.assertEqual(report["active_routes"], 0)

    def test_finite_json_exponent_in_unknown_field_is_safe(self):
        self.status.write_text(
            '{"updated_at":100,"usb_output":true,"extra":1.25e2}'
        )
        self.status.chmod(0o600)
        report = read_public_status(path=self.status, now=101)
        self.assertTrue(report["fresh"])
        self.assertTrue(report["usb_connected"])
        self.assertEqual(set(report), PUBLIC_FIELDS)
        self.assertNotIn("extra", report)

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

    def test_total_client_lifetime_is_fixed_in_addition_to_recv_timeout(self):
        self.assertEqual(CLIENT_MAX_LIFETIME_SECONDS, 15)
        self.assertEqual(CLIENT_READ_TIMEOUT_SECONDS, 5)
        self.assertLessEqual(CLIENT_MAX_LIFETIME_SECONDS, 3 * CLIENT_READ_TIMEOUT_SECONDS)

    def test_expired_slow_client_socket_is_shutdown_without_peer_logging(self):
        server = self.server()
        conn = mock.Mock()
        server._expire_client(conn)
        conn.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        conn.shutdown.side_effect = OSError("already closed")
        server._expire_client(conn)  # Never re-raise teardown failures.

    def test_worker_starts_and_cancels_total_lifetime_watchdog(self):
        server = self.server()
        client = mock.Mock()
        peer = ("127.0.0.1", 12345)
        self.assertTrue(server._client_slots.acquire(blocking=False))
        timer = mock.Mock()
        with mock.patch("audiohub.webserver.threading.Timer", return_value=timer) as factory, mock.patch.object(
            ThreadingHTTPServer, "process_request_thread"
        ) as handler:
            server.process_request_thread(client, peer)
            handler.assert_called_once_with(client, peer)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.args[0], 15)
        self.assertEqual(factory.call_args.kwargs["args"], (client,))
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once_with()
        timer.cancel.assert_called_once_with()
        self.assertTrue(server._client_slots.acquire(blocking=False))

    def test_watchdog_start_failure_still_releases_worker_slot(self):
        server = self.server()
        self.assertTrue(server._client_slots.acquire(blocking=False))
        timer = mock.Mock()
        timer.start.side_effect = RuntimeError("no timer thread")
        with mock.patch("audiohub.webserver.threading.Timer", return_value=timer):
            with self.assertRaisesRegex(RuntimeError, "no timer"):
                server.process_request_thread(mock.Mock(), ("127.0.0.1", 8765))
        timer.cancel.assert_called_once_with()
        self.assertTrue(server._client_slots.acquire(blocking=False))

    def test_generic_handler_exceptions_do_not_log_peer_identifiers(self):
        server = self.server()
        with mock.patch("sys.stderr") as sink:
            server.handle_error(
                mock.Mock(), ("192.168.1.42", "PRIVATE-DEVICE-MAC")
            )
        sink.write.assert_not_called()

    def test_existing_readonly_handler_routes_are_unmodified(self):
        self.assertIn("/api/status", Handler.do_GET.__code__.co_consts)
        self.assertTrue(callable(Handler.do_POST))
        self.assertIs(Handler.do_DELETE, Handler.do_POST)



def preview_status_reader_source():
    """Extract the shipped status poller, not a duplicate test implementation."""
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    start = source.index("  function requestRoutingRecheck() {")
    end = source.index("\n  function translate()", start)
    return source[start:end]


class BrowserStatusPollOrderTests(unittest.TestCase):
    def test_status_read_has_success_and_failure_generation_guards(self):
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        body = preview_status_reader_source()
        self.assertIn("let statusRequestId = 0;", source)
        self.assertIn("const requestId = ++statusRequestId;", body)
        self.assertEqual(body.count("if (requestId !== statusRequestId) return;"), 2)
        self.assertIn('fetch("./api/status", {cache: "no-store"})', body)
        self.assertIn("renderHardwareStatus();", body)
        self.assertIn("return readDeviceStatus();", body)
        self.assertIn("now - lastManualStatusRequestAt < 2000", body)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_actual_status_poller_latest_response_wins_over_stale_success_and_error(self):
        setup = r'''
const assert = require("node:assert/strict");
let statusRequestId = 0;
let deviceHealth = null;
let statusChecked = false;
let statusReceivedAt = null;
const performance = {now: () => 1000};
const events = [];
const transitions = () => events.filter((value, i) => i === 0 || value !== events[i - 1]);
const renderHardwareStatus = () => {
  events.push(deviceHealth === null ? "unknown"
    : (deviceHealth.usb_connected ? "connected" : "disconnected"));
};
const renderRoutingSummary = () => {};
const pending = [];
const fetch = () => new Promise((resolve, reject) => pending.push({resolve, reject}));
'''
        verify = r'''
async function check() {
  const slow = readDeviceStatus();
  const latest = readDeviceStatus();
  pending[1].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await latest;
  pending[0].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: false})});
  await slow;
  assert.deepEqual(transitions(), ["unknown", "connected"]);
  assert.equal(deviceHealth.usb_connected, true);

  const staleError = readDeviceStatus();
  const next = readDeviceStatus();
  pending[3].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: false})});
  await next;
  pending[2].reject(new Error("old request failed"));
  await staleError;
  assert.deepEqual(transitions(), ["unknown", "connected", "disconnected"]);

  let finishParsing;
  const slowParsing = readDeviceStatus();
  pending[4].resolve({ok: true,
    json: () => new Promise(resolve => {finishParsing = resolve;})});
  await Promise.resolve();
  assert.equal(typeof finishParsing, "function");
  const updated = readDeviceStatus();
  pending[5].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await updated;
  finishParsing({fresh: true, usb_connected: false});
  await slowParsing;
  assert.deepEqual(transitions(), ["unknown", "connected", "disconnected", "connected"]);

  const oldSuccess = readDeviceStatus();
  const latestError = readDeviceStatus();
  pending[7].reject(new Error("new request failed"));
  await latestError;
  pending[6].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await oldSuccess;
  assert.deepEqual(transitions(), ["unknown", "connected", "disconnected", "connected", "unknown"]);
  assert.equal(deviceHealth, null);
}
check().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_status_reader_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)



    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_manual_status_recheck_uses_live_api_and_limits_rapid_clicks(self):
        """Execute actual shipping on-demand check with the existing poller."""
        setup = r'''
const assert = require("node:assert/strict");
let statusRequestId = 0;
let deviceHealth = null;
let statusChecked = false;
let statusReceivedAt = null;
let lastManualStatusRequestAt = -Infinity;
let nowMs = 1000;
const performance = {now: () => nowMs};
const feedback = {textContent: ""};
const byId = id => id === "routing-recheck-status" ? feedback : null;
const tr = key => key === "routingRecheckRequested"
  ? "Status recheck requested" : key;
let rendered = 0;
const renderHardwareStatus = () => {rendered++;};
const renderRoutingSummary = () => {};
const pending = [];
const fetch = () => new Promise((resolve, reject) => pending.push({resolve, reject}));
'''
        verify = r'''
async function check() {
  const first = requestRoutingRecheck();
  assert.equal(pending.length, 1);
  assert.equal(feedback.textContent, "Status recheck requested");
  assert.equal(requestRoutingRecheck(), undefined);
  assert.equal(pending.length, 1);
  pending[0].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await first;
  assert.equal(deviceHealth.usb_connected, true);
  assert.equal(statusChecked, true);
  assert.equal(statusReceivedAt, 1000);

  // A new manual click after the throttle window gets a fresh request;
  // network failure must not leave an old successful measurement visible.
  nowMs = 3001;
  const failed = requestRoutingRecheck();
  assert.equal(pending.length, 2);
  pending[1].reject(new Error("device disconnected"));
  await failed;
  assert.equal(deviceHealth, null);
  assert.equal(statusReceivedAt, null);

  // An overlapping scheduled poll still wins, regardless of which
  // response finishes last.
  nowMs = 5002;
  const manual = requestRoutingRecheck();
  const scheduled = readDeviceStatus();
  assert.equal(pending.length, 4);
  pending[3].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: false})});
  await scheduled;
  pending[2].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await manual;
  assert.equal(deviceHealth.usb_connected, false);
  assert.equal(rendered > 0, true);
}
check().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_status_reader_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


def preview_hardware_view_source():
    """Use the real shipped status renderer and poller together."""
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    start = source.index("  function statusIsRecent() {")
    end = source.index("\n  function translate() {", start)
    return source[start:end]


class BrowserStatusClarityTests(unittest.TestCase):
    """Unavailable telemetry must never be described as unplugged hardware."""

    def test_five_languages_have_explicit_unavailable_hardware_status(self):
        base = (ROOT / "web" / "locales")
        for lang in ("en", "de", "es", "fr", "it"):
            with self.subTest(lang=lang):
                labels = json.loads((base / (lang + ".json")).read_text(encoding="utf-8"))
                self.assertTrue(labels["speakerStatusUnavailable"].strip())
                self.assertNotEqual(labels["speakerStatusUnavailable"], labels["speakerState"])
                self.assertNotEqual(labels["speakerStatusUnavailable"], labels["speakerDisconnected"])

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipping_renderer_distinguishes_initial_connected_disconnected_and_unavailable(self):
        setup = r'''
const assert = require("node:assert/strict");
const speaker = {textContent: ""};
const document = {querySelector(sel) {
  assert.equal(sel, '[data-t="speakerState"]');
  return speaker;
}};
let words = {
  speakerState: "Checking hardware",
  speakerConnected: "USB speakers connected",
  speakerDisconnected: "USB speakers disconnected",
  speakerStatusUnavailable: "Hardware status unavailable"
};
const tr = key => words[key] || key;
const byId = () => null; // No summary metrics in this speaker-only test.
let deviceHealth = null;
let statusChecked = false;
let statusRequestId = 0;
let statusReceivedAt = null;
let nowMs = 1000;
const performance = {now: () => nowMs};
const routingHistory = [];
let lastRoutingHistorySignature = null;
const pending = [];
const fetch = () => new Promise((resolve, reject) => pending.push({resolve, reject}));
'''
        verify = r'''
async function check() {
  renderHardwareStatus();
  assert.equal(speaker.textContent, "Checking hardware");
  assert.equal(statusChecked, false);

  const connected = readDeviceStatus();
  pending[0].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await connected;
  assert.equal(speaker.textContent, "USB speakers connected");

  const disconnected = readDeviceStatus();
  pending[1].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: false})});
  await disconnected;
  assert.equal(speaker.textContent, "USB speakers disconnected");

  const stale = readDeviceStatus();
  pending[2].resolve({ok: true, json: async () =>
    ({fresh: false, usb_connected: true})});
  await stale;
  assert.equal(speaker.textContent, "Hardware status unavailable");

  words.speakerStatusUnavailable = "Hardwarestatus nicht verfügbar";
  renderHardwareStatus();
  assert.equal(speaker.textContent, "Hardwarestatus nicht verfügbar");

  const failure = readDeviceStatus();
  pending[3].reject(new Error("API offline"));
  await failure;
  assert.equal(speaker.textContent, "Hardwarestatus nicht verfügbar");

  const malformed = readDeviceStatus();
  pending[4].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: "yes"})});
  await malformed;
  assert.equal(speaker.textContent, "Hardwarestatus nicht verfügbar");

  const slow = readDeviceStatus();
  const latest = readDeviceStatus();
  pending[6].resolve({ok: true, json: async () =>
    ({fresh: true, usb_connected: true})});
  await latest;
  pending[5].resolve({ok: true, json: async () =>
    ({fresh: false, usb_connected: false})});
  await slow;
  assert.equal(speaker.textContent, "USB speakers connected");
  assert.equal(statusChecked, true);

  // A stalled poll must never leave previous "connected" status forever.
  nowMs += 15001;
  renderHardwareStatus();
  assert.equal(speaker.textContent, "Hardwarestatus nicht verfügbar");
  const stalled = readDeviceStatus();
  assert.equal(speaker.textContent, "Hardwarestatus nicht verfügbar");
  pending[7].reject(new Error("network stalled"));
  await stalled;
  assert.equal(speaker.textContent, "Hardwarestatus nicht verfügbar");
}
check().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_hardware_view_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)



def preview_routing_summary_source():
    """Run the actual browser routing renderer rather than a copied version."""
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    start = source.index("  function statusIsRecent() {")
    end = source.index("\n  async function readDeviceStatus()", start)
    return source[start:end]


def preview_eq_guide_source():
    """Exercise the shipped browser EQ command builder, not a test copy."""
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    begin = source.index("  function buildLocalEqPreview(")
    end = source.index("  // A browser-only WHAT-IF layout.", begin)
    return source[begin:end]


class BrowserEqOwnerGuideTests(unittest.TestCase):
    """The EQ browser helper must be informative, localized and read-only."""

    def test_readonly_eq_browser_guide_is_accessible_and_translated(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for ident in (
            "eq-operator-guide", "eq-guide-note", "eq-guide-slot",
            "eq-guide-feedback", "eq-guide-preview-command",
            "eq-guide-compare-command", "eq-guide-compare-note",
            "eq-guide-copy-preview", "eq-guide-copy-compare",
            "eq-guide-copy-status", "eq-guide-transfer-mode",
            "eq-guide-transfer-source", "eq-guide-transfer-target",
            "eq-guide-transfer-note", "eq-guide-transfer-feedback",
            "eq-guide-transfer-command", "eq-guide-copy-transfer",
            "eq-guide-neutral-note", "eq-guide-neutral-slot",
            "eq-guide-neutral-feedback", "eq-guide-neutral-command",
            "eq-guide-copy-neutral", "eq-guide-preset-choice",
            "eq-guide-preset-curve",
        ):
            self.assertIn('id="' + ident + '"', html)
        self.assertEqual(html.count('id="eq-guide-slot"'), 1)
        self.assertIn('<details class="eq-operator-guide"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('id="eq-guide-preview-command" readonly', html)
        self.assertIn('id="eq-guide-compare-command" readonly', html)
        self.assertIn('--compare-staged --format overview', html)
        self.assertIn('one Pi overview', html)
        self.assertIn('not selected or active presets', html)
        self.assertIn('one on-disk file for all three inputs', html)
        self.assertIn('value="copy-eq"', html)
        self.assertIn('value="swap-eq"', html)
        self.assertIn('id="eq-guide-transfer-command" readonly', html)
        self.assertIn('id="eq-guide-neutral-command" readonly', html)
        self.assertIn('id="eq-guide-preset-choice"', html)
        self.assertIn('id="eq-guide-preset-curve" role="status"', html)
        self.assertIn('id="eq-guide-restore-hint" data-t="eqGuideRestoreHint"', html)
        self.assertIn("comparison_baseline", html)
        self.assertIn("restore-eq", html)
        self.assertNotIn("b1-ORIGINAL", html)
        for preset in ("flat", "warm", "voice", "detail"):
            self.assertIn('value="' + preset + '"', html)
        self.assertIn('aria-describedby="eq-guide-neutral-note eq-guide-neutral-feedback"', html)
        self.assertIn('byId("eq-guide-copy-neutral").addEventListener("click", () => copyEqGuideCommand("neutral"));', js)
        self.assertIn('aria-describedby="eq-guide-transfer-note eq-guide-transfer-feedback"', html)
        self.assertIn('byId("eq-guide-copy-transfer").addEventListener("click", () => copyEqGuideCommand("transfer"));', js)
        self.assertNotIn('--confirm-local-mixer-change', html)
        self.assertNotIn('--stage-saved', html)
        self.assertIn('byId("eq-guide-slot").addEventListener("change", renderEqGuide);', js)
        self.assertIn('if (BANDS.includes(key)) renderEqGuide();', js)
        self.assertIn('    renderEqGuide();\n    renderEqTransferGuide();\n    renderEqNeutralGuide();\n    renderRoutingPlan();', js)
        self.assertIn('navigator.clipboard.writeText(command)', js)
        self.assertNotIn("fetch(", preview_eq_guide_source())
        keys = {
            "eqGuideTitle", "eqGuideNotice", "eqGuideSlot", "eqGuideReady",
            "eqGuideInvalid", "eqGuidePreviewLabel", "eqGuideCopyPreview",
            "eqGuideCompareLabel", "eqGuideCompareNotice",
            "eqGuideCopyCompare", "eqGuideCopied", "eqGuideCopyUnavailable",
            "eqGuideTransferTitle", "eqGuideTransferNotice",
            "eqGuideTransferMode", "eqGuideTransferCopy", "eqGuideTransferSwap",
            "eqGuideTransferSource", "eqGuideTransferTarget",
            "eqGuideTransferReady", "eqGuideTransferInvalid",
            "eqGuideTransferCommandLabel", "eqGuideTransferCopyCommand",
            "eqGuideNeutralTitle", "eqGuideNeutralNotice",
            "eqGuideNeutralSlot", "eqGuideNeutralReady",
            "eqGuideNeutralInvalid", "eqGuideNeutralCommandLabel",
            "eqGuideNeutralCopyCommand", "eqGuidePresetChoice",
            "eqGuidePresetFlat", "eqGuidePresetWarm",
            "eqGuidePresetVoice", "eqGuidePresetDetail",
            "eqGuidePresetExampleOnly", "eqGuideRestoreHint",
        }
        for code in ("en", "de", "es", "fr", "it"):
            with self.subTest(locale=code):
                loc = json.loads(
                    (ROOT / "web" / "locales" / (code + ".json")).read_text(
                        encoding="utf-8"))
                self.assertTrue(keys.issubset(loc))
                self.assertTrue(all(type(loc[key]) is str and loc[key].strip()
                                    for key in keys))
                self.assertTrue(any(term in loc["eqGuideNotice"].lower()
                                    for term in ("not", "keine", "no", "pas", "non")))
                self.assertTrue(any(term in loc["eqGuideCompareNotice"].lower()
                                    for term in ("not", "nicht", "no", "pas", "non")))
                self.assertIn("comparison_baseline", loc["eqGuideRestoreHint"])
                self.assertIn("restore-eq", loc["eqGuideRestoreHint"])

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_real_eq_browser_commands_fail_closed_and_copy_only_readonly(self):
        setup = r'''
const assert = require("node:assert/strict");
const CHANNELS = ["music", "laptop", "tablet"];
const BANDS = ["bass", "mid", "treble"];
const state = {
  music: {bass: -3, mid: 2, treble: 1},
  laptop: {bass: 0, mid: 0, treble: 0},
  tablet: {bass: 12, mid: -12, treble: 6}
};
const elements = {
  "eq-guide-slot": {value: "music"},
  "eq-guide-preview-command": {value: ""},
  "eq-guide-compare-command": {
    value: "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.eq_setup --compare-staged --format overview"
  },
  "eq-guide-copy-preview": {disabled: false},
  "eq-guide-feedback": {textContent: "", dataset: {}},
  "eq-guide-copy-status": {textContent: ""}
};
const byId = id => elements[id];
const tr = key => key;
let copied = [];
const navigator = {
  clipboard: {writeText: async value => {copied.push(value);}}
};
const fetch = () => {throw new Error("No network or device call permitted");};
'''
        verify = r'''
async function check() {
  const expected = "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control " +
    "--preview set-eq-curve music -3 2 1";
  assert.equal(buildLocalEqPreview("music", state.music), expected);
  assert.equal(buildLocalEqPreview("tablet", state.tablet),
    "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control " +
    "--preview set-eq-curve tablet 12 -12 6");
  for (const input of ["unknown", "music;id", "../music", "", null]) {
    assert.equal(buildLocalEqPreview(input, state.music), null);
  }
  for (const invalid of [NaN, Infinity, 13, -13, 1.5, "3", {}, null]) {
    assert.equal(buildLocalEqPreview("music", {bass: invalid, mid: 2, treble: 1}), null);
  }
  assert.equal(buildLocalEqPreview("music", {bass: 1, mid: 2}), null);
  renderEqGuide();
  assert.equal(elements["eq-guide-preview-command"].value, expected);
  assert.equal(elements["eq-guide-copy-preview"].disabled, false);
  await copyEqGuideCommand("preview");
  assert.deepEqual(copied, [expected]);
  assert.equal(elements["eq-guide-copy-status"].textContent, "eqGuideCopied");
  await copyEqGuideCommand("compare");
  assert.equal(copied.length, 2);
  assert.equal(copied[1], elements["eq-guide-compare-command"].value);
  assert.ok(!copied.some(cmd => cmd.includes("--confirm-") ||
    cmd.includes("--stage-saved") || cmd.includes("curl")));

  state.music.treble = 5;
  renderEqGuide();
  assert.ok(elements["eq-guide-preview-command"].value.endsWith("music -3 2 5"));
  elements["eq-guide-slot"].value = "laptop";
  renderEqGuide();
  assert.ok(elements["eq-guide-preview-command"].value.endsWith("laptop 0 0 0"));
  elements["eq-guide-slot"].value = "tablet";
  renderEqGuide();
  assert.ok(elements["eq-guide-preview-command"].value.endsWith("tablet 12 -12 6"));

  elements["eq-guide-slot"].value = "music;bad";
  renderEqGuide();
  assert.equal(elements["eq-guide-preview-command"].value, "");
  assert.equal(elements["eq-guide-copy-preview"].disabled, true);
  assert.equal(elements["eq-guide-feedback"].dataset.invalid, "true");
  await copyEqGuideCommand("preview");
  assert.equal(copied.length, 2);

  elements["eq-guide-slot"].value = "music";
  state.music.bass = 900;
  renderEqGuide();
  assert.equal(elements["eq-guide-preview-command"].value, "");
  assert.equal(elements["eq-guide-copy-preview"].disabled, true);
  await copyEqGuideCommand("unknown");
  assert.equal(copied.length, 2);

  state.music.bass = -3;
  renderEqGuide();
  navigator.clipboard = null;
  await copyEqGuideCommand("preview");
  assert.equal(elements["eq-guide-copy-status"].textContent,
    "eqGuideCopyUnavailable");
  assert.equal(copied.length, 2);
}
check().catch(error => {console.error(error); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_eq_guide_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipped_eq_copy_swap_preview_uses_fixed_slots_and_never_mutates(self):
        """Use the actual shipped JS builder and clipboard handler, not a copy."""
        setup = r'''
const assert = require("node:assert/strict");
const CHANNELS = ["music", "laptop", "tablet"];
const BANDS = ["bass", "mid", "treble"];
const elements = {
  "eq-guide-transfer-mode": {value: "copy-eq"},
  "eq-guide-transfer-source": {value: "music"},
  "eq-guide-transfer-target": {value: "tablet"},
  "eq-guide-transfer-command": {value: ""},
  "eq-guide-copy-transfer": {disabled: false},
  "eq-guide-transfer-feedback": {textContent: "", dataset: {}},
  "eq-guide-copy-status": {textContent: ""}
};
const byId = id => elements[id];
const tr = key => key;
const copied = [];
let navigator = {clipboard: {
  writeText: async value => { copied.push(value); }
}};
const fetch = () => { throw new Error("No network or device operation"); };
'''
        verify = r'''
async function check() {
  const prefix = "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control ";
  const copy = prefix + "--preview copy-eq music tablet";
  const swap = prefix + "--preview swap-eq music tablet";
  assert.equal(buildLocalEqTransferPreview("copy-eq", "music", "tablet"), copy);
  assert.equal(buildLocalEqTransferPreview("swap-eq", "music", "tablet"), swap);
  assert.equal(buildLocalEqTransferPreview("swap-eq", "tablet", "music"),
    prefix + "--preview swap-eq tablet music");
  for (const mode of ["stage-eq", "set-eq", "confirm", ";id", "", null, 3]) {
    assert.equal(buildLocalEqTransferPreview(mode, "music", "tablet"), null);
  }
  for (const source of ["", null, "music;id", "../music", "unknown", {}, 1]) {
    assert.equal(buildLocalEqTransferPreview("copy-eq", source, "tablet"), null);
  }
  for (const target of ["", null, "tablet;echo", "../tablet", "unknown", {}, 1]) {
    assert.equal(buildLocalEqTransferPreview("copy-eq", "music", target), null);
  }
  for (const mode of ["copy-eq", "swap-eq"]) {
    for (const same of CHANNELS) {
      assert.equal(buildLocalEqTransferPreview(mode, same, same), null);
    }
  }
  renderEqTransferGuide();
  assert.equal(elements["eq-guide-transfer-command"].value, copy);
  assert.equal(elements["eq-guide-copy-transfer"].disabled, false);
  assert.equal(elements["eq-guide-transfer-feedback"].dataset.invalid, "false");
  await copyEqGuideCommand("transfer");
  assert.deepEqual(copied, [copy]);
  assert.equal(elements["eq-guide-copy-status"].textContent, "eqGuideCopied");

  elements["eq-guide-transfer-mode"].value = "swap-eq";
  renderEqTransferGuide();
  assert.equal(elements["eq-guide-transfer-command"].value, swap);
  await copyEqGuideCommand("transfer");
  assert.deepEqual(copied, [copy, swap]);
  assert.ok(copied.every(cmd => cmd.includes("--preview ") &&
    !cmd.includes("--confirm-") && !cmd.includes("--stage-saved")));

  // Changing to invalid/self-assignments MUST clear stale commands.
  elements["eq-guide-transfer-target"].value = "music";
  renderEqTransferGuide();
  assert.equal(elements["eq-guide-transfer-command"].value, "");
  assert.equal(elements["eq-guide-copy-transfer"].disabled, true);
  assert.equal(elements["eq-guide-transfer-feedback"].dataset.invalid, "true");
  await copyEqGuideCommand("transfer");
  assert.equal(copied.length, 2);

  elements["eq-guide-transfer-mode"].value = "invalid;whoami";
  elements["eq-guide-transfer-target"].value = "tablet";
  renderEqTransferGuide();
  assert.equal(elements["eq-guide-transfer-command"].value, "");
  assert.equal(elements["eq-guide-copy-transfer"].disabled, true);
  await copyEqGuideCommand("transfer");
  assert.equal(copied.length, 2);

  elements["eq-guide-transfer-mode"].value = "copy-eq";
  elements["eq-guide-transfer-source"].value = "laptop";
  renderEqTransferGuide();
  assert.equal(elements["eq-guide-transfer-command"].value,
    prefix + "--preview copy-eq laptop tablet");
  navigator.clipboard = null;
  await copyEqGuideCommand("transfer");
  assert.equal(elements["eq-guide-copy-status"].textContent,
    "eqGuideCopyUnavailable");
  assert.equal(copied.length, 2);
}
check().catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_eq_guide_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipped_eq_neutral_preview_is_one_slot_readonly_and_fail_closed(self):
        """Run real production JavaScript, including the clipboard boundary."""
        setup = r'''
const assert = require("node:assert/strict");
const CHANNELS = ["music", "laptop", "tablet"];
const BANDS = ["bass", "mid", "treble"];
const elements = {
  "eq-guide-neutral-slot": {value: "music"},
  "eq-guide-preset-choice": {value: "flat"},
  "eq-guide-preset-curve": {textContent: ""},
  "eq-guide-neutral-command": {value: ""},
  "eq-guide-copy-neutral": {disabled: false},
  "eq-guide-neutral-feedback": {textContent: "", dataset: {}},
  "eq-guide-copy-status": {textContent: ""}
};
const byId = id => elements[id];
const tr = key => key;
const copied = [];
let navigator = {clipboard: {writeText: async value => copied.push(value)}};
const fetch = () => {throw new Error("Unexpected device or network request");};
'''
        verify = r'''
async function check() {
  const prefix = "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control " +
    "--preview reset-eq ";
  for (const slot of CHANNELS) {
    assert.equal(buildLocalEqNeutralPreview(slot), prefix + slot);
  }
  for (const injected of [null, undefined, "", 0, 1, {}, [],
                           "music;id", "../tablet", "laptop --confirm-local-mixer-change",
                           "tablet\nrm -rf"]) {
    assert.equal(buildLocalEqNeutralPreview(injected), null);
  }
  renderEqNeutralGuide();
  assert.equal(elements["eq-guide-neutral-command"].value, prefix + "music");
  assert.equal(elements["eq-guide-copy-neutral"].disabled, false);
  assert.equal(elements["eq-guide-neutral-feedback"].dataset.invalid, "false");
  await copyEqGuideCommand("neutral");
  assert.deepEqual(copied, [prefix + "music"]);
  assert.equal(elements["eq-guide-copy-status"].textContent, "eqGuideCopied");
  assert.ok(copied.every(x => x.includes("--preview reset-eq ") &&
    !x.includes("--confirm-") && !x.includes("--stage-saved")));

  elements["eq-guide-neutral-slot"].value = "tablet";
  renderEqNeutralGuide();
  assert.equal(elements["eq-guide-neutral-command"].value, prefix + "tablet");
  await copyEqGuideCommand("neutral");
  assert.deepEqual(copied, [prefix + "music", prefix + "tablet"]);

  // Invalid selection clears prior valid command rather than copying stale text.
  elements["eq-guide-neutral-slot"].value = "music;bad";
  renderEqNeutralGuide();
  assert.equal(elements["eq-guide-neutral-command"].value, "");
  assert.equal(elements["eq-guide-copy-neutral"].disabled, true);
  assert.equal(elements["eq-guide-neutral-feedback"].dataset.invalid, "true");
  await copyEqGuideCommand("neutral");
  assert.equal(copied.length, 2);

  elements["eq-guide-neutral-slot"].value = "laptop";
  renderEqNeutralGuide();
  navigator.clipboard = null;
  await copyEqGuideCommand("neutral");
  assert.equal(elements["eq-guide-copy-status"].textContent,
    "eqGuideCopyUnavailable");
  assert.equal(copied.length, 2);
}
check().catch(error => {console.error(error); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_eq_guide_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipped_eq_sound_profiles_match_backend_and_never_execute(self):
        """Production browser and private CLI agree on actual profile numbers."""
        from audiohub import mixer_control
        setup = r'''
const assert = require("node:assert/strict");
const CHANNELS = ["music", "laptop", "tablet"];
const BANDS = ["bass", "mid", "treble"];
const elements = {
  "eq-guide-neutral-slot": {value: "music"},
  "eq-guide-preset-choice": {value: "warm"},
  "eq-guide-preset-curve": {textContent: ""},
  "eq-guide-neutral-command": {value: ""},
  "eq-guide-copy-neutral": {disabled: false},
  "eq-guide-neutral-feedback": {textContent: "", dataset: {}},
  "eq-guide-copy-status": {textContent: ""}
};
const byId = id => elements[id];
const tr = key => key;
const copied = [];
let navigator = {clipboard: {writeText: async cmd => copied.push(cmd)}};
const fetch = () => {throw new Error("No web/device commands permitted");};
'''
        check = r'''
async function test() {
  const prefix = "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview ";
  const expected = {
    flat: [0, 0, 0], warm: [3, 0, -1],
    voice: [-2, 3, 1], detail: [0, 1, 3]
  };
  assert.deepEqual(EQ_SOUND_PRESETS.flat, expected.flat);
  assert.deepEqual(EQ_SOUND_PRESETS.warm, expected.warm);
  assert.deepEqual(EQ_SOUND_PRESETS.voice, expected.voice);
  assert.deepEqual(EQ_SOUND_PRESETS.detail, expected.detail);
  for (const slot of CHANNELS) {
    assert.equal(buildLocalEqSoundPresetPreview(slot, "flat"),
      prefix + "reset-eq " + slot);
    for (const profile of ["warm", "voice", "detail"]) {
      const result = buildLocalEqSoundPresetPreview(slot, profile);
      assert.equal(result, prefix + "eq-preset " + slot + " " + profile);
      assert.ok(!result.includes("--confirm-local-mixer-change"));
      assert.ok(!result.includes("--stage-saved"));
    }
  }
  for (const slot of [null, "", "music;id", "../tablet", "music --confirm",
                      true, 0, {}, []]) {
    assert.equal(buildLocalEqSoundPresetPreview(slot, "warm"), null);
  }
  for (const profile of [null, "", "WARM", "warm;id",
                          "voice --confirm", 1, {}, []]) {
    assert.equal(buildLocalEqSoundPresetPreview("music", profile), null);
  }
  renderEqNeutralGuide();
  assert.equal(elements["eq-guide-neutral-command"].value,
    prefix + "eq-preset music warm");
  assert.equal(elements["eq-guide-copy-neutral"].disabled, false);
  assert.ok(elements["eq-guide-preset-curve"].textContent.includes("bass +3 dB"));
  assert.ok(elements["eq-guide-preset-curve"].textContent.includes("treble -1 dB"));
  assert.ok(elements["eq-guide-preset-curve"].textContent.includes("eqGuidePresetExampleOnly"));
  await copyEqGuideCommand("neutral");
  assert.deepEqual(copied, [prefix + "eq-preset music warm"]);
  elements["eq-guide-preset-choice"].value = "voice";
  renderEqNeutralGuide();
  assert.ok(elements["eq-guide-preset-curve"].textContent.includes("mid +3 dB"));
  await copyEqGuideCommand("neutral");
  assert.equal(copied[1], prefix + "eq-preset music voice");

  elements["eq-guide-preset-choice"].value = "voice;id";
  renderEqNeutralGuide();
  assert.equal(elements["eq-guide-neutral-command"].value, "");
  assert.equal(elements["eq-guide-copy-neutral"].disabled, true);
  assert.equal(elements["eq-guide-neutral-feedback"].dataset.invalid, "true");
  assert.equal(elements["eq-guide-preset-curve"].textContent, "eqGuideNeutralInvalid");
  await copyEqGuideCommand("neutral");
  assert.equal(copied.length, 2);

  elements["eq-guide-preset-choice"].value = "detail";
  elements["eq-guide-neutral-slot"].value = "../music";
  renderEqNeutralGuide();
  assert.equal(elements["eq-guide-neutral-command"].value, "");
  assert.equal(elements["eq-guide-copy-neutral"].disabled, true);

  elements["eq-guide-neutral-slot"].value = "tablet";
  renderEqNeutralGuide();
  assert.ok(elements["eq-guide-neutral-command"].value.endsWith("eq-preset tablet detail"));
  navigator.clipboard = null;
  await copyEqGuideCommand("neutral");
  assert.equal(elements["eq-guide-copy-status"].textContent,
    "eqGuideCopyUnavailable");
  assert.equal(copied.length, 2);
  console.log(JSON.stringify({
    warm: EQ_SOUND_PRESETS.warm, voice: EQ_SOUND_PRESETS.voice,
    detail: EQ_SOUND_PRESETS.detail
  }));
}
test().catch(err => {console.error(err); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_eq_guide_source() + "\n" + check],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        browser = json.loads(result.stdout.strip())
        self.assertEqual(browser, {
            k: list(v) for k, v in mixer_control.EQ_PRESET_CURVES.items()
        })


class BrowserRoutingSummaryTests(unittest.TestCase):
    """Read-only routing diagnostics do not turn missing health into zero."""

    def test_existing_status_api_drives_localized_read_only_summary(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for key in ("routing-routes", "routing-bluetooth", "routing-channels",
                    "routing-freshness", "routing-diagnostic",
                    "routing-export", "routing-export-status"):
            self.assertIn('id="' + key + '"', html)
        for key in ("active_routes", "bluetooth_sources", "virtual_channel_count"):
            self.assertIn('"' + key + '"', preview_routing_summary_source())
        self.assertIn("renderRoutingSummary();", source)
        self.assertIn('fetch("./api/status", {cache: "no-store"})', source)
        self.assertNotIn('method: "POST"', source)
        self.assertIn('role="status"', html)
        self.assertIn("Read-only device counts", html)
        self.assertIn('id="routing-recheck"', html)
        self.assertIn('id="routing-recheck-status" role="status"', html)
        self.assertIn('id="routing-history-list"', html)
        self.assertIn('id="routing-history-clear"', html)
        self.assertIn('id="routing-history-status" role="status"', html)
        for field in ("routing-compare-file", "routing-compare-clear",
                      "routing-compare-status", "routing-compare-table",
                      "routing-compare-old-usb", "routing-compare-new-active_routes",
                      "routing-compare-diff-bluetooth_sources"):
            self.assertIn('id="' + field + '"', html)
        self.assertIn('aria-describedby="routing-compare-note"', html)
        self.assertIn('byId("routing-compare-file").addEventListener("change", loadRoutingComparison);', source)
        self.assertIn('byId("routing-compare-clear").addEventListener("click", clearRoutingComparison);', source)
        for field in ("routing-compare-observations-table",
                      "routing-compare-note-old-usb_output_audio",
                      "routing-compare-note-diff-bluetooth_source_audio",
                      "routing-compare-note-new-usb_audio_after_reconnect"):
            self.assertIn('id="' + field + '"', html)
        self.assertIn('addEventListener("change", renderManualComparison)', source)
        self.assertIn('byId("routing-history-clear").addEventListener("click", clearRoutingHistory);', source)
        self.assertIn('byId("routing-recheck").addEventListener("click", requestRoutingRecheck);', source)
        self.assertIn('byId("routing-export").addEventListener("click", downloadRoutingDiagnostics);', source)
        for field in ("routing-observation-usb", "routing-observation-bluetooth",
                      "routing-observation-three", "routing-observation-dual-bt",
                      "routing-observation-usb-reconnect", "routing-observations-reset"):
            self.assertIn('id="' + field + '"', html)
        self.assertIn('aria-describedby="routing-observations-note"', html)
        self.assertIn('id="routing-observations-reset-status" role="status"', html)
        self.assertIn('byId("routing-observations-reset").addEventListener("click", resetManualSoundObservations);', source)
        self.assertIn('value="not_tested"', html)
        self.assertIn('value="heard"', html)
        self.assertIn('value="not_heard"', html)

    def test_five_locale_labels_have_safe_nonplayback_disclaimer(self):
        keys = {
            "routingTitle", "routingNotice", "routingRoutes",
            "routingBluetooth", "routingChannels", "routingPending",
            "routingRecent", "routingUnavailable", "routingRecheck",
            "routingRecheckRequested", "routingDiagPending",
            "routingDiagUnavailable", "routingDiagUsbMissing",
            "routingDiagNoChannels", "routingDiagNoRoutes",
            "routingDiagNoBluetooth", "routingDiagCountsAvailable",
            "routingExport", "routingExportRequested", "routingExportUnavailable",
            "routingObservationsTitle", "routingObservationsNote", "routingObservationUsb",
            "routingObservationBluetooth", "routingObservationThree",
            "routingNotTested", "routingHeard", "routingNotHeard",
            "routingObservationDualBluetooth", "routingObservationUsbReconnect",
            "routingObservationsReset", "routingObservationsCleared",
            "routingHistoryTitle", "routingHistoryNote", "routingHistoryEmpty",
            "routingHistoryClear", "routingHistoryCleared",
            "routingCompareTitle", "routingCompareNote", "routingCompareFile",
            "routingCompareClear", "routingCompareNoFile", "routingCompareInvalid",
            "routingCompareTooLarge", "routingCompareReady",
            "routingCompareCurrentUnavailable", "routingCompareColumnMetric",
            "routingCompareColumnPrevious", "routingCompareColumnCurrent",
            "routingCompareColumnChange", "routingCompareUsb", "routingCompareChanged",
            "routingCompareUnchanged", "routingCompareUnknown", "routingCompareCleared",
            "routingCompareObservationsTitle", "routingCompareObservationsNote",
            "routingCompareObservationsCurrent"
        }
        for code in ("en", "de", "es", "fr", "it"):
            with self.subTest(code=code):
                messages = json.loads(
                    (ROOT / "web" / "locales" / (code + ".json")).read_text(encoding="utf-8")
                )
                self.assertTrue(keys.issubset(messages))
                self.assertTrue(all(messages[key].strip() for key in keys))
                self.assertNotEqual(messages["routingPending"], messages["routingRecent"])
                self.assertNotEqual(messages["routingUnavailable"], messages["routingRecent"])

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipped_routing_renderer_fails_closed_and_retranslates(self):
        setup = r'''
const assert = require("node:assert/strict");
const ids = ["routing-routes", "routing-bluetooth",
             "routing-channels", "routing-freshness", "routing-diagnostic"];
const elements = Object.fromEntries(ids.map(id => [id, {textContent: ""}]));
const byId = id => elements[id] || null;
const get = id => elements[id].textContent;
let words = {
  routingPending: "Waiting for first status check",
  routingRecent: "Recent device report",
  routingUnavailable: "Routing status unavailable",
  routingDiagPending: "Waiting for diagnosis",
  routingDiagUnavailable: "No recent device report",
  routingDiagUsbMissing: "Check USB speakers",
  routingDiagNoChannels: "Check virtual input channels",
  routingDiagNoRoutes: "Check input routing",
  routingDiagNoBluetooth: "No Bluetooth sources; other inputs may still work",
  routingDiagCountsAvailable: "Verify audible playback manually"
};
const tr = key => words[key] || key;
let deviceHealth = null;
let statusChecked = false;
let nowMs = 1000;
let statusReceivedAt = 1000;
const performance = {now: () => nowMs};
const routingHistory = [];
let lastRoutingHistorySignature = null;
'''
        verify = r'''
function values() {
  return ["routing-routes", "routing-bluetooth", "routing-channels"].map(get);
}
renderRoutingSummary();
assert.deepEqual(values(), ["—", "—", "—"]);
assert.equal(get("routing-freshness"), "Waiting for first status check");
assert.equal(get("routing-diagnostic"), "Waiting for diagnosis");

statusChecked = true;
// Invalid, stale or missing snapshots must not claim zero audio routes.
for (const snapshot of [null, {}, {fresh: false, usb_connected: true,
    active_routes: 3, bluetooth_sources: 2, virtual_channel_count: 3},
    {fresh: true, usb_connected: "yes", active_routes: 2,
     bluetooth_sources: 1, virtual_channel_count: 2}]) {
  deviceHealth = snapshot;
  renderRoutingSummary();
  assert.deepEqual(values(), ["—", "—", "—"]);
  assert.equal(get("routing-freshness"), "Routing status unavailable");
  assert.equal(get("routing-diagnostic"), "No recent device report");
}
// A genuine zero is meaningful only in a fresh, complete, bounded report.
deviceHealth = {fresh: true, usb_connected: false,
  active_routes: 0, bluetooth_sources: 0, virtual_channel_count: 0};
renderRoutingSummary();
assert.deepEqual(values(), ["0", "0", "0"]);
assert.equal(get("routing-freshness"), "Recent device report");
assert.equal(get("routing-diagnostic"), "Check USB speakers");

// Missing channels take priority over routes once USB has been found.
deviceHealth = {fresh: true, usb_connected: true,
  active_routes: 0, bluetooth_sources: 0, virtual_channel_count: 0};
renderRoutingSummary();
assert.equal(get("routing-diagnostic"), "Check virtual input channels");

// A present virtual channel but no routes leads to routing guidance.
deviceHealth.virtual_channel_count = 1;
renderRoutingSummary();
assert.equal(get("routing-diagnostic"), "Check input routing");

// Routes without Bluetooth sources are not automatically a failure.
deviceHealth.active_routes = 1;
renderRoutingSummary();
assert.equal(get("routing-diagnostic"),
  "No Bluetooth sources; other inputs may still work");

// Different valid counts do not leak source identifiers or assert audible sound.
deviceHealth = {fresh: true, usb_connected: true,
  active_routes: 3, bluetooth_sources: 2, virtual_channel_count: 3,
  mac: "PRIVATE-DEVICE-MAC", ssid: "PRIVATE-SSID"};
renderRoutingSummary();
assert.deepEqual(values(), ["3", "2", "3"]);
assert.equal(get("routing-diagnostic"), "Verify audible playback manually");
assert.ok(!JSON.stringify(elements).includes("PRIVATE"));

// Accept no string coercion, negative counts, fractions, arrays or oversized data.
for (const bad of [
  {active_routes: "2", bluetooth_sources: 1, virtual_channel_count: 1},
  {active_routes: -1, bluetooth_sources: 1, virtual_channel_count: 1},
  {active_routes: 4, bluetooth_sources: 1, virtual_channel_count: 1},
  {active_routes: 2, bluetooth_sources: 3, virtual_channel_count: 1},
  {active_routes: 2, bluetooth_sources: 1, virtual_channel_count: 4},
  {active_routes: 2.5, bluetooth_sources: 1, virtual_channel_count: 1},
  {active_routes: 2, bluetooth_sources: [], virtual_channel_count: 1}
]) {
  deviceHealth = {fresh: true, usb_connected: true, ...bad};
  renderRoutingSummary();
  assert.deepEqual(values(), ["—", "—", "—"]);
  assert.equal(get("routing-diagnostic"), "No recent device report");
}
// Locale changes translate the status without altering fresh counts.
deviceHealth = {fresh: true, usb_connected: true,
  active_routes: 2, bluetooth_sources: 1, virtual_channel_count: 3};
words.routingRecent = "Aktueller Gerätebericht";
words.routingDiagCountsAvailable = "Wiedergabe manuell prüfen";
renderRoutingSummary();
assert.deepEqual(values(), ["2", "1", "3"]);
assert.equal(get("routing-freshness"), "Aktueller Gerätebericht");
assert.equal(get("routing-diagnostic"), "Wiedergabe manuell prüfen");
// Browser-local expiry must remove misleading routing measurements.
nowMs += 15001;
renderRoutingSummary();
assert.deepEqual(values(), ["—", "—", "—"]);
assert.equal(get("routing-freshness"), "Routing status unavailable");
assert.equal(get("routing-diagnostic"), "No recent device report");
// Browser monotonic clock rollback or reset must fail closed.
nowMs = 999;
assert.equal(safeRoutingHealth(), null);
'''
        program = setup + "\n" + preview_routing_summary_source() + "\n" + verify
        result = subprocess.run(
            ["node", "-e", program],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)



    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_actual_browser_history_is_bounded_redacted_and_clearable(self):
        """No raw API IDs or persistence in the shipped routing change log."""
        setup = r'''
const assert = require("node:assert/strict");
const list = {
  children: [],
  replaceChildren() {this.children = [];},
  append(item) {this.children.push(item);}
};
const feedback = {textContent: ""};
const byId = id => id === "routing-history-list" ? list :
  id === "routing-history-status" ? feedback : null;
const document = {createElement(tag) {
  assert.equal(tag, "li");
  return {textContent: ""};
}};
const words = {
  routingHistoryEmpty: "No recent changes",
  routingHistoryCleared: "History cleared",
  routingRoutes: "Routes",
  routingBluetooth: "Bluetooth",
  routingChannels: "Channels",
  routingUnavailable: "Status unavailable",
  speakerConnected: "USB connected",
  speakerDisconnected: "USB disconnected"
};
const tr = key => words[key] || key;
let deviceHealth = null;
let statusChecked = false;
let statusReceivedAt = 1000;
let nowMs = 1000;
const performance = {now: () => nowMs};
const routingHistory = [];
let lastRoutingHistorySignature = null;
'''
        verify = r'''
renderRoutingSummary();
assert.equal(routingHistory.length, 0);
assert.equal(list.children[0].textContent, "No recent changes");
statusChecked = true;
deviceHealth = {fresh: true, usb_connected: true,
  active_routes: 0, bluetooth_sources: 0, virtual_channel_count: 1,
  mac: "SENSITIVE-MAC", ssid: "SENSITIVE-SSID", owner: "SECRET-OWNER"};
renderRoutingSummary();
assert.equal(routingHistory.length, 1);
assert.deepEqual(Object.keys(routingHistory[0].health),
  ["usb_connected", "active_routes", "bluetooth_sources", "virtual_channel_count"]);
assert.equal(routingHistory[0].health.active_routes, 0);
assert.match(routingHistory[0].at_utc, /^\d{4}-\d{2}-\d{2}T/);
assert.equal(safeRoutingHistoryReport()[0].active_routes, 0);
renderRoutingSummary();
assert.equal(routingHistory.length, 1); // Re-render is not another event.

// Frequent real changes use a bounded in-memory history.
for (let i = 0; i < 15; i++) {
  deviceHealth.usb_connected = i % 2 === 0;
  deviceHealth.active_routes = i % 3;
  deviceHealth.bluetooth_sources = i % 2;
  renderRoutingSummary();
}
assert.equal(routingHistory.length, 8);
assert.equal(list.children.length, 8);
assert.ok(!JSON.stringify(routingHistory).includes("SENSITIVE"));
assert.ok(!JSON.stringify(list.children).includes("SENSITIVE"));
assert.ok(!JSON.stringify(list.children).includes("SECRET"));

// Language changes update visible labels but never create observations.
const count = routingHistory.length;
words.routingRoutes = "Routen";
renderRoutingSummary();
assert.equal(routingHistory.length, count);
assert.ok(list.children.some(node => node.textContent.includes("Routen")));

// A hung API makes the report unavailable; this is a transition, not zero.
nowMs = 16001;
renderRoutingSummary();
assert.equal(routingHistory.length, 8);
assert.equal(routingHistory[routingHistory.length - 1].health, null);
assert.ok(list.children[list.children.length - 1].textContent.includes("Status unavailable"));
clearRoutingHistory();
assert.equal(routingHistory.length, 0);
assert.equal(list.children[0].textContent, "No recent changes");
assert.equal(feedback.textContent, "History cleared");
renderRoutingSummary();
assert.equal(routingHistory.length, 0); // No immediate reappearance.
nowMs = 17000;
statusReceivedAt = 17000;
renderRoutingSummary();
assert.equal(routingHistory.length, 1);
assert.equal(routingHistory[0].health.active_routes, 2);
// Malformed status must not reach the log, even with additional IDs.
deviceHealth.active_routes = "PRIVATE-INVALID";
renderRoutingSummary();
assert.equal(routingHistory[routingHistory.length - 1].health, null);
assert.ok(!JSON.stringify(routingHistory).includes("PRIVATE"));
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_routing_summary_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_previous_local_v4_report_compare_excludes_secrets_and_handles_stale(self):
        """Run the shipped importer and table projection without network access."""
        setup = r'''
const assert = require("node:assert/strict");
const keys = ["usb", "active_routes", "bluetooth_sources", "virtual_channel_count"];
const hearingFields = ["usb_output_audio", "bluetooth_source_audio",
  "three_inputs_simultaneously_audible",
  "two_bluetooth_sources_simultaneously_audible",
  "usb_audio_after_reconnect"];
const hearingSelects = ["usb", "bluetooth", "three", "dual-bt", "usb-reconnect"];
const ids = ["routing-compare-table", "routing-compare-status", "routing-compare-file",
  "routing-compare-observations-table",
  ...hearingSelects.map(key => "routing-observation-" + key),
  ...keys.flatMap(key => ["routing-compare-old-" + key,
    "routing-compare-new-" + key, "routing-compare-diff-" + key]),
  ...hearingFields.flatMap(key => ["routing-compare-note-old-" + key,
    "routing-compare-note-new-" + key, "routing-compare-note-diff-" + key])];
const nodes = Object.fromEntries(ids.map(id => [id, {textContent: "", hidden: true, value: ""}]));
nodes["routing-observation-usb"].value = "heard";
nodes["routing-observation-bluetooth"].value = "heard";
nodes["routing-observation-three"].value = "not_tested";
nodes["routing-observation-dual-bt"].value = "not_heard";
nodes["routing-observation-usb-reconnect"].value = "not_tested";
const byId = id => nodes[id] || null;
const words = {
  routingCompareUnknown: "Unavailable",
  routingCompareReady: "Compared",
  routingCompareCurrentUnavailable: "Live status unavailable",
  routingCompareInvalid: "Invalid report",
  routingCompareTooLarge: "Report too large",
  routingCompareCleared: "Comparison cleared",
  speakerConnected: "USB connected",
  speakerDisconnected: "USB disconnected",
  routingCompareChanged: "Changed",
  routingCompareUnchanged: "Unchanged",
  routingHeard: "Heard",
  routingNotHeard: "Not heard",
  routingNotTested: "Not tested"
};
const tr = key => words[key] || key;
let comparisonBaseline = null;
let comparisonManualBaseline = null;
let comparisonLoadId = 0;
let deviceHealth = {fresh: true, usb_connected: true,
  active_routes: 3, bluetooth_sources: 2, virtual_channel_count: 3,
  mac: "SENSITIVE-MAC", ssid: "SENSITIVE-SSID", owner: "PRIVATE-OWNER"};
let statusChecked = true;
let statusReceivedAt = 1000;
let nowMs = 1000;
const performance = {now: () => nowMs};
const routingHistory = [];
let lastRoutingHistorySignature = null;
const fetch = () => {throw new Error("Unexpected network use");};
const fileInput = data => ({files: [data], value: "previous.json"});
const report = {
  format: "audiohub.routing-diagnostics.v4", status: "recent",
  usb_connected: false, active_routes: 1, bluetooth_sources: 1,
  virtual_channel_count: 2, owner: "PRIVATE-OWNER",
  mac: "SENSITIVE-MAC", ssid: "SENSITIVE-SSID",
  recent_routing_changes: [{owner: "SECRET-OWNER"}],
  operator_observations: {
    usb_output_audio: "heard",
    bluetooth_source_audio: "not_heard",
    three_inputs_simultaneously_audible: "not_tested",
    two_bluetooth_sources_simultaneously_audible: "heard",
    usb_audio_after_reconnect: "PRIVATE-INJECTION"
  }
};
const file = value => ({size: 350, text: async () => JSON.stringify(value)});
const get = id => nodes[id].textContent;
'''
        verify = r'''
async function check() {
  assert.equal(safeImportedRoutingReport(null), null);
  assert.equal(safeImportedRoutingReport({...report, status: "unavailable"}), null);
  assert.equal(safeImportedRoutingReport({...report,
    format: "audiohub.routing-diagnostics.v3"}), null);
  assert.equal(safeImportedRoutingReport({...report, active_routes: 4}), null);
  assert.equal(safeImportedRoutingReport({...report, bluetooth_sources: "1"}), null);
  assert.equal(safeImportedRoutingReport({...report, usb_connected: "false"}), null);
  assert.equal(safeImportedRoutingReport({...report, virtual_channel_count: -1}), null);
  assert.equal(safeImportedRoutingReport({...report, active_routes: 1.2}), null);
  assert.deepEqual(Object.keys(safeImportedRoutingReport(report)),
    ["usb_connected", "active_routes", "bluetooth_sources", "virtual_channel_count"]);
  assert.ok(!JSON.stringify(safeImportedRoutingReport(report)).includes("PRIVATE"));
  assert.deepEqual(Object.keys(safeImportedManualObservations(report)), hearingFields);
  assert.deepEqual(Object.values(safeImportedManualObservations(report)),
    ["heard", "not_heard", "not_tested", "heard", null]);
  assert.deepEqual(Object.values(safeImportedManualObservations({
    operator_observations: {usb_output_audio: ["heard"], bluetooth_source_audio: "<img>"}
  })), [null, null, null, null, null]);

  renderRoutingComparison();
  assert.equal(nodes["routing-compare-table"].hidden, true);
  assert.equal(nodes["routing-compare-observations-table"].hidden, true);
  const chosen = fileInput(file(report));
  await loadRoutingComparison({target: chosen});
  assert.equal(chosen.value, "");
  assert.equal(nodes["routing-compare-table"].hidden, false);
  assert.equal(get("routing-compare-status"), "Compared");
  assert.equal(get("routing-compare-old-usb"), "USB disconnected");
  assert.equal(get("routing-compare-new-usb"), "USB connected");
  assert.equal(get("routing-compare-diff-usb"), "Changed");
  assert.equal(get("routing-compare-old-active_routes"), "1");
  assert.equal(get("routing-compare-new-active_routes"), "3");
  assert.equal(get("routing-compare-diff-active_routes"), "+2");
  assert.equal(get("routing-compare-diff-bluetooth_sources"), "+1");
  assert.equal(get("routing-compare-diff-virtual_channel_count"), "+1");
  assert.equal(nodes["routing-compare-observations-table"].hidden, false);
  assert.equal(get("routing-compare-note-old-usb_output_audio"), "Heard");
  assert.equal(get("routing-compare-note-new-usb_output_audio"), "Heard");
  assert.equal(get("routing-compare-note-diff-usb_output_audio"), "Unchanged");
  assert.equal(get("routing-compare-note-old-bluetooth_source_audio"), "Not heard");
  assert.equal(get("routing-compare-note-diff-bluetooth_source_audio"), "Changed");
  assert.equal(get("routing-compare-note-diff-three_inputs_simultaneously_audible"), "Unchanged");
  assert.equal(get("routing-compare-note-diff-two_bluetooth_sources_simultaneously_audible"), "Changed");
  assert.equal(get("routing-compare-note-old-usb_audio_after_reconnect"), "Unavailable");
  assert.equal(get("routing-compare-note-diff-usb_audio_after_reconnect"), "Unavailable");
  // Changing a human dropdown can be compared without changing hardware status.
  nodes["routing-observation-bluetooth"].value = "not_heard";
  renderManualComparison();
  assert.equal(get("routing-compare-note-diff-bluetooth_source_audio"), "Unchanged");
  assert.ok(!JSON.stringify(nodes).includes("PRIVATE"));
  assert.ok(!JSON.stringify(nodes).includes("SENSITIVE"));
  assert.ok(!JSON.stringify(nodes).includes("SECRET"));

  // Counts can fall; an unchanged USB state is distinct from changed state.
  deviceHealth.active_routes = 0;
  deviceHealth.usb_connected = false;
  renderRoutingComparison();
  assert.equal(get("routing-compare-diff-active_routes"), "-1");
  assert.equal(get("routing-compare-diff-usb"), "Unchanged");

  // Local age expiry blocks comparisons to an untrustworthy live snapshot.
  nowMs = 16001;
  renderRoutingComparison();
  assert.equal(get("routing-compare-status"), "Live status unavailable");
  assert.equal(get("routing-compare-new-active_routes"), "Unavailable");
  assert.equal(get("routing-compare-diff-active_routes"), "Unavailable");
  assert.equal(get("routing-compare-old-active_routes"), "1");
  assert.equal(get("routing-compare-note-diff-usb_output_audio"), "Unchanged");

  // Wrong format and unreadable/oversized files fail closed.
  await loadRoutingComparison({target: fileInput(file({...report, status: "pending"}))});
  assert.equal(nodes["routing-compare-table"].hidden, true);
  assert.equal(nodes["routing-compare-observations-table"].hidden, true);
  assert.equal(comparisonManualBaseline, null);
  assert.equal(get("routing-compare-status"), "Invalid report");
  await loadRoutingComparison({target: fileInput({size: 65537, text: async () => "{}"})});
  assert.equal(get("routing-compare-status"), "Report too large");
  await loadRoutingComparison({target: fileInput({size: 4, text: async () => "{"})});
  assert.equal(get("routing-compare-status"), "Invalid report");
  await loadRoutingComparison({target: fileInput({size: NaN, text: async () => "{}"})});
  assert.equal(get("routing-compare-status"), "Report too large");

  // A pending earlier read cannot overwrite a newer report or a clear.
  nowMs = 1000;
  let resolveOld;
  const older = loadRoutingComparison({target: fileInput({
    size: 200, text: () => new Promise(resolve => {resolveOld = resolve;})
  })});
  await loadRoutingComparison({target: fileInput(file(report))});
  resolveOld(JSON.stringify({...report, active_routes: 0}));
  await older;
  assert.equal(comparisonBaseline.active_routes, 1);
  let resolveAfterClear;
  const pending = loadRoutingComparison({target: fileInput({
    size: 200, text: () => new Promise(resolve => {resolveAfterClear = resolve;})
  })});
  clearRoutingComparison();
  resolveAfterClear(JSON.stringify(report));
  await pending;
  assert.equal(comparisonBaseline, null);
  assert.equal(comparisonManualBaseline, null);
  assert.equal(nodes["routing-compare-table"].hidden, true);
  assert.equal(nodes["routing-compare-observations-table"].hidden, true);
  assert.equal(get("routing-compare-status"), "Comparison cleared");
}
check().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_routing_summary_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_actual_browser_export_only_copies_bounded_public_fields(self):
        """Click exports a safe, fixed JSON schema and no device identifiers."""
        setup = r'''
const assert = require("node:assert/strict");
const Date = class {
  toISOString() {return "2026-11-07T15:00:00.000Z";}
  toLocaleTimeString() {return "15:00:00";}
};
let nowMs = 1000;
let statusReceivedAt = 1000;
const performance = {now: () => nowMs};
const routingHistory = [];
let lastRoutingHistorySignature = null;
const elements = {
  "routing-export-status": {textContent: ""},
  "routing-observation-usb": {value: "not_tested"},
  "routing-observation-bluetooth": {value: "not_tested"},
  "routing-observation-three": {value: "not_tested"},
  "routing-observation-dual-bt": {value: "not_tested"},
  "routing-observation-usb-reconnect": {value: "not_tested"},
  "routing-observations-reset-status": {textContent: ""}
};
const byId = id => elements[id] || null;
const tr = key => ({
  routingExportRequested: "Download requested",
  routingExportUnavailable: "Download unavailable",
  routingObservationsCleared: "Observations cleared"
})[key] || key;
let deviceHealth = null;
let statusChecked = false;
const links = [];
const blobs = [];
const revoked = [];
class Blob {
  constructor(parts, opts) {this.parts = parts; this.opts = opts;}
}
const URL = {
  createObjectURL(blob) {blobs.push(blob); return "blob:local-report";},
  revokeObjectURL(url) {revoked.push(url);}
};
const setTimeout = (fn, delay) => {
  assert.equal(delay, 1000);
  fn();
};
const document = {
  body: {append(node) {links.push(node);}},
  createElement(tag) {
    assert.equal(tag, "a");
    return {
      href: "", download: "", hidden: false,
      click() {this.clicked = true;},
      remove() {this.removed = true;}
    };
  }
};
const exportContent = () => blobs[blobs.length - 1].parts.join("");
'''
        verify = r'''
const fields = ["format", "recorded_at_browser_utc", "status", "usb_connected",
  "active_routes", "bluetooth_sources", "virtual_channel_count",
  "recent_routing_changes", "operator_observations", "hardware_verified",
  "audible_playback_verified", "release_approved"];
const observations = {
  usb_output_audio: "not_tested",
  bluetooth_source_audio: "not_tested",
  three_inputs_simultaneously_audible: "not_tested",
  two_bluetooth_sources_simultaneously_audible: "not_tested",
  usb_audio_after_reconnect: "not_tested"
};
const clock = "2026-11-07T15:00:00.000Z";
const checkDownload = expected => {
  downloadRoutingDiagnostics();
  const report = JSON.parse(exportContent());
  assert.deepEqual(Object.keys(report), fields);
  assert.deepEqual(report, expected);
  const link = links[links.length - 1];
  assert.equal(link.download, "audiohub-routing-diagnostics.json");
  assert.equal(link.href, "blob:local-report");
  assert.equal(link.clicked, true);
  assert.equal(link.removed, true);
  assert.equal(elements["routing-export-status"].textContent, "Download requested");
  assert.equal(revoked[revoked.length - 1], "blob:local-report");
  return report;
};
const unverified = {
  recent_routing_changes: [],
  operator_observations: observations,
  hardware_verified: false,
  audible_playback_verified: false,
  release_approved: false
};
checkDownload({
  format: "audiohub.routing-diagnostics.v4",
  recorded_at_browser_utc: clock, status: "pending",
  usb_connected: null, active_routes: null, bluetooth_sources: null,
  virtual_channel_count: null, ...unverified
});
statusChecked = true;
deviceHealth = {fresh: true, usb_connected: true,
  active_routes: 2, bluetooth_sources: 1, virtual_channel_count: 3,
  mac: "PRIVATE-MAC", ssid: "PRIVATE-WIFI", username: "PRIVATE-OWNER",
  hidden: {key: "SECRET"}};
checkDownload({
  format: "audiohub.routing-diagnostics.v4",
  recorded_at_browser_utc: clock, status: "recent",
  usb_connected: true, active_routes: 2, bluetooth_sources: 1,
  virtual_channel_count: 3, ...unverified
});
assert.ok(!exportContent().includes("PRIVATE"));
assert.ok(!exportContent().includes("SECRET"));
assert.ok(!exportContent().includes("MAC"));
// The local history includes only strictly validated state transitions.
captureRoutingHistory(safeRoutingHealth());
assert.equal(routingHistory.length, 1);
const eventFields = ["observed_at_browser_utc", "status", "usb_connected",
  "active_routes", "bluetooth_sources", "virtual_channel_count"];
const event = {observed_at_browser_utc: clock, status: "recent",
  usb_connected: true, active_routes: 2, bluetooth_sources: 1,
  virtual_channel_count: 3};
downloadRoutingDiagnostics();
const exportedWithHistory = JSON.parse(exportContent());
assert.deepEqual(exportedWithHistory.recent_routing_changes, [event]);
assert.deepEqual(Object.keys(exportedWithHistory.recent_routing_changes[0]), eventFields);
assert.ok(!exportContent().includes("PRIVATE"));
assert.ok(!exportContent().includes("SECRET"));
// A corrupted in-memory entry is independently rechecked and fails closed.
routingHistory.push({
  at_utc: "PRIVATE-OWNER",
  health: {usb_connected: true, active_routes: 99,
    bluetooth_sources: 1, virtual_channel_count: 3, mac: "PRIVATE-MAC"}
});
const corrupted = safeRoutingHistoryReport()[1];
assert.deepEqual(Object.keys(corrupted), eventFields);
assert.equal(corrupted.observed_at_browser_utc, null);
assert.equal(corrupted.status, "unavailable");
assert.equal(corrupted.active_routes, null);
assert.ok(!JSON.stringify(safeRoutingHistoryReport()).includes("PRIVATE"));
// Report output has a strict eight-event cap even if internal state is tampered.
for (let i = 0; i < 15; i++) {
  routingHistory.push({at_utc: clock,
    health: {usb_connected: true, active_routes: i % 4,
      bluetooth_sources: i % 3, virtual_channel_count: i % 4}});
}
assert.equal(safeRoutingHistoryReport().length, 8);
assert.equal(safeRoutingReport().recent_routing_changes.length, 8);
routingHistory.length = 0;
// Operator choices have no automatic hardware-certification side effect.
elements["routing-observation-usb"].value = "heard";
elements["routing-observation-bluetooth"].value = "not_heard";
elements["routing-observation-three"].value = "heard";
elements["routing-observation-dual-bt"].value = "heard";
elements["routing-observation-usb-reconnect"].value = "not_heard";
assert.deepEqual(manualSoundObservations(), {
  usb_output_audio: "heard",
  bluetooth_source_audio: "not_heard",
  three_inputs_simultaneously_audible: "heard",
  two_bluetooth_sources_simultaneously_audible: "heard",
  usb_audio_after_reconnect: "not_heard"
});
assert.equal(safeRoutingReport().hardware_verified, false);
assert.equal(safeRoutingReport().audible_playback_verified, false);
assert.equal(safeRoutingReport().release_approved, false);
// Unknown or injected select values are not copied to the report.
elements["routing-observation-usb"].value = "PRIVATE-NAME";
assert.equal(manualSoundObservations().usb_output_audio, "not_tested");
assert.deepEqual(safeRoutingReport().operator_observations, {
  usb_output_audio: "not_tested",
  bluetooth_source_audio: "not_heard",
  three_inputs_simultaneously_audible: "heard",
  two_bluetooth_sources_simultaneously_audible: "heard",
  usb_audio_after_reconnect: "not_heard"
});
// A reset must only clear manual selections, not change real device status.
const beforeReset = safeRoutingReport();
resetManualSoundObservations();
assert.deepEqual(manualSoundObservations(), observations);
assert.equal(elements["routing-observations-reset-status"].textContent,
  "Observations cleared");
assert.equal(elements["routing-export-status"].textContent, "");
assert.deepEqual(safeRoutingReport().active_routes, beforeReset.active_routes);
// Reset human selections before expecting the all-unchecked report.
elements["routing-observation-usb"].value = "not_tested";
elements["routing-observation-bluetooth"].value = "not_tested";
elements["routing-observation-three"].value = "not_tested";
elements["routing-observation-dual-bt"].value = "not_tested";
elements["routing-observation-usb-reconnect"].value = "not_tested";
deviceHealth = {fresh: false, usb_connected: true,
  active_routes: 2, bluetooth_sources: 1, virtual_channel_count: 3,
  mac: "PRIVATE-MAC"};
checkDownload({
  format: "audiohub.routing-diagnostics.v4",
  recorded_at_browser_utc: clock, status: "unavailable",
  usb_connected: null, active_routes: null, bluetooth_sources: null,
  virtual_channel_count: null, ...unverified
});
deviceHealth = {fresh: true, usb_connected: true,
  active_routes: "2", bluetooth_sources: 1, virtual_channel_count: 3};
assert.equal(safeRoutingHealth(), null);
assert.equal(safeRoutingReport().status, "unavailable");
deviceHealth.active_routes = 0;
assert.equal(safeRoutingReport().active_routes, 0);
assert.equal(safeRoutingReport().status, "recent");
// Even an API-fresh report must expire in the browser during hung polls.
nowMs = 16001;
assert.equal(safeRoutingHealth(), null);
assert.equal(safeRoutingReport().status, "unavailable");
assert.equal(safeRoutingReport().active_routes, null);
assert.equal(safeRoutingReport().hardware_verified, false);
// Non-supporting browsers receive an honest failure instead of false success.
URL.createObjectURL = () => {throw new Error("blob URLs unsupported");};
downloadRoutingDiagnostics();
assert.equal(elements["routing-export-status"].textContent, "Download unavailable");
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_routing_summary_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
