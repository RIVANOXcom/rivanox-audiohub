# SPDX-License-Identifier: AGPL-3.0-only
"""Experimental first-boot BlueZ NoInputNoOutput pairing agent.

Limited to a ten-minute, at-most-two-new-device window while unowned.
This window does not provide cryptographic ownership proof: no public stable
image may ship until device claiming and re-pairing are security reviewed.
"""
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from .pairing_policy import PENDING_TTL_SECONDS, may_trust_pair, valid_pending

PATH = "/org/rivanox/audiohub/agent"
BOOT_WINDOW = 600
PAIRING_LIMIT = 2


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class PairingAgent(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, PATH)
        self.bus = bus
        self.deadline = time.monotonic() + BOOT_WINDOW
        mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
        mgr.RegisterAgent(PATH, "NoInputNoOutput")
        mgr.RequestDefaultAgent(PATH)
        obj = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        self.manager = obj
        # Rebooting a previously paired device must not reopen guest pairing.
        self.initial_pairing_allowed = self.paired_count() == 0
        self.pending = {}
        managed = obj.GetManagedObjects()
        adapters = [path for path, attrs in managed.items() if "org.bluez.Adapter1" in attrs]
        if not adapters:
            raise RuntimeError("No Bluetooth adapter available")
        self.adapter = dbus.Interface(bus.get_object("org.bluez", adapters[0]), "org.freedesktop.DBus.Properties")
        self.adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
        self.adapter.Set("org.bluez.Adapter1", "Alias", dbus.String("AudioHub"))
        self.adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))
        bus.add_signal_receiver(
            self.changed, dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged", path_keyword="path"
        )
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)

    def paired_count(self):
        return sum(
            bool(interfaces["org.bluez.Device1"].get("Paired"))
            for interfaces in self.manager.GetManagedObjects().values()
            if "org.bluez.Device1" in interfaces
        )

    def allowed(self):
        return (self.initial_pairing_allowed and time.monotonic() < self.deadline
                and self.paired_count() < PAIRING_LIMIT)

    def refresh(self):
        value = dbus.Boolean(self.allowed())
        self.adapter.Set("org.bluez.Adapter1", "Pairable", value)
        self.adapter.Set("org.bluez.Adapter1", "Discoverable", value)
        return True

    def _prune_pending(self):
        now = time.monotonic()
        self.pending = {path: expires for path, expires in self.pending.items()
                        if valid_pending(now, expires)}

    def _authorize_candidate(self, device):
        if not self.allowed():
            raise Rejected("Pairing is closed")
        self._prune_pending()
        path = str(device)
        if path not in self.pending and len(self.pending) >= PAIRING_LIMIT:
            raise Rejected("Concurrent pairing slots exhausted")
        self.pending[path] = time.monotonic() + PENDING_TTL_SECONDS

    def changed(self, interface, change, invalidated, path=None):
        if interface != "org.bluez.Device1" or change.get("Paired") is not True or not path:
            return
        self._prune_pending()
        candidate = str(path) in self.pending
        if not may_trust_pair(self.initial_pairing_allowed, time.monotonic(),
                              self.deadline, self.paired_count(), candidate):
            self.refresh()
            return
        self.pending.pop(str(path), None)
        device = dbus.Interface(self.bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
        device.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
        self.refresh()

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        self._authorize_candidate(device)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        p = dbus.Interface(self.bus.get_object("org.bluez", device), "org.freedesktop.DBus.Properties")
        self._prune_pending()
        if not p.Get("org.bluez.Device1", "Trusted") and str(device) not in self.pending:
            raise Rejected("Untrusted or unapproved device")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        self._authorize_candidate(device)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        raise Rejected("PIN entry unsupported")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        raise Rejected("Passkey entry unsupported")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        self.pending.clear()


def main():
    DBusGMainLoop(set_as_default=True)
    PairingAgent(dbus.SystemBus())
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
