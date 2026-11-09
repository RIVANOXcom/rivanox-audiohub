"""Offline checks for the Windows GUI; no Tk display or real audio needed."""
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import secure_lan as transport
from audiohub import windows_bridge_gui as gui


class _Value:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class _Button:
    def __init__(self):
        self.events = []
    def state(self, names):
        self.events.append(tuple(names))


class GuiOfflineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.key = Path(tmp.name) / "key"
        self.key.write_bytes(os.urandom(32))
        if os.name == "posix":
            self.key.chmod(0o600)

    def test_validate_fields_only_accepts_existing_private_settings(self):
        ip, pin, path, length = gui.validate_fields(
            " 192.168.10.30 ", "f" * 64, str(self.key), "10")
        self.assertEqual((ip, pin, path, length),
                         ("192.168.10.30", "f" * 64, str(self.key), 10))
        for params in (
            ("8.8.8.8", "f" * 64, str(self.key), "10"),
            ("192.168.10.30", "f" * 63, str(self.key), "10"),
            ("192.168.10.30", "f" * 64, str(self.key), "0"),
            ("192.168.10.30", "f" * 64, str(self.key), "31"),
            ("192.168.10.30", "f" * 64, str(self.key), "1.5"),
            ("192.168.10.30", "f" * 64, "/missing-key", "10"),
        ):
            with self.subTest(params=params), self.assertRaises((ValueError, OSError)):
                gui.validate_fields(*params)

    def _fake_window(self, bridge):
        win = gui.BridgeWindow.__new__(gui.BridgeWindow)
        win.test_tone = _Value(False)
        win.entries = {
            "ip": _Value("192.168.10.30"), "pin": _Value("f" * 64),
            "key": _Value(str(self.key)), "minutes": _Value("1"),
            "confirmation": _Value("ISOLATED"),
        }
        win.checked = False
        win.closing = False
        win.worker = None
        win.stop_event = threading.Event()
        win.results = queue.Queue()
        win.start_button = _Button()
        win.stop_button = _Button()
        win.check_button = _Button()
        win.status = _Value("Not connected")
        win.bridge = bridge
        win.root = mock.Mock()
        return win

    def test_check_then_explicit_consent_then_stop_without_tk_display(self):
        bridge_started = threading.Event()
        calls = []
        def fake_bridge(**kwargs):
            calls.append(kwargs)
            bridge_started.set()
            self.assertTrue(kwargs["stop_event"].wait(timeout=5))
            return 7
        window = self._fake_window(fake_bridge)
        self.assertTrue(window.check())
        self.assertTrue(window.checked)
        self.assertTrue(window.start())
        self.assertTrue(bridge_started.wait(timeout=5))
        window.stop()
        window.worker.join(timeout=5)
        self.assertFalse(window.worker.is_alive())
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["isolated_lab"])
        self.assertEqual(calls[0]["session_minutes"], 1)
        self.assertEqual(calls[0]["key_file"], str(self.key))
        window._poll()
        self.assertIn("7", window.status.get())
        self.assertNotIn(str(self.key), window.status.get())
        self.assertTrue(any("disabled" in call for call in window.stop_button.events))

    def test_tone_mode_uses_authenticated_bridge_without_driver(self):
        recorded = []
        def fake_bridge(**kwargs):
            recorded.append(kwargs)
            return 4
        window = self._fake_window(fake_bridge)
        window.test_tone.set(True)
        self.assertTrue(window.check())
        self.assertTrue(window.start())
        window.worker.join(timeout=5)
        self.assertFalse(window.worker.is_alive())
        window._poll()
        self.assertTrue(recorded[0]["test_tone"])
        self.assertTrue(recorded[0]["isolated_lab"])
        self.assertIn("Human confirmation", window.status.get())

    def test_cannot_start_without_manual_confirmation_or_valid_preflight(self):
        bridge = mock.Mock()
        win = self._fake_window(bridge)
        self.assertFalse(win.start())
        self.assertTrue(win.check())
        win.entries["confirmation"].set("wrong")
        self.assertFalse(win.start())
        bridge.assert_not_called()
        self.assertTrue(win.check())
        win.entries["confirmation"].set("ISOLATED")
        win.entries["pin"].set("invalid")
        self.assertFalse(win.start())
        bridge.assert_not_called()

    def test_gui_module_imports_without_tk_or_linux_fcntl(self):
        # No graphical dependencies imported until explicit --gui invocation.
        source = Path(gui.__file__).read_text(encoding="utf-8")
        pre = source.split("def launch():", 1)[0]
        self.assertNotIn("\nimport tkinter", pre)
        self.assertNotIn("\nfrom tkinter import", pre)

    def test_cancel_signal_exits_loopback_forwarder_without_transmission(self):
        stop = threading.Event()
        stop.set()
        udp = mock.Mock()
        stream = mock.Mock()
        count = transport.forward_loopback_pcm(
            udp, stream, time.monotonic() + 60, stop_event=stop)
        self.assertEqual(count, 0)
        udp.recvfrom.assert_not_called()
        stream.sendall.assert_not_called()

    def test_cancel_before_socket_open_skips_all_network(self):
        stop = threading.Event()
        stop.set()
        with mock.patch.object(transport.socket, "create_connection") as dial:
            count = transport.run_bridge(
                server_ip="192.168.10.30", port=4044, udp_port=4010,
                key_file=self.key, pin_sha256="f" * 64, isolated_lab=True,
                stop_event=stop)
            self.assertEqual(count, 0)
            dial.assert_not_called()


if __name__ == "__main__":
    unittest.main()
