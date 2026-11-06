# SPDX-License-Identifier: AGPL-3.0-only
"""Experimental first-boot BlueZ NoInputNoOutput pairing agent.

Limited to a ten-minute, at-most-two-new-device window while unowned.
This window does not provide cryptographic ownership proof: no public stable
image may ship until device claiming and re-pairing are security reviewed.
"""
import re
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

PATH = "/org/rivanox/audiohub/agent"
BOOT_WINDOW = 600
PAIRING_LIMIT = 2
AUTHORIZATION_TTL = 45
BLUEZ_DEVICE_PATH = re.compile(
    r"/org/bluez/hci[0-9]{1,3}/dev_(?:[0-9A-F]{2}_){5}[0-9A-F]{2}\Z"
)


def authorized_pairing_signal(device, pending, initial_allowed, deadline,
                              paired_count, now):
    """Only a previously authorized, fresh BlueZ device may receive trust."""
    return (
        isinstance(device, str) and BLUEZ_DEVICE_PATH.fullmatch(device) is not None
        and type(pending) is dict
        and initial_allowed is True
        and isinstance(now, (float, int)) and now < deadline
        and type(paired_count) is int and 1 <= paired_count <= PAIRING_LIMIT
        and device in pending and now < pending[device]
    )



class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class PairingAgent(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, PATH)
        self.bus = bus
        self.deadline = float(BOOT_WINDOW)  # Linux monotonic uptime, independent of service restart
        self.pending_authorizations = {}
        mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
        mgr.RegisterAgent(PATH, "NoInputNoOutput")
        mgr.RequestDefaultAgent(PATH)
        obj = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        self.manager = obj
        # Rebooting a previously paired device must not reopen guest pairing.
        self.initial_pairing_allowed = self.paired_count() == 0
        managed = obj.GetManagedObjects()
        adapters = [path for path, attrs in managed.items() if "org.bluez.Adapter1" in attrs]
        if not adapters:
            raise RuntimeError("No Bluetooth adapter available")
        self.adapter = dbus.Interface(bus.get_object("org.bluez", adapters[0]), "org.freedesktop.DBus.Properties")
        self.adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
        self.adapter.Set("org.bluez.Adapter1", "Alias", dbus.String("AudioHub"))
        self.adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(False))
        self.adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(False))
        self.adapter.Set("org.bluez.Adapter1", "PairableTimeout", dbus.UInt32(BOOT_WINDOW))
        self.adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(BOOT_WINDOW))
        bus.add_signal_receiver(
            self.changed, dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged", path_keyword="path",
            bus_name="org.bluez"
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
        if not (self.initial_pairing_allowed and time.monotonic() < self.deadline):
            return False
        try:
            return self.paired_count() < PAIRING_LIMIT
        except Exception:
            # BlueZ reporting failure must close, not reopen, pairing.
            return False

    def authorize_pending(self, device):
        if not isinstance(device, str) or BLUEZ_DEVICE_PATH.fullmatch(device) is None:
            raise Rejected("Invalid Bluetooth device path")
        if not self.allowed():
            raise Rejected("Pairing is closed")
        now = time.monotonic()
        self.pending_authorizations = {
            path: expires for path, expires in self.pending_authorizations.items()
            if expires > now
        }
        if device not in self.pending_authorizations and (
                len(self.pending_authorizations) >= PAIRING_LIMIT):
            raise Rejected("Too many simultaneous pairing requests")
        self.pending_authorizations[device] = min(
            now + AUTHORIZATION_TTL, self.deadline
        )

    def refresh(self):
        value = dbus.Boolean(self.allowed())
        self.adapter.Set("org.bluez.Adapter1", "Pairable", value)
        self.adapter.Set("org.bluez.Adapter1", "Discoverable", value)
        return True

    def changed(self, interface, change, invalidated, path=None):
        if interface != "org.bluez.Device1" or not isinstance(change, dict):
            return
        if path is None:
            return
        # An explicit unpair or invalidated Paired property may arrive without
        # Agent1.Cancel. Revoke only this device's in-flight trust token.
        if ((invalidated and "Paired" in invalidated)
                or ("Paired" in change and not change["Paired"])):
            self.pending_authorizations.pop(path, None)
            return
        if not change.get("Paired"):
            return
        try:
            now = time.monotonic()
            count = self.paired_count()
            if authorized_pairing_signal(
                    path, self.pending_authorizations,
                    self.initial_pairing_allowed, self.deadline, count, now):
                device = dbus.Interface(
                    self.bus.get_object("org.bluez", path),
                    "org.freedesktop.DBus.Properties"
                )
                # Verify the real, current BlueZ property. A forged or
                # delayed PropertiesChanged signal alone proves nothing.
                if device.Get("org.bluez.Device1", "Paired"):
                    device.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
        finally:
            # An authorization is one-use; a later signal cannot replay it.
            self.pending_authorizations.pop(path, None)
            self.refresh()

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        self.pending_authorizations.clear()
        self.initial_pairing_allowed = False
        self.refresh()

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        self.authorize_pending(device)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        if not isinstance(device, str) or BLUEZ_DEVICE_PATH.fullmatch(device) is None:
            raise Rejected("Invalid Bluetooth device path")
        p = dbus.Interface(
            self.bus.get_object("org.bluez", device),
            "org.freedesktop.DBus.Properties"
        )
        if p.Get("org.bluez.Device1", "Trusted"):
            # BlueZ trust may survive an unpair; trust alone must not grant
            # a profile service to a currently unpaired device.
            if not p.Get("org.bluez.Device1", "Paired"):
                raise Rejected("Unpaired trusted device")
            return
        # Open discovery is not sufficient authorization for services.
        now = time.monotonic()
        if not self.allowed() or not (
                device in self.pending_authorizations
                and now < self.pending_authorizations[device]):
            raise Rejected("Untrusted device")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        self.authorize_pending(device)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        raise Rejected("PIN entry unsupported")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        raise Rejected("Passkey entry unsupported")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        # BlueZ canceled the current agent request; no device path is given.
        # Revoke all pending trust tokens so a delayed Paired event is inert.
        self.pending_authorizations.clear()


def main():
    DBusGMainLoop(set_as_default=True)
    PairingAgent(dbus.SystemBus())
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
