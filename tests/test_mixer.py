"""Unit tests: per-source mixer safety and configuration independence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.mixer import (CHANNELS, defaults, patch_settings, pipewire_filter_config,
                            volume_commands, mix_gain_budget, effective_master_gain)


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
        self.assertIn(["wpctl", "set-volume", "25", str(effective_master_gain(defaults()))], commands)
        self.assertFalse(any(isinstance(command, str) for command in commands))


    def test_three_full_scale_inputs_have_one_third_gain_budget(self):
        settings = defaults()
        settings["master"] = 100
        for channel in CHANNELS:
            settings[channel]["volume"] = 100
        self.assertAlmostEqual(mix_gain_budget(settings), 1 / 3)
        self.assertAlmostEqual(effective_master_gain(settings), 1 / 3)
        commands = volume_commands(settings, {channel: index + 1 for index, channel in enumerate(CHANNELS)}, 9)
        self.assertIn(["wpctl", "set-volume", "9", str(1 / 3)], commands)

    def test_single_channel_does_not_unnecessarily_attenuate(self):
        settings = defaults()
        settings["master"] = 100
        settings["music"]["volume"] = 100
        for channel in ("laptop", "tablet"):
            settings[channel]["mute"] = True
        self.assertEqual(mix_gain_budget(settings), 1.0)
        self.assertEqual(effective_master_gain(settings), 1.0)

    def test_master_zero_and_all_sources_muted(self):
        settings = defaults()
        settings["master"] = 0
        self.assertEqual(effective_master_gain(settings), 0.0)
        for channel in CHANNELS:
            settings[channel]["mute"] = True
        settings["master"] = 80
        self.assertEqual(mix_gain_budget(settings), 1.0)
        self.assertEqual(effective_master_gain(settings), 0.8)

    def test_positive_eq_boost_reduces_budget(self):
        settings = defaults()
        settings["master"] = 100
        for channel in CHANNELS:
            settings[channel]["mute"] = channel != "music"
        settings["music"]["volume"] = 100
        self.assertEqual(mix_gain_budget(settings), 1.0)
        settings["music"].update({"bass": 12, "mid": 12, "treble": 12})
        expected = 10 ** (-36 / 20)
        self.assertAlmostEqual(mix_gain_budget(settings), expected)
        self.assertAlmostEqual(effective_master_gain(settings), expected)
        settings["music"]["bass"] = -12
        self.assertAlmostEqual(mix_gain_budget(settings), 10 ** (-24 / 20))

    def test_budget_covers_worst_case_three_source_sum(self):
        settings = defaults()
        settings["master"] = 100
        for channel in CHANNELS:
            settings[channel].update({"volume": 100, "mute": False, "bass": 12, "mid": 12, "treble": 12})
        aggregate = 3 * 10 ** (36 / 20)
        self.assertLessEqual(aggregate * mix_gain_budget(settings), 1 + 1e-12)
        self.assertGreater(mix_gain_budget(settings), 0)
        self.assertLess(mix_gain_budget(settings), 1 / 3)


if __name__ == "__main__":
    unittest.main()
