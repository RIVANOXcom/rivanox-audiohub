"""Verify that temporary pairing cannot silently turn strangers into trusted peers."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audiohub.pairing_policy import may_pair, may_trust_pair, valid_pending, MAX_PEERS


class PairingPolicyTests(unittest.TestCase):
    def test_fresh_unpaired_owner_window(self):
        self.assertTrue(may_pair(True, 100, 700, 0))
        self.assertTrue(may_pair(True, 100, 700, 1))
        self.assertFalse(may_pair(True, 100, 700, MAX_PEERS))

    def test_reboot_with_existing_pair_closes_new_pairing(self):
        self.assertFalse(may_pair(False, 100, 700, 1))
        self.assertFalse(may_trust_pair(False, 100, 700, 1, True))

    def test_expired_window_never_trusts_new_device(self):
        self.assertFalse(may_pair(True, 700, 700, 0))
        self.assertFalse(may_trust_pair(True, 701, 700, 1, True))

    def test_pairing_signal_does_not_mean_authorization(self):
        self.assertFalse(may_trust_pair(True, 100, 700, 1, False))
        self.assertTrue(may_trust_pair(True, 100, 700, 1, True))
        self.assertFalse(may_trust_pair(True, 100, 700, 3, True))

    def test_invalid_types_fail_closed(self):
        self.assertFalse(may_pair(True, 100, 700, True))
        self.assertFalse(may_trust_pair(True, 100, 700, 1, 1))
        self.assertFalse(valid_pending(100, None))

    def test_real_agent_requires_candidate_before_trust(self):
        agent = (ROOT / "src/audiohub/pairing.py").read_text()
        ast.parse(agent)
        self.assertIn("candidate = str(path) in self.pending", agent)
        self.assertIn('not bool(change.get("Paired", False))', agent)
        self.assertNotIn('change.get("Paired") is not True', agent)
        self.assertIn("may_trust_pair(", agent)
        self.assertIn('self.pending.pop(str(path), None)', agent)
        self.assertIn("self._authorize_candidate(device)", agent)


if __name__ == "__main__":
    unittest.main()
