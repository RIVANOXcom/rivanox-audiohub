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
        return time.monotonic() < self.deadline and self.paired_count() < PAIRING_LIMIT

    def refresh(self):
        value = dbus.Boolean(self.allowed())
        self.adapter.Set("org.bluez.Adapter1", "Pairable", value)
        self.adapter.Set("org.bluez.Adapter1", "Discoverable", value)
        return True

    def changed(self, interface, change, invalidated, path=None):
        if interface == "org.bluez.Device1" and change.get("Paired") and path:
            device = dbus.Interface(self.bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
            device.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
            self.refresh()

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        if not self.allowed():
            raise Rejected("Pairing is closed")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        p = dbus.Interface(self.bus.get_object("org.bluez", device), "org.freedesktop.DBus.Properties")
        if not p.Get("org.bluez.Device1", "Trusted") and not self.allowed():
            raise Rejected("Untrusted device")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        if not self.allowed():
            raise Rejected("Pairing is closed")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        raise Rejected("PIN entry unsupported")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        raise Rejected("Passkey entry unsupported")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        pass


def main():
    DBusGMainLoop(set_as_default=True)
    PairingAgent(dbus.SystemBus())
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
