"""Private AudioHub channel label tests."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audiohub import input_profiles

class InputProfilesSmoke(unittest.TestCase):
    def test_generic_defaults(self):
        self.assertEqual(tuple(input_profiles.DEFAULT_NAMES.values()), ('Input 1', 'Input 2', 'Input 3'))
