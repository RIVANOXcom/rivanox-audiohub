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
            "routingObservationsReset", "routingObservationsCleared"
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
    def test_actual_browser_export_only_copies_bounded_public_fields(self):
        """Click exports a safe, fixed JSON schema and no device identifiers."""
        setup = r'''
const assert = require("node:assert/strict");
const Date = class {toISOString() {return "2026-11-07T15:00:00.000Z";}};
let nowMs = 1000;
let statusReceivedAt = 1000;
const performance = {now: () => nowMs};
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
  "operator_observations", "hardware_verified",
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
  operator_observations: observations,
  hardware_verified: false,
  audible_playback_verified: false,
  release_approved: false
};
checkDownload({
  format: "audiohub.routing-diagnostics.v3",
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
  format: "audiohub.routing-diagnostics.v3",
  recorded_at_browser_utc: clock, status: "recent",
  usb_connected: true, active_routes: 2, bluetooth_sources: 1,
  virtual_channel_count: 3, ...unverified
});
assert.ok(!exportContent().includes("PRIVATE"));
assert.ok(!exportContent().includes("SECRET"));
assert.ok(!exportContent().includes("MAC"));
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
  format: "audiohub.routing-diagnostics.v3",
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
