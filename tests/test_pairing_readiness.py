"""Read-only local Bluetooth onboarding experience without a Pi, network or DBus."""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import pairing_readiness as pairing


class PairingReadinessTests(unittest.TestCase):
    ADAPTER = "/org/bluez/hci0"

    def devices(self, *, paired=0, trusted=None, connected=0,
                powered=True, pairable=True, discoverable=True):
        if trusted is None:
            trusted = paired
        objects = {self.ADAPTER: {
            "org.bluez.Adapter1": {
                "Powered": powered, "Pairable": pairable,
                "Discoverable": discoverable,
            }
        }}
        for n in range(paired):
            objects[self.ADAPTER + "/dev_AA_BB_CC_DD_EE_" + str(n)] = {
                "org.bluez.Device1": {
                    "Adapter": self.ADAPTER,
                    "Paired": True, "Trusted": n < trusted,
                    "Connected": n < connected,
                    "Address": "AA:BB:CC:DD:EE:FF",
                    "Alias": "private phone",
                }
            }
        return objects

    def test_first_boot_window_is_guided_but_not_owner_claimed(self):
        snapshot = pairing.inspect_managed_objects(self.devices(), 95)
        self.assertEqual(snapshot["state"], "initial_window_observed")
        self.assertEqual(snapshot["first_boot_seconds_left"], 505)
        self.assertFalse(snapshot["owner_authenticated"])
        self.assertFalse(snapshot["pairing_performed"])
        self.assertFalse(snapshot["hardware_audio_verified"])
        msg = pairing.render_guide(snapshot)
        self.assertIn("Approximate boot-window", msg)
        self.assertIn("not proof of ownership", msg)
        self.assertNotIn("AA:BB", msg)
        self.assertNotIn("private phone", msg)

    def test_known_device_reconnection_advice_does_not_reopen_pairing(self):
        snapshot = pairing.inspect_managed_objects(
            self.devices(paired=1, connected=1, pairable=False,
                         discoverable=False), 1500)
        self.assertEqual(snapshot["state"], "known_devices")
        self.assertEqual(snapshot["trusted_paired_devices"], 1)
        self.assertEqual(snapshot["connected_paired_devices"], 1)
        self.assertIn("reconnect", pairing.render_guide(snapshot))
        self.assertEqual(snapshot["first_boot_seconds_left"], 0)

    def test_two_device_limit_and_guest_open_warning(self):
        snap = pairing.inspect_managed_objects(self.devices(
            paired=2, pairable=False, discoverable=False), 1700)
        self.assertEqual(snap["state"], "device_limit")
        snap = pairing.inspect_managed_objects(self.devices(
            paired=1, pairable=True, discoverable=False), 1700)
        self.assertEqual(snap["state"], "unexpected_open")
        self.assertIn("Do not add", pairing.render_guide(snap))

    def test_window_expired_never_suggests_reboot_to_bypass_claim(self):
        snap = pairing.inspect_managed_objects(
            self.devices(pairable=False, discoverable=False), 601)
        self.assertEqual(snap["state"], "window_closed")
        self.assertEqual(snap["first_boot_seconds_left"], 0)
        self.assertIn("Do not bypass", pairing.render_guide(snap))

    def test_inconsistent_unknown_and_untrusted_states_are_not_ready(self):
        self.assertEqual(pairing.inspect_managed_objects(
            self.devices(paired=3, pairable=False, discoverable=False), 500)["state"],
                         "inconsistent")
        self.assertEqual(pairing.inspect_managed_objects(
            self.devices(paired=1, trusted=0, pairable=False, discoverable=False), 500)["state"],
                         "paired_untrusted")
        self.assertEqual(pairing.inspect_managed_objects(
            self.devices(powered=False), 50)["state"], "controller_off")
        self.assertEqual(pairing.inspect_managed_objects({}, 50)["state"], "ambiguous_adapter")
        self.assertEqual(pairing.inspect_managed_objects(
            self.devices(), float("nan"))["state"], "unavailable")

    def test_strict_shapes_refuse_fabricated_positive_readiness(self):
        for objects in (
            {"x": {}}, None, [], {self.ADAPTER: {
                "org.bluez.Adapter1": {"Powered": 1, "Discoverable": True,
                                       "Pairable": True}}},
            {self.ADAPTER: {"org.bluez.Adapter1": {
                "Powered": "yes", "Pairable": True, "Discoverable": True}}},
        ):
            result = pairing.inspect_managed_objects(objects, 100)
            self.assertNotEqual(result["state"], "initial_window_observed")
        objects = self.devices()
        objects[self.ADAPTER]["org.bluez.Adapter1"]["Powered"] = True
        objects["/org/bluez/hci1"] = objects[self.ADAPTER]
        self.assertEqual(pairing.inspect_managed_objects(
            objects, 50)["state"], "ambiguous_adapter")
        self.assertEqual(pairing.inspect_managed_objects(
            self.devices(), -1)["state"], "unavailable")

    def test_all_report_fields_are_anonymous_and_bounded(self):
        obj = self.devices(paired=1, pairable=False, discoverable=False)
        obj[self.ADAPTER + "/dev_00"]["org.bluez.Device1"]["Name"] = "private-user"
        snap = pairing.inspect_managed_objects(obj, 700)
        rendered = json.dumps(snap) + pairing.render_guide(snap)
        for bad in ("AA:BB", "private-user", "private phone", "hci0", "/org/bluez"):
            self.assertNotIn(bad, rendered)
        self.assertFalse(snap["production_ready"])
        self.assertLessEqual(snap["paired_devices"], 2)

    def test_pure_module_has_no_eager_pi_dbus_import(self):
        source = Path(pairing.__file__).read_text(encoding="utf8")
        self.assertNotIn("\nimport dbus\n", source)
        self.assertNotIn("bluetoothctl pair", source)
        self.assertNotIn("Set(", source)
        self.assertNotIn("Pair(", source)

    def test_json_console_has_only_whitelisted_fields(self):
        snapshot = pairing.inspect_managed_objects(
            self.devices(pairable=False, discoverable=False), 700)
        output = []
        with mock.patch.object(pairing, "read_local_bluez", return_value=snapshot), \
             mock.patch("builtins.print", side_effect=output.append):
            self.assertEqual(pairing.main(["--json"]), 0)
        parsed = json.loads(output[0])
        self.assertEqual(parsed["state"], "window_closed")
        self.assertEqual(set(parsed), set(pairing._empty("window_closed")))
        self.assertNotIn("Adapter", output[0])

    def test_local_dbus_probe_failure_is_safe_and_has_no_identity_leak(self):
        snap = pairing.read_local_bluez(bus=mock.Mock(
            get_object=mock.Mock(side_effect=RuntimeError("mac AA:BB:CC"))))
        self.assertEqual(snap["state"], "unavailable")
        self.assertNotIn("AA:BB", pairing.render_guide(snap))


if __name__ == "__main__":
    unittest.main()
