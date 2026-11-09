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
        win.tone_channel = _Value("Both speakers")
        win.cert_path = _Value("")
        win.entries = {
            "ip": _Value("192.168.10.30"), "pin": _Value("f" * 64),
            "key": _Value(str(self.key)), "minutes": _Value("1"),
            "confirmation": _Value("ISOLATED"),
        }
        win.checked = False
        win.closing = False
        win.worker = None
        win.active_soundcheck_channel = None
        win.last_soundcheck = None
        win.stop_event = threading.Event()
        win.results = queue.Queue()
        win.start_button = _Button()
        win.stop_button = _Button()
        win.check_button = _Button()
        win.report_button = _Button()
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
        self.assertEqual(window.last_soundcheck["channel"], "both")
        self.assertEqual(window.last_soundcheck["frames"], 4)
        self.assertTrue(recorded[0]["test_tone"])
        self.assertTrue(recorded[0]["isolated_lab"])
        self.assertIn("Human confirmation", window.status.get())

    def test_gui_explicit_left_right_sequence_uses_only_authenticated_bridge(self):
        for label, code in (
            ("Left speaker only", "left"),
            ("Right speaker only", "right"),
            ("Left then right (5 seconds)", "sequence"),
        ):
            with self.subTest(label=label):
                calls = []
                def fake_bridge(**kwargs):
                    calls.append(kwargs)
                    return 3
                win = self._fake_window(fake_bridge)
                win.test_tone.set(True)
                win.tone_channel.set(label)
                self.assertTrue(win.check())
                self.assertTrue(win.start())
                win.worker.join(timeout=5)
                self.assertFalse(win.worker.is_alive())
                win._poll()
                self.assertEqual(win.last_soundcheck["channel"], code)
                self.assertTrue(any("!disabled" in e for e in win.report_button.events))
                self.assertEqual(calls[0]["test_channel"], code)
                self.assertTrue(calls[0]["isolated_lab"])
                self.assertTrue(calls[0]["test_tone"])
                self.assertNotIn(str(self.key), win.status.get())

    def test_bad_or_changed_gui_channel_refuses_start_offline(self):
        bridge = mock.Mock()
        win = self._fake_window(bridge)
        win.test_tone.set(True)
        win.tone_channel.set("Left speaker only")
        self.assertTrue(win.check())
        win.tone_channel.set("UNKNOWN")
        self.assertFalse(win.start())
        bridge.assert_not_called()
        self.assertFalse(win.check())
        bridge.assert_not_called()

    def test_report_not_available_before_real_tone_attempt(self):
        win = self._fake_window(mock.Mock(return_value=10))
        self.assertFalse(win.record_observation())
        self.assertTrue(win.check())
        self.assertTrue(win.start())
        win.worker.join(timeout=5)
        win._poll()
        # A normal Windows Scream audio session is not the manual tone test.
        self.assertIsNone(win.last_soundcheck)
        self.assertFalse(any("!disabled" in x for x in win.report_button.events))

    def test_failed_tone_session_can_record_failure_without_audio_claim(self):
        def fake_bridge(**kwargs):
            raise ConnectionError("this secret local path must not be disclosed")
        win = self._fake_window(fake_bridge)
        win.test_tone.set(True)
        win.tone_channel.set("Left then right (5 seconds)")
        self.assertTrue(win.check())
        self.assertTrue(win.start())
        win.worker.join(timeout=5)
        win._poll()
        self.assertEqual(win.last_soundcheck, {
            "channel": "sequence", "outcome": "connection_failed", "frames": 0,
        })
        self.assertTrue(any("!disabled" in x for x in win.report_button.events))
        self.assertNotIn("secret local path", win.status.get())

    def test_manual_observation_dialog_saves_only_on_explicit_operator_action(self):
        win = self._fake_window(mock.Mock())
        win.last_soundcheck = {
            "channel": "sequence", "outcome": "completed", "frames": 500,
        }
        win.tk = mock.Mock()
        win.tk.StringVar.side_effect = lambda value=None: _Value(value)
        win.tk.BooleanVar.side_effect = lambda value=None: _Value(value)
        win.ttk = mock.Mock()
        win.filedialog = mock.Mock()
        outfile = Path(self.key.parent) / "operator-observation.json"
        win.filedialog.asksaveasfilename.return_value = str(outfile)
        self.assertTrue(win.record_observation())
        self.assertFalse(outfile.exists())  # Dialog alone never writes.
        # Two string variables for L/R selection; one for in-dialog status.
        # Track actual entries by the combobox textvariables.
        dropdown_vars = [
            c.kwargs["textvariable"] for c in win.ttk.Combobox.call_args_list
        ]
        self.assertEqual(len(dropdown_vars), 2)
        dropdown_vars[0].set("Heard from expected speaker")
        dropdown_vars[1].set("No sound")
        confirm = win.ttk.Checkbutton.call_args.kwargs["variable"]
        confirm.set(True)
        save_buttons = [
            c for c in win.ttk.Button.call_args_list
            if c.kwargs.get("text", "").startswith("Save private JSON")
        ]
        self.assertEqual(len(save_buttons), 1)
        save_buttons[0].kwargs["command"]()
        self.assertTrue(outfile.exists())
        import json
        recorded = json.loads(outfile.read_text(encoding="ascii"))
        self.assertEqual(recorded["left_speaker_observation"], "heard_expected")
        self.assertEqual(recorded["right_speaker_observation"], "silent")
        self.assertTrue(recorded["operator_physically_listened"])
        self.assertFalse(recorded["hardware_verified"])
        self.assertFalse(recorded["release_ready"])
        self.assertNotIn(str(self.key), outfile.read_text(encoding="ascii"))
        self.assertNotIn("192.168.", outfile.read_text(encoding="ascii"))
        win.tk.Toplevel.return_value.destroy.assert_called_once()

    def test_report_dialog_refuses_heard_claim_without_personally_listening(self):
        win = self._fake_window(mock.Mock())
        win.last_soundcheck = {
            "channel": "left", "outcome": "connection_failed", "frames": 0,
        }
        win.tk = mock.Mock()
        win.tk.StringVar.side_effect = lambda value=None: _Value(value)
        win.tk.BooleanVar.side_effect = lambda value=None: _Value(value)
        win.ttk = mock.Mock()
        win.filedialog = mock.Mock()
        self.assertTrue(win.record_observation())
        labels = [
            c.kwargs["textvariable"] for c in win.ttk.Combobox.call_args_list
        ]
        labels[0].set("Heard from expected speaker")
        save = next(c.kwargs["command"] for c in win.ttk.Button.call_args_list
                    if c.kwargs.get("text", "").startswith("Save private JSON"))
        save()
        win.filedialog.asksaveasfilename.assert_not_called()

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
