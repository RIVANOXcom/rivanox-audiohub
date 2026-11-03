"""Unit tests: per-source mixer safety and configuration independence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.mixer import CHANNELS, defaults, patch_settings, pipewire_filter_config, volume_commands


class MixerTests(unittest.TestCase):
    def test_three_independent_paths(self):
        rendered = pipewire_filter_config({})
        self.assertEqual(rendered.count("libpipewire-module-filter-chain"), 3)
        for channel in CHANNELS:
            self.assertIn('node.name = "audiohub.%s"' % channel, rendered)

    def test_equalizer_isolation(self):
        data = patch_settings(defaults(), {"music": {"bass": 9}, "tablet": {"bass": -7}})
        self.assertEqual(data["laptop"]["bass"], 0)
        self.assertIn("gain = 9", pipewire_filter_config(data))
        self.assertIn("gain = -7", pipewire_filter_config(data))

    def test_unknown_fields_rejected(self):
        for payload in ({"shell": "true"}, {"music": {"unknown": 1}}, {"tablet": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                patch_settings(defaults(), payload)

    def test_bad_numbers_rejected(self):
        for value in ("10", True, -1, 101, float("nan"), float("inf"), 2.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                patch_settings(defaults(), {"master": value})

    def test_boolean_required_for_mute(self):
        with self.assertRaises(ValueError):
            patch_settings(defaults(), {"music": {"mute": 1}})

    def test_volume_commands_are_argv(self):
        commands = volume_commands(defaults(), {"music": 17, "laptop": 18}, 25)
        self.assertIn(["wpctl", "set-volume", "17", "0.65"], commands)
        self.assertIn(["wpctl", "set-volume", "25", "0.7"], commands)
        self.assertFalse(any(isinstance(command, str) for command in commands))


if __name__ == "__main__":
    unittest.main()
