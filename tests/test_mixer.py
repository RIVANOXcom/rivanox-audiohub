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


    def test_enormous_native_integer_mixer_controls_fail_with_value_error(self):
        huge = 10 ** 400
        for value in (huge, -huge):
            with self.subTest(control="master", negative=value < 0):
                with self.assertRaises(ValueError):
                    patch_settings(defaults(), {"master": value})
            with self.subTest(control="music_volume", negative=value < 0):
                with self.assertRaises(ValueError):
                    patch_settings(defaults(), {"music": {"volume": value}})
            with self.subTest(control="tablet_eq", negative=value < 0):
                with self.assertRaises(ValueError):
                    patch_settings(defaults(), {"tablet": {"treble": value}})

    def test_large_integer_current_settings_fail_closed_without_overflow(self):
        old = defaults()
        old["master"] = 10**400
        with self.assertRaises(ValueError):
            patch_settings(old, {})
        old = defaults()
        old["laptop"]["mid"] = -(10**400)
        with self.assertRaises(ValueError):
            patch_settings(old, {})

    def test_float_numeric_controls_require_finite_integral_in_range(self):
        for number in (float("nan"), float("inf"), float("-inf"),
                       1e300, -1e300, 2.5):
            with self.subTest(number=repr(number)), self.assertRaises(ValueError):
                patch_settings(defaults(), {"master": number})
        with self.assertRaises(ValueError):
            patch_settings(defaults(), {"music": {"bass": 12.5}})
        self.assertEqual(patch_settings(defaults(), {"master": 100.0})["master"], 100)

    def test_valid_integer_bounds_still_generate_expected_safe_controls(self):
        state = patch_settings(defaults(), {
            "master": 100,
            "music": {"volume": 0, "bass": -12, "mid": 12, "treble": 0},
            "laptop": {"volume": 100, "mute": True},
        })
        self.assertEqual(state["music"]["bass"], -12)
        self.assertEqual(state["music"]["mid"], 12)
        self.assertEqual(state["laptop"]["volume"], 100)
        cmds = volume_commands(state, {"music": 17, "laptop": 18}, 25)
        self.assertIn(["wpctl", "set-volume", "17", "0.0"], cmds)
        self.assertIn(["wpctl", "set-mute", "18", "1"], cmds)

    def test_boolean_required_for_mute(self):
        with self.assertRaises(ValueError):
            patch_settings(defaults(), {"music": {"mute": 1}})


    def test_volume_targets_refuse_bool_float_string_negative_or_oversize_id(self):
        for invalid in (True, False, 1.75, "17", -1, 2**31, None):
            with self.subTest(kind="channel", value=repr(invalid)):
                with self.assertRaises(ValueError):
                    volume_commands(defaults(), {"music": invalid}, 25)
        for invalid in (True, False, 25.1, "25", -1, 2**31):
            with self.subTest(kind="output", value=repr(invalid)):
                with self.assertRaises(ValueError):
                    volume_commands(defaults(), {"music": 17}, invalid)

    def test_volume_targets_refuse_duplicates_or_unknown_channel(self):
        for targets, output in (
            ({"music": 10, "laptop": 10}, 25),
            ({"music": 25}, 25),
            ({"unexpected": 17}, 25),
            ({"music": 17}, 17),
        ):
            with self.subTest(targets=repr(targets), output=output):
                with self.assertRaises(ValueError):
                    volume_commands(defaults(), targets, output)
        with self.assertRaises(ValueError):
            volume_commands(defaults(), [17], 25)

    def test_volume_targets_accept_exact_pi_pipewire_id_boundaries(self):
        cmds = volume_commands(defaults(), {"music": 0, "laptop": 2**31 - 1}, 25)
        self.assertIn(["wpctl", "set-volume", "0", "0.65"], cmds)
        self.assertIn(["wpctl", "set-volume", str(2**31 - 1), "0.5"], cmds)
        self.assertEqual(cmds[0][:3], ["wpctl", "set-volume", "25"])

    def test_volume_targets_without_physical_output_are_still_local_only(self):
        cmds = volume_commands(defaults(), {"music": 17}, None)
        self.assertEqual(cmds[0], ["wpctl", "set-volume", "17", "0.65"])
        self.assertFalse(any(x[2] == "None" for x in cmds))

    def test_volume_commands_are_argv(self):
        commands = volume_commands(defaults(), {"music": 17, "laptop": 18}, 25)
        self.assertIn(["wpctl", "set-volume", "17", "0.65"], commands)
        self.assertIn(["wpctl", "set-volume", "25", str(effective_master_gain(defaults()))], commands)
        self.assertFalse(any(isinstance(command, str) for command in commands))


    def test_master_attenuation_is_applied_before_source_unmute(self):
        state = defaults()
        state["master"] = 100
        for channel in CHANNELS:
            state[channel]["volume"] = 100
        commands = volume_commands(state, {"music": 17, "tablet": 19}, 25)
        self.assertEqual(commands[0][:3], ["wpctl", "set-volume", "25"])
        self.assertEqual(commands[0][3], str(effective_master_gain(state)))
        self.assertTrue(all(args[:3] != ["wpctl", "set-mute", "17"]
                            for args in commands[:1]))
        self.assertLess(commands.index(commands[0]),
                        commands.index(["wpctl", "set-volume", "17", "1.0"]))

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
