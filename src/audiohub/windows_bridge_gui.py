# SPDX-License-Identifier: AGPL-3.0-only
"""Optional local Windows Tk graphical controls for the isolated TLS lab.

No Tk import at module load: terminal mode and package tests also run on
headless Pi/Linux. UI never writes settings, key material, or browser state.
"""
from __future__ import annotations

import queue
import ssl
import threading

from . import secure_lan
from .windows_bridge_setup import check_python_tls, validate_local_setup

CHANNEL_OPTIONS = {
    "Both speakers": "both",
    "Left speaker only": "left",
    "Right speaker only": "right",
    "Left then right (5 seconds)": "sequence",
}


def validate_fields(ip, pin, secret_path, minutes):
    """Pure, offline gate reused by Check and Start; no sockets."""
    check_python_tls()
    if not isinstance(minutes, str) or not minutes.isascii() or not minutes.isdecimal():
        raise ValueError("Choose 1–30 whole minutes")
    amount = secure_lan.validate_session_minutes(int(minutes))
    path = validate_local_setup(ip.strip(), pin.strip(), secret_path, amount)
    return (ip.strip(), pin.strip(), path, amount)


class BridgeWindow:
    def __init__(self, root, tk, ttk, filedialog, *, bridge=None):
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.bridge = secure_lan.run_bridge if bridge is None else bridge
        self.stop_event = threading.Event()
        self.results = queue.Queue()
        self.worker = None
        self.checked = False
        self.closing = False
        self.entries = {}
        self.status = tk.StringVar(value="Not connected. No network port opened.")
        self.root.title("RIVANOX AudioHub - isolated Windows TLS test")
        self.root.resizable(True, True)
        self.root.minsize(640, 510)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Windows audio bridge · isolated ALPHA",
                  font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Never use a home/work network. No driver or key is included.",
                  wraplength=580).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))
        fields = [
            ("Pi private IPv4 address", "192.168.10.30", None),
            ("Pinned Pi certificate SHA256 (from trusted offline source)", "", None),
            ("Private 32-byte shared-key file (path hidden)", "", "*"),
            ("Session minutes (1–30)", "10", None),
            ("Type ISOLATED to authorize one connection", "", None),
        ]
        for idx, (caption, initial, mask) in enumerate(fields):
            v = tk.StringVar(value=initial)
            key = ("ip", "pin", "key", "minutes", "confirmation")[idx]
            self.entries[key] = v
            ttk.Label(frame, text=caption, wraplength=570).grid(
                row=2 + 2 * idx, column=0, columnspan=3, sticky="w")
            entry = ttk.Entry(frame, textvariable=v, show=mask or "", width=70)
            entry.grid(row=3 + 2 * idx, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            v.trace_add("write", self._changed)
            if key == "key":
                ttk.Button(frame, text="Choose local file…", command=self._pick_file).grid(
                    row=3 + 2 * idx, column=2, sticky="e", padx=(8, 0))
        self.test_tone = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, text="Pi speaker test: quiet 5-second tone (no Scream driver)",
            variable=self.test_tone, command=self._changed,
        ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(5, 4))
        self.tone_channel = tk.StringVar(value="Both speakers")
        ttk.Label(frame, text="Speaker channel to verify (tone only):").grid(
            row=13, column=0, columnspan=3, sticky="w")
        self.tone_choice = ttk.Combobox(
            frame, textvariable=self.tone_channel,
            values=tuple(CHANNEL_OPTIONS), state="readonly", width=32,
        )
        self.tone_choice.grid(row=14, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.tone_channel.trace_add("write", self._changed)
        self.check_button = ttk.Button(frame, text="1 · Check locally (offline)", command=self.check)
        self.check_button.grid(row=15, column=0, sticky="ew", padx=(0, 8), pady=(8, 4))
        self.start_button = ttk.Button(frame, text="2 · Start isolated session", command=self.start)
        self.start_button.grid(row=15, column=1, sticky="ew", padx=(0, 8), pady=(8, 4))
        self.stop_button = ttk.Button(frame, text="Stop", command=self.stop)
        self.stop_button.grid(row=15, column=2, sticky="ew", pady=(8, 4))
        self.start_button.state(["disabled"])
        self.stop_button.state(["disabled"])
        ttk.Label(frame, textvariable=self.status, wraplength=580).grid(
            row=16, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="The Windows Scream driver must independently send only to 127.0.0.1:4010. "
                  "For speaker test the Scream driver is NOT needed. "
                  "Windows NTFS key-file permissions and real audible output are not verified.",
                  wraplength=580).grid(row=17, column=0, columnspan=3, sticky="w", pady=(12, 0))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=0)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._poll)

    def _running(self):
        return self.worker is not None and self.worker.is_alive()

    def _changed(self, *_args):
        self.checked = False
        if not self._running():
            self.start_button.state(["disabled"])

    def _pick_file(self):
        if self._running():
            return
        path = self.filedialog.askopenfilename(title="Choose private 32-byte key file")
        if path:
            self.entries["key"].set(path)

    def _channel(self):
        label = self.tone_channel.get()
        if label not in CHANNEL_OPTIONS:
            raise ValueError("Unknown speaker channel selection")
        return secure_lan.validate_tone_channel(CHANNEL_OPTIONS[label])

    def _params(self):
        if self.test_tone.get():
            self._channel()  # Fail closed before opening any TCP/UDP socket.
        return validate_fields(
            self.entries["ip"].get(), self.entries["pin"].get(),
            self.entries["key"].get(), self.entries["minutes"].get()
        )

    def check(self):
        if self._running():
            return False
        try:
            self._params()
        except (OSError, ValueError, RuntimeError, PermissionError):
            self.checked = False
            self.start_button.state(["disabled"])
            self.status.set("Local check failed. Recheck IP, key file, SHA256 and duration offline.")
            return False
        self.checked = True
        self.status.set("Local format and key file checked. Not connected; no Pi/driver proof.")
        if self.entries["confirmation"].get() == "ISOLATED":
            self.start_button.state(["!disabled"])
        return True

    def start(self):
        if self._running() or self.closing or not self.checked:
            return False
        if self.entries["confirmation"].get() != "ISOLATED":
            self.start_button.state(["disabled"])
            self.status.set("Type the exact word ISOLATED, then check locally again.")
            return False
        # Re-read the private key file and validate the same path immediately
        # before handing off. No network or driver configuration done here.
        try:
            ip, pin, path, minutes = self._params()
        except (OSError, ValueError, RuntimeError, PermissionError):
            self.checked = False
            self.start_button.state(["disabled"])
            self.status.set("Local setup changed; repeat the offline check.")
            return False
        self.checked = False
        self.stop_event.clear()
        self.start_button.state(["disabled"])
        self.check_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        tone = bool(self.test_tone.get())
        channel = self._channel() if tone else "both"
        self.status.set(("Authenticated 5-second " + channel + " speaker test; keep volume LOW.")
                        if tone else "Manually authorized Scream bridge running; no audio receipt proven.")
        self.worker = threading.Thread(
            target=self._execute, args=(ip, pin, path, minutes, tone, channel), daemon=False
        )
        self.worker.start()
        return True

    def _execute(self, ip, pin, path, minutes, tone=False, channel="both"):
        try:
            kwargs = dict(
                server_ip=ip, port=secure_lan.DEFAULT_PORT,
                udp_port=secure_lan.DEFAULT_UDP_PORT, key_file=path,
                pin_sha256=pin, session_minutes=minutes, isolated_lab=True,
                stop_event=self.stop_event,
            )
            if tone:
                kwargs["test_tone"] = True
                if channel != "both":
                    kwargs["test_channel"] = channel
            frames = self.bridge(**kwargs)
            self.results.put(("done", int(frames)))
        except (OSError, ValueError, RuntimeError, TimeoutError,
                ConnectionError, PermissionError, ssl.SSLError):
            # Never let underlying exceptions leak file paths, IPs or secrets.
            self.results.put(("error", None))
        except BaseException:
            self.results.put(("error", None))

    def stop(self):
        if not self._running():
            return
        self.stop_event.set()
        self.stop_button.state(["disabled"])
        self.status.set("Stop requested. Closing the manual lab connection.")

    def close(self):
        if self._running():
            self.closing = True
            self.stop()
        else:
            self.root.destroy()

    def _poll(self):
        try:
            while True:
                kind, value = self.results.get_nowait()
                self.worker = None
                self.stop_button.state(["disabled"])
                self.check_button.state(["!disabled"])
                self.start_button.state(["disabled"])
                if kind == "done":
                    self.status.set(
                        "Session ended. Accepted PCM frames: " + str(value) +
                        ". Human confirmation of actual Edifier sound is still required."
                    )
                else:
                    self.status.set(
                        "Connection stopped safely. Review isolated Pi, driver and keys offline."
                    )
        except queue.Empty:
            pass
        if self.closing and not self._running():
            self.root.destroy()
            return
        self.root.after(100, self._poll)


def launch():
    check_python_tls()
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog
    except ImportError as exc:
        raise RuntimeError("Tk interface unavailable; use --check-only terminal mode") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Desktop display unavailable; use terminal mode") from exc
    BridgeWindow(root, tk, ttk, filedialog)
    root.mainloop()
    return 0
