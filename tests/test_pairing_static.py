"""Build-time security checks for experimental Bluetooth pairing policy."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PairingPolicyTests(unittest.TestCase):
    def test_service_closes_pairing_on_reboot_with_known_devices(self):
        text = (ROOT / "src/audiohub/pairing.py").read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn("self.initial_pairing_allowed = self.paired_count() == 0", text)
        self.assertIn("self.initial_pairing_allowed and time.monotonic() < self.deadline", text)

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

if __name__ == "__main__":
    unittest.main()
