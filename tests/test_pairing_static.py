"""Build-time security checks for experimental Bluetooth pairing policy."""
import ast
import re
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PairingPolicyTests(unittest.TestCase):
    def test_service_closes_pairing_on_reboot_with_known_devices(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn("self.initial_pairing_allowed = self.paired_count() == 0", text)
        self.assertIn("self.initial_pairing_allowed and time.monotonic() < self.deadline", text)

    def test_boot_window_does_not_reset_on_agent_service_restart(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        self.assertIn("self.deadline = float(BOOT_WINDOW)", text)
        self.assertNotIn("self.deadline = time.monotonic() + BOOT_WINDOW", text)

    def test_adapter_discovery_and_pairability_have_nonzero_failsafe(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        for name in ("DiscoverableTimeout", "PairableTimeout"):
            self.assertIn(name + '", dbus.UInt32(BOOT_WINDOW)', text)
            self.assertNotIn(name + '", dbus.UInt32(0)', text)

    def test_existing_discovery_is_closed_before_opening_boot_window(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        self.assertIn('self.adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(False))', text)
        self.assertIn('self.adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(False))', text)

    def test_device_count_and_timeout_bounded(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        self.assertIn("BOOT_WINDOW = 600", text)
        self.assertIn("PAIRING_LIMIT = 2", text)
        self.assertIn("NoInputNoOutput", text)


def policy_only():
    """Compile the production pure helper without Raspberry Pi DBus."""
    source = ROOT / "src/audiohub/pairing.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in
            ("PAIRING_LIMIT", "AUTHORIZATION_TTL", "BLUEZ_DEVICE_PATH")
            for t in node.targets
        ):
            selected.append(node)
        if isinstance(node, ast.FunctionDef) and node.name == "authorized_pairing_signal":
            selected.append(node)
    namespace = {"re": re}
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=selected, type_ignores=[]
    )), str(source), "exec"), namespace)
    return namespace


class PairingAuthorizationBoundaryTests(unittest.TestCase):
    DEVICE = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
    OTHER = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"

    def check(self, pending, initial=True, deadline=700,
              paired=1, now=100, device=None):
        return policy_only()["authorized_pairing_signal"](
            self.DEVICE if device is None else device,
            pending, initial, deadline, paired, now
        )

    def test_pending_authorization_is_required(self):
        self.assertFalse(self.check({}))

    def test_recent_approved_device_is_eligible(self):
        self.assertTrue(self.check({self.DEVICE: 140}))

    def test_wrong_device_does_not_inherit_authorization(self):
        self.assertFalse(self.check({self.OTHER: 140}))

    def test_expired_pending_authorization_fails(self):
        self.assertFalse(self.check({self.DEVICE: 100}, now=100))
        self.assertFalse(self.check({self.DEVICE: 145}, now=146))

    def test_post_boot_window_cannot_grant_trust(self):
        self.assertFalse(self.check({self.DEVICE: 140}, deadline=100))

    def test_existing_owned_device_cannot_reopen_pairing(self):
        self.assertFalse(self.check({self.DEVICE: 140}, initial=False))

    def test_zero_or_more_than_two_paired_devices_are_rejected(self):
        for count in (0, 3, -1, True):
            with self.subTest(count=count):
                self.assertFalse(self.check({self.DEVICE: 140}, paired=count))

    def test_second_authorized_device_can_finish_at_limit(self):
        self.assertTrue(self.check({self.DEVICE: 140}, paired=2))

    def test_non_bluez_device_object_path_is_rejected(self):
        self.assertFalse(self.check({self.DEVICE: 140}, device="/org/bluez/unknown"))
        self.assertFalse(self.check({self.DEVICE: 140}, device=self.DEVICE + "/extra"))

    def test_no_unsolicited_trust_write_remains(self):
        source = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        self.assertIn("authorized_pairing_signal(", source)
        self.assertIn("self.pending_authorizations.pop(path, None)", source)
        self.assertIn("self.authorize_pending(device)", source)
        self.assertIn("if p.Get(", source)
        self.assertIn('raise Rejected("Untrusted device")', source)


def agent_methods_without_pi_imports():
    """Exercise real PairingAgent methods with DBus decorators removed."""
    source = ROOT / "src/audiohub/pairing.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in
            ("PAIRING_LIMIT", "AUTHORIZATION_TTL", "BLUEZ_DEVICE_PATH")
            for t in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "authorized_pairing_signal":
            selected.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "PairingAgent":
            node.bases = []
            for method in node.body:
                if isinstance(method, ast.FunctionDef):
                    method.decorator_list = []
            selected.append(node)

    class DBus:
        @staticmethod
        def Boolean(value):
            return bool(value)

        @staticmethod
        def Interface(obj, interface):
            return obj

    namespace = {
        "re": re, "time": time, "dbus": DBus,
        "Rejected": type("Rejected", (Exception,), {}),
    }
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=selected, type_ignores=[]
    )), str(source), "exec"), namespace)
    return namespace


class AgentCallbackAuthorizationTests(unittest.TestCase):
    DEVICE = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"
    SECOND = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_02"

    def setUp(self):
        self.ns = agent_methods_without_pi_imports()
        self.agent = object.__new__(self.ns["PairingAgent"])
        self.paired = 0
        self.fail_bluez = False

        class Manager:
            def GetManagedObjects(inner):
                if self.fail_bluez:
                    raise OSError("service unavailable")
                return {
                    "record-" + str(i): {"org.bluez.Device1": {"Paired": True}}
                    for i in range(self.paired)
                }

        class Props:
            def __init__(inner):
                inner.values = {}
                inner.trusted = False
                inner.paired = True

            def Set(inner, interface, key, value):
                inner.values[key] = value
                if key == "Trusted":
                    inner.trusted = value

            def Get(inner, interface, key):
                if key == "Paired":
                    return inner.paired
                if key == "Trusted":
                    return inner.trusted
                raise AssertionError("unexpected property")

        class Bus:
            def get_object(inner, service, path):
                return self.properties[path]

        self.properties = {
            self.DEVICE: Props(),
            self.SECOND: Props(),
        }
        self.adapter = Props()
        self.agent.manager = Manager()
        self.agent.adapter = self.adapter
        self.agent.bus = Bus()
        self.agent.pending_authorizations = {}
        self.agent.initial_pairing_allowed = True
        self.agent.deadline = 700.0
        p = mock.patch.object(time, "monotonic", return_value=100.0)
        p.start()
        self.addCleanup(p.stop)

    def test_unrelated_pairing_signal_not_trusted(self):
        self.paired = 1
        self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.DEVICE)
        self.assertFalse(self.properties[self.DEVICE].trusted)

    def test_agent_authorization_then_signal_grants_once(self):
        self.agent.RequestAuthorization(self.DEVICE)
        self.paired = 1
        self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.DEVICE)
        self.assertTrue(self.properties[self.DEVICE].trusted)
        self.assertEqual(self.agent.pending_authorizations, {})
        self.properties[self.DEVICE].trusted = False
        self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.DEVICE)
        self.assertFalse(self.properties[self.DEVICE].trusted)

    def test_approved_device_does_not_authorize_other_device(self):
        self.agent.RequestAuthorization(self.DEVICE)
        self.paired = 1
        self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.SECOND)
        self.assertFalse(self.properties[self.SECOND].trusted)

    def test_expired_callback_refuses_trust(self):
        self.agent.RequestAuthorization(self.DEVICE)
        self.paired = 1
        with mock.patch.object(time, "monotonic", return_value=160.0):
            self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.DEVICE)
        self.assertFalse(self.properties[self.DEVICE].trusted)

    def test_service_requires_prior_authorization_when_untrusted(self):
        with self.assertRaises(self.ns["Rejected"]):
            self.agent.AuthorizeService(self.DEVICE, "audio")
        self.agent.RequestAuthorization(self.DEVICE)
        self.agent.AuthorizeService(self.DEVICE, "audio")

    def test_forged_signal_when_bluez_device_is_not_paired_does_not_grant_trust(self):
        self.agent.RequestAuthorization(self.DEVICE)
        self.paired = 1
        self.properties[self.DEVICE].paired = False
        self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.DEVICE)
        self.assertFalse(self.properties[self.DEVICE].trusted)
        self.assertEqual(self.agent.pending_authorizations, {})

    def test_signal_origin_filter_is_registered(self):
        source = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        self.assertIn('bus_name="org.bluez"', source)
        self.assertIn('device.Get("org.bluez.Device1", "Paired")', source)

    def test_trusted_reconnection_works_after_window(self):
        self.properties[self.DEVICE].trusted = True
        self.agent.initial_pairing_allowed = False
        self.agent.AuthorizeService(self.DEVICE, "audio")

    def test_bluez_down_never_reopens_pairability(self):
        self.fail_bluez = True
        self.assertFalse(self.agent.allowed())
        with self.assertRaises(self.ns["Rejected"]):
            self.agent.RequestAuthorization(self.DEVICE)

    def test_release_clears_pending_and_discovery(self):
        self.agent.RequestAuthorization(self.DEVICE)
        self.agent.Release()
        self.assertFalse(self.agent.initial_pairing_allowed)
        self.assertEqual(self.agent.pending_authorizations, {})
        self.assertFalse(self.adapter.values["Discoverable"])

    def test_second_device_can_finish_pairing_at_limit(self):
        self.agent.RequestAuthorization(self.SECOND)
        self.paired = 2
        self.agent.changed("org.bluez.Device1", {"Paired": True}, [], self.SECOND)
        self.assertTrue(self.properties[self.SECOND].trusted)
        self.assertFalse(self.adapter.values["Pairable"])

    def test_close_window_rejects_pending_service(self):
        self.agent.RequestAuthorization(self.DEVICE)
        self.agent.deadline = 99.0
        with self.assertRaises(self.ns["Rejected"]):
            self.agent.AuthorizeService(self.DEVICE, "audio")

if __name__ == "__main__":
    unittest.main()
