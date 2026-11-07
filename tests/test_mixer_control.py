"""Offline AudioHub mixer controls: private atomic file only, never actual audio."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub import mixer_control
from audiohub.mixer import defaults, requested_mix_controls
from audiohub import runtime


class LocalMixerControlsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.settings = self.root / "audiohub" / "settings.json"

    def test_read_only_show_is_default_and_creates_nothing(self):
        current = mixer_control.show(path=self.settings)
        self.assertEqual(current, defaults())
        self.assertFalse(self.settings.parent.exists())

    def test_explicit_change_writes_private_atomic_file_and_keeps_other_channels(self):
        self.assertEqual(mixer_control.change({"master": 35}, path=self.settings,
                                              confirmed=True)["master"], 35)
        self.assertEqual(mixer_control.change(
            {"music": {"volume": 12}}, path=self.settings, confirmed=True
        )["music"]["volume"], 12)
        latest = mixer_control.change({"tablet": {"mute": True}},
                                      path=self.settings, confirmed=True)
        self.assertEqual(latest["master"], 35)
        self.assertEqual(latest["music"]["volume"], 12)
        self.assertTrue(latest["tablet"]["mute"])
        self.assertFalse(latest["laptop"]["mute"])
        self.assertEqual(mixer_control.show(path=self.settings), latest)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.settings.parent.stat().st_mode), 0o700)
        self.assertEqual(self.settings.stat().st_nlink, 1)
        self.assertEqual(stat.S_IMODE(
            (self.settings.parent / mixer_control.LOCK_NAME).stat().st_mode
        ), 0o600)
        self.assertEqual(set(self.settings.parent.iterdir()),
                         {self.settings, self.settings.parent / mixer_control.LOCK_NAME})

    def test_no_confirmation_or_root_cannot_create_files(self):
        with self.assertRaisesRegex(mixer_control.MixerControlUnavailable, "confirmation"):
            mixer_control.change({"master": 80}, path=self.settings)
        with mock.patch("audiohub.mixer_control.os.geteuid", return_value=0):
            with self.assertRaisesRegex(mixer_control.MixerControlUnavailable,
                                        "unprivileged"):
                mixer_control.change({"master": 80}, path=self.settings, confirmed=True)
            with self.assertRaisesRegex(mixer_control.MixerControlUnavailable,
                                        "unprivileged"):
                mixer_control.show(path=self.settings)
        self.assertFalse(self.settings.parent.exists())

    def test_invalid_value_cannot_replace_valid_setting(self):
        mixer_control.change({"master": 57}, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        for patch in ({"master": -1}, {"master": 101}, {"master": True},
                      {"music": {"volume": 200}}, {"tablet": {"mute": "yes"}},
                      {"wifi_password": "PRIVATE-SECRET"},
                      {"music": {"bass": float("nan")}}):
            with self.subTest(patch=repr(patch)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change(patch, path=self.settings, confirmed=True)
                self.assertEqual(self.settings.read_bytes(), before)
        self.assertNotIn(b"PRIVATE-SECRET", before)

    def test_corrupt_or_unreviewed_state_never_replaced_by_defaults(self):
        self.settings.parent.mkdir(mode=0o700)
        for payload in (
            b"{", b'{"master": 25, "master": 80}',
            b'{"master": 31, "unexpected": "SECRET"}',
            b'{"master": 80, "music": {"mute": "heard"}}',
        ):
            with self.subTest(payload=payload[:40]):
                self.settings.write_bytes(payload)
                self.settings.chmod(0o600)
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
                self.assertEqual(self.settings.read_bytes(), payload)

    def test_untrusted_symlinks_and_permissions_do_not_destroy_target(self):
        other = self.root / "protected.json"
        other.write_text("PRIVATE-OWNER")
        self.settings.parent.mkdir(mode=0o700)
        self.settings.symlink_to(other)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"master": 25}, path=self.settings, confirmed=True)
        self.assertEqual(other.read_text(), "PRIVATE-OWNER")
        self.settings.unlink()
        self.settings.write_text(json.dumps(defaults()))
        self.settings.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"master": 25}, path=self.settings, confirmed=True)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o644)

    def test_raced_lock_symlink_is_rejected_before_writing(self):
        self.settings.parent.mkdir(mode=0o700)
        other = self.root / "outside"
        other.write_text("PRIVATE-PROTECTED")
        (self.settings.parent / mixer_control.LOCK_NAME).symlink_to(other)
        with self.assertRaises(OSError):
            mixer_control.change({"master": 60}, path=self.settings, confirmed=True)
        self.assertEqual(other.read_text(), "PRIVATE-PROTECTED")
        self.assertFalse(self.settings.exists())

    def test_two_concurrent_local_writers_keep_both_user_changes(self):
        def update(request):
            return mixer_control.change(request, path=self.settings, confirmed=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [
                pool.submit(update, {"music": {"volume": 33}}),
                pool.submit(update, {"tablet": {"mute": True}}),
            ]
            for future in tasks:
                future.result(timeout=8)
        result = mixer_control.show(path=self.settings)
        self.assertEqual(result["music"]["volume"], 33)
        self.assertTrue(result["tablet"]["mute"])
        self.assertEqual(result["master"], defaults()["master"])

    def test_cli_defaults_are_read_only_and_mutation_needs_flag(self):
        with mock.patch("audiohub.mixer_control.show", return_value=defaults()) as show:
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["show"])
            self.assertIn('"master": 70', output.getvalue())
            show.assert_called_once_with()
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["set-master", "40"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with({"master": 40}, confirmed=False)
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-volume", "laptop", "45"
                ])
            change.assert_called_once_with({"laptop": {"volume": 45}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "mute", "tablet", "on"
                ])
            change.assert_called_once_with({"tablet": {"mute": True}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change") as change:
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-volume", "unknown", "50"
                ])
            change.assert_not_called()

    def test_atomic_mix_changes_all_four_levels_preserving_mutes_and_eq(self):
        mixer_control.change({"tablet": {"mute": True, "bass": 4},
                              "music": {"treble": -3}},
                             path=self.settings, confirmed=True)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            state = mixer_control.change(
                {"master": 20, "music": {"volume": 15},
                 "laptop": {"volume": 35}, "tablet": {"volume": 0}},
                path=self.settings, confirmed=True)
            atomic.assert_called_once()
        self.assertEqual(state["master"], 20)
        self.assertEqual([state[c]["volume"] for c in ("music", "laptop", "tablet")],
                         [15, 35, 0])
        self.assertTrue(state["tablet"]["mute"])
        self.assertEqual(state["tablet"]["bass"], 4)
        self.assertEqual(state["music"]["treble"], -3)
        self.assertEqual(mixer_control.show(path=self.settings), state)

    def test_invalid_mix_rejects_whole_update_without_changing_existing_state(self):
        mixer_control.change({"master": 45}, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change(
                {"master": 10, "music": {"volume": 20},
                 "laptop": {"volume": 101}, "tablet": {"volume": 30}},
                path=self.settings, confirmed=True)
        self.assertEqual(self.settings.read_bytes(), before)

    def test_set_mix_cli_is_gated_and_sends_one_validated_patch(self):
        expected = {"master": 20, "music": {"volume": 15},
                    "laptop": {"volume": 35}, "tablet": {"volume": 0}}
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-mix", "20", "15", "35", "0"
                ])
            change.assert_called_once_with(expected, confirmed=True)
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["set-mix", "20", "15", "35", "0"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with(expected, confirmed=False)
        with mock.patch("audiohub.mixer_control.change") as change:
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "set-mix", "20", "15", "35"
                ])
            change.assert_not_called()

    def test_mute_all_is_single_atomic_write_and_preserves_levels_and_eq(self):
        prior = mixer_control.change({
            "master": 27, "music": {"volume": 33, "bass": 4},
            "laptop": {"volume": 14, "mute": True},
            "tablet": {"volume": 95, "treble": -2},
        }, path=self.settings, confirmed=True)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            muted = mixer_control.change({
                slot: {"mute": True} for slot in ("music", "laptop", "tablet")
            }, path=self.settings, confirmed=True)
            atomic.assert_called_once()
        self.assertEqual(muted["master"], prior["master"])
        for slot in ("music", "laptop", "tablet"):
            self.assertTrue(muted[slot]["mute"])
            for control in ("volume", "bass", "mid", "treble"):
                self.assertEqual(muted[slot][control], prior[slot][control])
        self.assertEqual(mixer_control.show(path=self.settings), muted)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_mute_all_cli_requires_confirmation_and_no_extra_arguments(self):
        expected = {slot: {"mute": True} for slot in ("music", "laptop", "tablet")}
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main(["--confirm-local-mixer-change", "mute-all"])
            change.assert_called_once_with(expected, confirmed=True)
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["mute-all"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with(expected, confirmed=False)
        with mock.patch("audiohub.mixer_control.change") as change:
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                mixer_control.main(["--confirm-local-mixer-change", "mute-all", "off"])
            change.assert_not_called()

    def test_mute_all_keeps_existing_corrupt_state_unchanged(self):
        self.settings.parent.mkdir(mode=0o700)
        self.settings.write_bytes(b'{"music": {"mute": false}, "music": {"mute": true}}')
        self.settings.chmod(0o600)
        before = self.settings.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({
                slot: {"mute": True} for slot in ("music", "laptop", "tablet")
            }, path=self.settings, confirmed=True)
        self.assertEqual(self.settings.read_bytes(), before)

    def test_selective_unmute_restores_only_named_inputs_in_one_atomic_write(self):
        before = mixer_control.change({
            "master": 22,
            "music": {"volume": 33, "bass": 4, "mute": True},
            "laptop": {"volume": 41, "mid": -2, "mute": True},
            "tablet": {"volume": 80, "treble": 3, "mute": True},
        }, path=self.settings, confirmed=True)
        # Run real atomic change against the test-owned path; preserve the
        # original function before mocking CLI dispatch to avoid recursion.
        original_change = mixer_control.change
        def local_change(patch, *, confirmed=False):
            return original_change(patch, path=self.settings, confirmed=confirmed)
        with mock.patch("audiohub.mixer_control.change", side_effect=local_change) as changed:
            with mock.patch("audiohub.mixer_control.atomic_json",
                            wraps=mixer_control.atomic_json) as atomic:
                with redirect_stdout(StringIO()) as output:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "unmute-selected", "music", "laptop"
                    ])
                changed.assert_called_once_with({
                    "music": {"mute": False}, "laptop": {"mute": False}
                }, confirmed=True)
                atomic.assert_called_once()
            self.assertIn('"mute": false', output.getvalue())
        after = mixer_control.show(path=self.settings)
        self.assertFalse(after["music"]["mute"])
        self.assertFalse(after["laptop"]["mute"])
        self.assertTrue(after["tablet"]["mute"])
        self.assertEqual(after["master"], before["master"])
        for slot in ("music", "laptop", "tablet"):
            for control in ("volume", "bass", "mid", "treble"):
                self.assertEqual(after[slot][control], before[slot][control])

    def test_selective_unmute_requires_confirmation_and_rejects_duplicates_or_all(self):
        with mock.patch("audiohub.mixer_control.change", return_value=defaults()) as change:
            with redirect_stdout(StringIO()):
                mixer_control.main([
                    "--confirm-local-mixer-change", "unmute-selected", "tablet"
                ])
            change.assert_called_once_with({"tablet": {"mute": False}}, confirmed=True)
        with mock.patch("audiohub.mixer_control.change",
                        side_effect=mixer_control.MixerControlUnavailable("confirmation")) as change:
            with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                mixer_control.main(["unmute-selected", "music"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with({"music": {"mute": False}}, confirmed=False)
        for bad in (
            ["unmute-selected"],
            ["unmute-selected", "music", "music"],
            ["unmute-selected", "music", "laptop", "tablet"],
            ["unmute-selected", "music", "unknown"],
        ):
            with self.subTest(bad=bad):
                with mock.patch("audiohub.mixer_control.change") as change:
                    with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                        mixer_control.main(["--confirm-local-mixer-change", *bad])
                    self.assertEqual(failed.exception.code, 2)
                    change.assert_not_called()

    def test_selective_unmute_does_not_replace_unsafe_existing_settings(self):
        self.settings.parent.mkdir(mode=0o700)
        self.settings.write_bytes(b'{"master": 25, "master": 70}')
        self.settings.chmod(0o600)
        prior = self.settings.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.change({"laptop": {"mute": False}},
                                 path=self.settings, confirmed=True)
        self.assertEqual(self.settings.read_bytes(), prior)

    def test_preview_mute_all_preserves_eq_and_never_writes(self):
        initial = mixer_control.change({
            "master": 22,
            "music": {"volume": 33, "bass": 4, "mute": False},
            "laptop": {"volume": 41, "mid": -2, "mute": True},
            "tablet": {"volume": 80, "treble": 3, "mute": False},
        }, path=self.settings, confirmed=True)
        data = self.settings.read_bytes()
        original_preview = mixer_control.preview_change
        def local_preview(patch):
            return original_preview(patch, path=self.settings)
        with mock.patch("audiohub.mixer_control.preview_change",
                        side_effect=local_preview) as preview:
            with mock.patch("audiohub.mixer_control.change") as changed:
                with redirect_stdout(StringIO()) as stdout:
                    mixer_control.main(["--preview", "mute-all"])
                preview.assert_called_once_with({
                    slot: {"mute": True} for slot in ("music", "laptop", "tablet")
                })
                changed.assert_not_called()
        lines = stdout.getvalue().splitlines()
        result = json.loads(lines[0])
        self.assertEqual(result["mode"], "preview-only")
        self.assertEqual(result["would_change"], ["music.mute", "tablet.mute"])
        self.assertTrue(all(result["after"][slot]["mute"]
                            for slot in ("music", "laptop", "tablet")))
        self.assertFalse(result["settings_written"])
        self.assertFalse(result["supervisor_applied"])
        self.assertFalse(result["audible_playback_verified"])
        self.assertIn("no settings saved", lines[1])
        self.assertEqual(self.settings.read_bytes(), data)
        self.assertEqual(mixer_control.show(path=self.settings), initial)

    def test_preview_set_mix_and_selective_unmute_show_exact_changes(self):
        runtime = mixer_control.change({
            "master": 60,
            "music": {"volume": 25, "mute": True},
            "laptop": {"volume": 31, "mute": True},
            "tablet": {"volume": 90, "mute": True},
        }, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        mix = mixer_control.preview_change({
            "master": 20, "music": {"volume": 15},
            "laptop": {"volume": 31}, "tablet": {"volume": 0},
        }, path=self.settings)
        self.assertEqual(mix["would_change"], [
            "master", "music.volume", "tablet.volume",
        ])
        self.assertEqual(mix["before"]["master"], runtime["master"])
        self.assertEqual(mix["after"]["master"], 20)
        unmute = mixer_control.preview_change({
            "music": {"mute": False}, "laptop": {"mute": False},
        }, path=self.settings)
        self.assertEqual(unmute["would_change"], ["music.mute", "laptop.mute"])
        self.assertTrue(unmute["after"]["tablet"]["mute"])
        self.assertEqual(self.settings.read_bytes(), before)

    def test_preview_missing_defaults_creates_no_directory_or_lock(self):
        result = mixer_control.preview_change({"master": 19}, path=self.settings)
        self.assertEqual(result["mode"], "preview-only")
        self.assertEqual(result["would_change"], ["master"])
        self.assertEqual(result["before"]["master"], defaults()["master"])
        self.assertFalse(self.settings.parent.exists())

    def test_preview_refuses_bad_patch_and_unsafe_existing_state(self):
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.preview_change({"master": 101}, path=self.settings)
        self.settings.parent.mkdir(mode=0o700)
        original = b'{"master": 20, "master": 40}'
        self.settings.write_bytes(original)
        self.settings.chmod(0o600)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.preview_change({"master": 25}, path=self.settings)
        self.assertEqual(self.settings.read_bytes(), original)
        target = self.root / "other.json"
        target.write_text(json.dumps(defaults()))
        self.settings.unlink()
        self.settings.symlink_to(target)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.preview_change({"master": 25}, path=self.settings)
        self.assertEqual(target.read_text(), json.dumps(defaults()))

    def test_preview_cli_flags_and_invalid_selection_fail_before_any_write(self):
        for args in (
            ["--preview", "--confirm-local-mixer-change", "mute-all"],
            ["--preview", "show"],
            ["--preview", "status"],
            ["--preview", "unmute-selected", "music", "music"],
            ["--preview", "unmute-selected", "music", "laptop", "tablet"],
        ):
            with self.subTest(args=args):
                with mock.patch("audiohub.mixer_control.change") as change:
                    with mock.patch("audiohub.mixer_control.preview_change") as preview:
                        with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                            mixer_control.main(args)
                        self.assertEqual(failed.exception.code, 2)
                        change.assert_not_called()
                        preview.assert_not_called()

    def test_preview_revision_lets_operator_commit_only_same_generation(self):
        original = mixer_control.change(
            {"master": 50, "music": {"volume": 42, "bass": 3}},
            path=self.settings, confirmed=True)
        preview = mixer_control.preview_change(
            {"master": 15}, path=self.settings)
        self.assertRegex(preview["revision"], r"^v1-[0-9a-f]{64}$")
        self.assertEqual(preview["would_change"], ["master"])
        result = mixer_control.change(
            {"master": 15}, path=self.settings,
            confirmed=True, if_revision=preview["revision"])
        self.assertEqual(result["master"], 15)
        self.assertEqual(result["music"]["bass"], original["music"]["bass"])
        self.assertNotEqual(
            mixer_control.preview_change({"master": 25},
                                         path=self.settings)["revision"],
            preview["revision"])

    def test_preview_revision_rejects_concurrent_value_or_eq_change(self):
        mixer_control.change({"master": 50}, path=self.settings, confirmed=True)
        preview = mixer_control.preview_change({"master": 20}, path=self.settings)
        mixer_control.change(
            {"music": {"bass": 4}}, path=self.settings, confirmed=True)
        prior = self.settings.read_bytes()
        with self.assertRaisesRegex(
                mixer_control.MixerControlUnavailable, "no longer current"):
            mixer_control.change({"master": 20}, path=self.settings,
                                 confirmed=True, if_revision=preview["revision"])
        self.assertEqual(self.settings.read_bytes(), prior)
        self.assertEqual(mixer_control.show(path=self.settings)["master"], 50)

    def test_preview_revision_rejects_aba_restore_of_identical_values(self):
        mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
        preview = mixer_control.preview_change({"master": 25}, path=self.settings)
        mixer_control.change({"master": 40}, path=self.settings, confirmed=True)
        mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
        self.assertEqual(mixer_control.show(path=self.settings)["master"], 30)
        before = self.settings.read_bytes()
        with self.assertRaisesRegex(
                mixer_control.MixerControlUnavailable, "no longer current"):
            mixer_control.change({"master": 25}, path=self.settings,
                                 confirmed=True, if_revision=preview["revision"])
        self.assertEqual(self.settings.read_bytes(), before)

    def test_default_revision_is_read_only_and_guards_first_save(self):
        preview = mixer_control.preview_change({"master": 35}, path=self.settings)
        self.assertEqual(preview["before"]["master"], defaults()["master"])
        self.assertFalse(self.settings.parent.exists())
        after = mixer_control.change({"master": 35}, path=self.settings,
                                     confirmed=True, if_revision=preview["revision"])
        self.assertEqual(after["master"], 35)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.settings.parent.stat().st_mode), 0o700)

    def test_same_revision_two_simultaneous_writers_only_one_succeeds(self):
        mixer_control.change({"master": 50}, path=self.settings, confirmed=True)
        token = mixer_control.preview_change(
            {"master": 25}, path=self.settings)["revision"]
        def apply(level):
            try:
                mixer_control.change({"master": level}, path=self.settings,
                                     confirmed=True, if_revision=token)
                return True
            except mixer_control.MixerControlUnavailable:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(apply, level) for level in (20, 30)]
            results = [future.result(timeout=8) for future in futures]
        self.assertCountEqual(results, [True, False])
        self.assertIn(mixer_control.show(path=self.settings)["master"], (20, 30))

    def test_bad_revision_refuses_without_creating_any_settings(self):
        for token in ("", "v1-", "v1-" + "A" * 64, "v1-" + "a" * 63,
                      "v1-" + "x" * 64, 123, True):
            with self.subTest(token=repr(token)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.change({"master": 22}, path=self.settings,
                                         confirmed=True, if_revision=token)
                self.assertFalse(self.settings.parent.exists())

    def test_revision_cli_requires_explicit_consent_and_rejects_preview_combo(self):
        token = "v1-" + "a" * 64
        for argv in (
            ["--if-preview-revision", token, "set-master", "25"],
            ["--preview", "--if-preview-revision", token, "set-master", "25"],
            ["--if-preview-revision", token, "show"],
            ["--if-preview-revision", token, "status"],
            ["--confirm-local-mixer-change", "--if-preview-revision", token, "show"],
        ):
            with self.subTest(argv=argv):
                with (mock.patch("audiohub.mixer_control.change") as changed,
                      mock.patch("audiohub.mixer_control.preview_change") as preview):
                    with self.assertRaises(SystemExit) as failed, redirect_stderr(StringIO()):
                        mixer_control.main(argv)
                    self.assertEqual(failed.exception.code, 2)
                    changed.assert_not_called()
                    preview.assert_not_called()

    def test_revision_cli_passes_guard_to_same_existing_atomic_change(self):
        token = "v1-" + "b" * 64
        with mock.patch("audiohub.mixer_control.change",
                        return_value=defaults()) as changed:
            with redirect_stdout(StringIO()):
                mixer_control.main(["--confirm-local-mixer-change",
                                    "--if-preview-revision", token,
                                    "set-master", "35"])
            changed.assert_called_once_with(
                {"master": 35}, confirmed=True, if_revision=token)

    def test_stale_cli_shows_fresh_read_only_plan_and_exit_code_four(self):
        mixer_control.change({"master": 48}, path=self.settings, confirmed=True)
        stale = mixer_control.preview_change({"master": 25}, path=self.settings)
        mixer_control.change({"music": {"bass": 5}},
                             path=self.settings, confirmed=True)
        current_bytes = self.settings.read_bytes()
        original_change = mixer_control.change
        original_preview = mixer_control.preview_change
        def local_change(patch, *, confirmed=False, if_revision=None):
            return original_change(patch, path=self.settings, confirmed=confirmed,
                                   if_revision=if_revision)
        def local_preview(patch):
            return original_preview(patch, path=self.settings)
        with (mock.patch("audiohub.mixer_control.change",
                         side_effect=local_change) as change,
              mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=local_preview) as preview,
              mock.patch("audiohub.mixer_control.atomic_json",
                         wraps=mixer_control.atomic_json) as writer):
            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as caught:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "--if-preview-revision",
                        stale["revision"], "set-master", "25"
                    ])
            self.assertEqual(caught.exception.code, 4)
            change.assert_called_once_with(
                {"master": 25}, confirmed=True, if_revision=stale["revision"])
            preview.assert_called_once_with({"master": 25})
            writer.assert_not_called()
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["status"], "preview-stale")
        self.assertFalse(data["settings_written"])
        self.assertFalse(data["audible_playback_verified"])
        new_plan = data["fresh_preview"]
        self.assertEqual(new_plan["before"]["master"], 48)
        self.assertEqual(new_plan["after"]["master"], 25)
        self.assertEqual(new_plan["would_change"], ["master"])
        self.assertEqual(new_plan["mode"], "preview-only")
        self.assertFalse(new_plan["settings_written"])
        self.assertNotEqual(new_plan["revision"], stale["revision"])
        self.assertIn("explicitly confirm", stderr.getvalue())
        self.assertEqual(self.settings.read_bytes(), current_bytes)

    def test_stale_cli_refresh_failure_never_leaks_private_state(self):
        with (mock.patch("audiohub.mixer_control.change",
                         side_effect=mixer_control.StaleMixerPreview("private-path")) as changed,
              mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=mixer_control.MixerControlUnavailable("private-secret")) as preview):
            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as caught:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "--if-preview-revision",
                        "v1-" + "a" * 64, "set-master", "20"
                    ])
            self.assertEqual(caught.exception.code, 4)
            changed.assert_called_once()
            preview.assert_called_once_with({"master": 20})
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Fresh preview unavailable", stderr.getvalue())
        self.assertNotIn("private-secret", stderr.getvalue())
        self.assertNotIn("private-path", stderr.getvalue())

    def test_invalid_revision_is_not_misreported_as_stale_preview(self):
        with (mock.patch("audiohub.mixer_control.change",
                         side_effect=mixer_control.MixerControlUnavailable("invalid revision")) as changed,
              mock.patch("audiohub.mixer_control.preview_change") as preview):
            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as caught:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "--if-preview-revision",
                        "v1-" + "x" * 64, "mute-all"
                    ])
            self.assertEqual(caught.exception.code, 2)
            changed.assert_called_once()
            preview.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("not changed or unavailable", stderr.getvalue())

    def test_refresh_is_not_attempted_on_successful_guarded_change(self):
        with (mock.patch("audiohub.mixer_control.change",
                         return_value=defaults()) as changed,
              mock.patch("audiohub.mixer_control.preview_change") as preview):
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main([
                    "--confirm-local-mixer-change", "--if-preview-revision",
                    "v1-" + "a" * 64, "set-volume", "music", "22"
                ])
            changed.assert_called_once_with(
                {"music": {"volume": 22}},
                confirmed=True, if_revision="v1-" + "a" * 64)
            preview.assert_not_called()
        self.assertNotIn("preview-stale", stdout.getvalue())

    def test_comparison_snapshot_pinpoints_individual_eq_and_input_changes(self):
        mixer_control.change({
            "master": 32,
            "music": {"volume": 25, "bass": 3, "mid": -2},
            "laptop": {"mute": True},
            "tablet": {"treble": 4}
        }, path=self.settings, confirmed=True)
        old = mixer_control.preview_change({"master": 20}, path=self.settings)
        token = old["comparison_baseline"]
        self.assertTrue(token.startswith("b1-"))
        self.assertIsNone(old["changed_since_baseline"])
        self.assertEqual(old["planned_changes"], [
            {"control": "master", "previous": 32, "current": 20}
        ])
        mixer_control.change({
            "music": {"volume": 30, "bass": 5},
            "tablet": {"treble": 2, "mute": True}
        }, path=self.settings, confirmed=True)
        bytes_before = self.settings.read_bytes()
        refreshed = mixer_control.preview_change(
            {"master": 20}, path=self.settings, baseline=token)
        self.assertEqual(refreshed["changed_since_baseline"], [
            {"control": "music.volume", "previous": 25, "current": 30},
            {"control": "music.bass", "previous": 3, "current": 5},
            {"control": "tablet.mute", "previous": False, "current": True},
            {"control": "tablet.treble", "previous": 4, "current": 2},
        ])
        self.assertEqual(refreshed["planned_changes"], [
            {"control": "master", "previous": 32, "current": 20}
        ])
        self.assertNotEqual(refreshed["comparison_baseline"], token)
        self.assertTrue(refreshed["before"]["tablet"]["mute"])
        self.assertFalse(refreshed["settings_written"])
        self.assertFalse(refreshed["supervisor_applied"])
        self.assertFalse(refreshed["audible_playback_verified"])
        self.assertEqual(self.settings.read_bytes(), bytes_before)

    def test_comparison_baseline_equal_values_reports_empty_not_unavailable(self):
        old = mixer_control.preview_change({"music": {"volume": 21}},
                                           path=self.settings)
        again = mixer_control.preview_change(
            {"music": {"volume": 21}}, path=self.settings,
            baseline=old["comparison_baseline"])
        self.assertEqual(again["changed_since_baseline"], [])
        self.assertEqual(again["planned_changes"], [
            {"control": "music.volume", "previous": 65, "current": 21}
        ])
        self.assertFalse(self.settings.parent.exists())
        # A generation change without a value difference must not invent one.
        mixer_control.change({"master": 70}, path=self.settings, confirmed=True)
        generation = mixer_control.preview_change({"music": {"volume": 21}},
                       path=self.settings, baseline=old["comparison_baseline"])
        self.assertEqual(generation["changed_since_baseline"], [])

    def test_stale_guarded_cli_comparison_renders_intervening_eq_changes_without_write(self):
        mixer_control.change({"master": 49}, path=self.settings, confirmed=True)
        original_preview = mixer_control.preview_change(
            {"master": 20}, path=self.settings)
        mixer_control.change({"laptop": {"mid": -4, "volume": 17}},
                             path=self.settings, confirmed=True)
        original_bytes = self.settings.read_bytes()
        real_change = mixer_control.change
        real_preview = mixer_control.preview_change
        def change_local(patch, *, confirmed=False, if_revision=None):
            return real_change(patch, path=self.settings, confirmed=confirmed,
                               if_revision=if_revision)
        def preview_local(patch, *, baseline=None):
            return real_preview(patch, path=self.settings, baseline=baseline)
        with (mock.patch("audiohub.mixer_control.change",
                         side_effect=change_local) as change,
              mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=preview_local) as preview,
              mock.patch("audiohub.mixer_control.atomic_json",
                         wraps=mixer_control.atomic_json) as atomic):
            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as exc:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "--if-preview-revision",
                        original_preview["revision"], "--compare-baseline",
                        original_preview["comparison_baseline"], "set-master", "20"
                    ])
            self.assertEqual(exc.exception.code, 4)
            change.assert_called_once_with({"master": 20}, confirmed=True,
                                           if_revision=original_preview["revision"])
            preview.assert_called_once_with(
                {"master": 20}, baseline=original_preview["comparison_baseline"])
            atomic.assert_not_called()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "preview-stale")
        fresh = payload["fresh_preview"]
        self.assertEqual(fresh["changed_since_baseline"], [
            {"control": "laptop.volume", "previous": 50, "current": 17},
            {"control": "laptop.mid", "previous": 0, "current": -4},
        ])
        self.assertEqual(fresh["planned_changes"], [
            {"control": "master", "previous": 49, "current": 20}
        ])
        self.assertFalse(payload["settings_written"])
        self.assertIn("explicitly confirm", stderr.getvalue())
        self.assertEqual(self.settings.read_bytes(), original_bytes)

    def test_compare_baseline_cli_preview_without_writing_anything(self):
        earlier = mixer_control.preview_change({"master": 20}, path=self.settings)
        with mock.patch("audiohub.mixer_control.preview_change",
                        return_value=earlier) as preview:
            with mock.patch("audiohub.mixer_control.change") as change:
                with redirect_stdout(StringIO()):
                    mixer_control.main([
                        "--preview", "--compare-baseline",
                        earlier["comparison_baseline"], "mute-all"])
                preview.assert_called_once_with({
                    slot: {"mute": True} for slot in ("music", "laptop", "tablet")
                }, baseline=earlier["comparison_baseline"])
                change.assert_not_called()

    def test_invalid_comparison_tokens_fail_closed_before_any_write(self):
        valid = mixer_control.preview_change({"master": 20},
                       path=self.settings)["comparison_baseline"]
        for bad in (None, "", "b1-", "b1-%", "b1-" + "A" * 300,
                    valid + "=", valid[:-1] + "!", "b2-" + valid[3:],
                    "b1-" + "e30"):
            with self.subTest(token=repr(bad)[:40]):
                if bad is None:
                    continue  # None means comparison was not requested.
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control._decode_baseline(bad)
                with mock.patch("audiohub.mixer_control.change") as change:
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            mixer_control.main([
                                "--confirm-local-mixer-change", "--if-preview-revision",
                                "v1-" + "a" * 64, "--compare-baseline",
                                bad, "set-master", "20"
                            ])
                        self.assertEqual(failed.exception.code, 2)
                    change.assert_not_called()
        self.assertFalse(self.settings.parent.exists())

    def test_compare_baseline_requires_preview_or_conditional_confirmed_change(self):
        baseline = mixer_control.preview_change({"master": 20},
                          path=self.settings)["comparison_baseline"]
        for args in (
            ["--compare-baseline", baseline, "show"],
            ["--compare-baseline", baseline, "status"],
            ["--compare-baseline", baseline, "set-master", "20"],
            ["--confirm-local-mixer-change", "--compare-baseline",
             baseline, "set-master", "20"],
        ):
            with self.subTest(args=args):
                with (mock.patch("audiohub.mixer_control.change") as change,
                      mock.patch("audiohub.mixer_control.preview_change") as preview):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            mixer_control.main(args)
                    self.assertEqual(failed.exception.code, 2)
                    change.assert_not_called()
                    preview.assert_not_called()
        self.assertFalse(self.settings.parent.exists())

    def test_named_presets_are_fixed_bounded_and_volume_only(self):
        self.assertEqual(set(mixer_control.PRESET_VOLUMES),
                         {"quiet", "balanced", "music-priority"})
        for name, values in mixer_control.PRESET_VOLUMES.items():
            with self.subTest(name=name):
                self.assertEqual(len(values), 4)
                self.assertTrue(all(type(value) is int and 0 <= value <= 100
                                    for value in values))
                patch = mixer_control.preset_patch(name)
                self.assertEqual(patch["master"], values[0])
                for index, slot in enumerate(("music", "laptop", "tablet"), 1):
                    self.assertEqual(patch[slot], {"volume": values[index]})
                self.assertNotIn("mute", repr(patch))
                self.assertNotIn("bass", repr(patch))
                self.assertNotIn("treble", repr(patch))
        for bad in ("unmute-all", "loud", "", None, True):
            with self.subTest(name=repr(bad)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.preset_patch(bad)

    def test_preset_preview_creates_nothing_and_supports_existing_revision(self):
        for name in mixer_control.PRESET_VOLUMES:
            with self.subTest(name=name):
                result = mixer_control.preview_change(
                    mixer_control.preset_patch(name), path=self.settings)
                self.assertEqual(result["mode"], "preview-only")
                self.assertRegex(result["revision"], r"^v1-[0-9a-f]{64}$")
                self.assertFalse(result["settings_written"])
                self.assertFalse(result["audible_playback_verified"])
                self.assertFalse(self.settings.parent.exists())
        with mock.patch("audiohub.mixer_control.preview_change",
                        return_value={"mode": "preview-only"}) as preview:
            with mock.patch("audiohub.mixer_control.change") as change:
                with redirect_stdout(StringIO()):
                    mixer_control.main(["--preview", "preset", "music-priority"])
                preview.assert_called_once_with(
                    mixer_control.preset_patch("music-priority"))
                change.assert_not_called()

    def test_preset_preserves_every_mute_eq_and_uses_one_atomic_change(self):
        initial = mixer_control.change({
            "master": 72,
            "music": {"volume": 72, "bass": 9, "mid": -2, "mute": True},
            "laptop": {"volume": 80, "bass": -3, "treble": 5, "mute": True},
            "tablet": {"volume": 65, "mid": 4, "treble": -6, "mute": False},
        }, path=self.settings, confirmed=True)
        original_change = mixer_control.change
        def change_local(patch, *, confirmed=False):
            return original_change(patch, path=self.settings, confirmed=confirmed)
        with (mock.patch("audiohub.mixer_control.change",
                         side_effect=change_local) as changed,
              mock.patch("audiohub.mixer_control.atomic_json",
                         wraps=mixer_control.atomic_json) as atomic):
            with redirect_stdout(StringIO()):
                mixer_control.main(["--confirm-local-mixer-change",
                                    "preset", "quiet"])
            changed.assert_called_once_with(
                mixer_control.preset_patch("quiet"), confirmed=True)
            atomic.assert_called_once()
        now = mixer_control.show(path=self.settings)
        self.assertEqual(now["master"], 15)
        self.assertEqual(tuple(now[x]["volume"] for x in
                         ("music", "laptop", "tablet")), (25, 25, 25))
        for slot in ("music", "laptop", "tablet"):
            for field in ("mute", "bass", "mid", "treble"):
                self.assertEqual(now[slot][field], initial[slot][field])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_preset_stale_guard_refuses_and_read_only_repreviews(self):
        initial = mixer_control.preview_change(
            mixer_control.preset_patch("balanced"), path=self.settings)
        mixer_control.change({"tablet": {"mute": True}},
                             path=self.settings, confirmed=True)
        original_bytes = self.settings.read_bytes()
        original_change = mixer_control.change
        original_preview = mixer_control.preview_change
        def local_change(patch, *, confirmed=False, if_revision=None):
            return original_change(patch, path=self.settings,
                                   confirmed=confirmed, if_revision=if_revision)
        def local_preview(patch):
            return original_preview(patch, path=self.settings)
        with (mock.patch("audiohub.mixer_control.change",
                         side_effect=local_change) as changed,
              mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=local_preview) as preview,
              mock.patch("audiohub.mixer_control.atomic_json",
                         wraps=mixer_control.atomic_json) as atomic):
            with redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "--if-preview-revision",
                        initial["revision"], "preset", "balanced"])
            self.assertEqual(failed.exception.code, 4)
            changed.assert_called_once_with(
                mixer_control.preset_patch("balanced"), confirmed=True,
                if_revision=initial["revision"])
            preview.assert_called_once_with(
                mixer_control.preset_patch("balanced"))
            atomic.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "preview-stale")
        self.assertFalse(report["settings_written"])
        self.assertTrue(report["fresh_preview"]["before"]["tablet"]["mute"])
        self.assertTrue(report["fresh_preview"]["after"]["tablet"]["mute"])
        self.assertEqual(self.settings.read_bytes(), original_bytes)

    def test_preset_cli_rejects_invalid_name_and_implicit_write(self):
        with mock.patch(
                "audiohub.mixer_control.change",
                side_effect=mixer_control.MixerControlUnavailable("confirmation")
        ) as change:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main(["preset", "quiet"])
            self.assertEqual(failed.exception.code, 2)
            change.assert_called_once_with(
                mixer_control.preset_patch("quiet"), confirmed=False)
        for argv in (
            ["--preview", "--confirm-local-mixer-change", "preset", "quiet"],
            ["--confirm-local-mixer-change", "preset", "loud"],
            ["--confirm-local-mixer-change", "preset"],
        ):
            with self.subTest(argv=argv):
                with (mock.patch("audiohub.mixer_control.change") as change,
                      mock.patch("audiohub.mixer_control.preview_change") as preview):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            mixer_control.main(argv)
                    self.assertEqual(failed.exception.code, 2)
                    change.assert_not_called()
                    preview.assert_not_called()

    def test_preset_cli_supports_wait_after_confirmed_save_without_auto_unmute(self):
        saved = defaults()
        saved["music"]["mute"] = True
        report = {"delivery_state": "accepted", "saved_request": {},
                  "settings_written": True, "pending_controls": [],
                  "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.change",
                         return_value=saved) as change,
              mock.patch("audiohub.mixer_control.wait_for_supervisor",
                         return_value=report) as wait):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["--confirm-local-mixer-change",
                                    "--wait-for-supervisor", "preset", "balanced"])
            change.assert_called_once_with(
                mixer_control.preset_patch("balanced"), confirmed=True)
            wait.assert_called_once_with(saved)
            self.assertIn('"audible_playback_verified": false', out.getvalue())

    def test_custom_profiles_read_only_list_does_not_create_any_file(self):
        self.assertEqual(mixer_control.list_volume_profiles(
            path=self.settings.with_name("volume-profiles.json")),
            {"version": 1, "profiles": {}})
        self.assertFalse(self.settings.parent.exists())

    def test_custom_profile_save_is_private_without_applying_audio(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        self.assertEqual(mixer_control.save_volume_profile(
            "night-mix", 20, 35, 25, 0, path=profile_path, confirmed=True),
            {"profile_saved": "night-mix",
             "volumes": {"master": 20, "music": 35,
                         "laptop": 25, "tablet": 0},
             "mixer_settings_written": False, "audible_playback_verified": False})
        self.assertFalse(self.settings.exists())
        self.assertEqual(stat.S_IMODE(profile_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(profile_path.parent.stat().st_mode), 0o700)
        self.assertEqual(mixer_control.list_volume_profiles(path=profile_path),
            {"version": 1, "profiles": {
                "night-mix": {"master": 20, "music": 35,
                              "laptop": 25, "tablet": 0}}})
        self.assertEqual(mixer_control.saved_profile_patch(
            "night-mix", path=profile_path),
            {"master": 20, "music": {"volume": 35},
             "laptop": {"volume": 25}, "tablet": {"volume": 0}})

    def test_custom_profile_preview_then_atomic_apply_preserves_all_mutes_and_eq(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile("film", 30, 35, 55, 12,
                                          path=profile_path, confirmed=True)
        old = mixer_control.change({
            "master": 75, "music": {"mute": True, "bass": 5, "volume": 90},
            "laptop": {"mute": True, "mid": -5, "treble": 8},
            "tablet": {"mute": False, "treble": 6}}, path=self.settings,
            confirmed=True)
        patch = mixer_control.saved_profile_patch("film", path=profile_path)
        preview = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual(preview["after"]["master"], 30)
        self.assertFalse(preview["settings_written"])
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as write:
            updated = mixer_control.change(
                patch, path=self.settings, confirmed=True,
                if_revision=preview["revision"])
            write.assert_called_once()
        self.assertEqual([updated[x]["volume"] for x in
                          ("music", "laptop", "tablet")], [35, 55, 12])
        for channel in ("music", "laptop", "tablet"):
            for field in ("mute", "bass", "mid", "treble"):
                self.assertEqual(old[channel][field], updated[channel][field])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_custom_profile_missing_duplicate_and_full_catalog_never_overwrite(self):
        path = self.settings.with_name("volume-profiles.json")
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.saved_profile_patch("missing", path=path)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.save_volume_profile("test", 20, 20, 20, 20, path=path)
        self.assertFalse(path.parent.exists())
        mixer_control.save_volume_profile("test", 20, 20, 20, 20,
                                          path=path, confirmed=True)
        before = path.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.save_volume_profile("test", 40, 40, 40, 40,
                                              path=path, confirmed=True)
        self.assertEqual(path.read_bytes(), before)
        for index in range(1, 8):
            mixer_control.save_volume_profile(
                "other-" + str(index), 20, 20, 20, 20,
                path=path, confirmed=True)
        full = path.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.save_volume_profile("over-cap", 20, 20, 20, 20,
                                              path=path, confirmed=True)
        self.assertEqual(path.read_bytes(), full)
        self.assertEqual(len(mixer_control.list_volume_profiles(
            path=path)["profiles"]), 8)

    def test_custom_profile_names_and_exact_levels_reject_unsafe_values(self):
        path = self.settings.with_name("volume-profiles.json")
        for name in ("", "../escape", ".hidden", "MixedCase", "a/b", "a_b",
                     "a" * 25, "ü", True, None):
            with self.subTest(name=repr(name)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.save_volume_profile(
                        name, 20, 20, 20, 20, path=path, confirmed=True)
        for levels in ((101, 20, 20, 20), (-1, 20, 20, 20),
                       (True, 20, 20, 20), (20, "35", 20, 20),
                       (20, 20, float("nan"), 20)):
            with self.subTest(levels=repr(levels)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.save_volume_profile(
                        "fine", *levels, path=path, confirmed=True)
        self.assertFalse(path.parent.exists())

    def test_custom_profile_symlink_corruption_and_permissions_fail_closed(self):
        path = self.settings.with_name("volume-profiles.json")
        other = self.root / "private-target.json"
        other.write_text("PRIVATE-OWNER")
        path.parent.mkdir(mode=0o700)
        path.symlink_to(other)
        for operation in (
            lambda: mixer_control.list_volume_profiles(path=path),
            lambda: mixer_control.save_volume_profile(
                "quietish", 20, 20, 20, 20, path=path, confirmed=True),
        ):
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                operation()
        self.assertEqual(other.read_text(), "PRIVATE-OWNER")
        path.unlink()
        for payload in (b'{', b'{"version":1,"profiles":{"x":{"master":2}}}',
                        b'{"version":1,"profiles":{},"secret":"PRIVATE"}',
                        b'{"version":1,"profiles":{},"profiles":{}}'):
            path.write_bytes(payload)
            path.chmod(0o600)
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.list_volume_profiles(path=path)
            before = path.read_bytes()
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.save_volume_profile(
                    "new", 20, 20, 20, 20, path=path, confirmed=True)
            self.assertEqual(path.read_bytes(), before)
        path.write_text('{"version":1,"profiles":{}}')
        path.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.list_volume_profiles(path=path)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_custom_profile_concurrent_creators_serialize_without_loss(self):
        path = self.settings.with_name("volume-profiles.json")
        def create(name):
            return mixer_control.save_volume_profile(
                name, 25, 35, 45, 20, path=path, confirmed=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ("north", "south")))
        self.assertEqual({r["profile_saved"] for r in results},
                         {"north", "south"})
        self.assertEqual(set(mixer_control.list_volume_profiles(
            path=path)["profiles"]), {"north", "south"})

    def test_custom_profile_cli_private_save_and_list_no_active_mixer_change(self):
        path = self.settings.with_name("volume-profiles.json")
        original = mixer_control.save_volume_profile
        def local_save(name, master, music, laptop, tablet, *, confirmed=False):
            return original(name, master, music, laptop, tablet,
                            path=path, confirmed=confirmed)
        original_list = mixer_control.list_volume_profiles
        def local_list():
            return original_list(path=path)
        with (mock.patch("audiohub.mixer_control.save_volume_profile",
                         side_effect=local_save) as save,
              mock.patch("audiohub.mixer_control.list_volume_profiles",
                         side_effect=local_list) as listing,
              mock.patch("audiohub.mixer_control.change") as active):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["--confirm-local-profile-save",
                                    "save-profile", "my-volume", "30", "40",
                                    "15", "10"])
            self.assertIn('"mixer_settings_written": false', out.getvalue())
            save.assert_called_once_with("my-volume", 30, 40, 15, 10,
                                         confirmed=True)
            self.assertFalse(self.settings.exists())
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["list-profiles"])
            self.assertIn('"my-volume"', out.getvalue())
            listing.assert_called_once_with()
            active.assert_not_called()

    def test_custom_profile_cli_enforces_separate_explicit_consents(self):
        bads = (
            ["save-profile", "some", "20", "30", "40", "50"],
            ["--confirm-local-mixer-change", "save-profile", "some", "20",
             "30", "40", "50"],
            ["--preview", "save-profile", "some", "20", "30", "40", "50"],
            ["--confirm-local-profile-save", "list-profiles"],
            ["--confirm-local-profile-save", "preset", "quiet"],
            ["--confirm-local-profile-save", "--confirm-local-mixer-change",
             "profile", "some"],
            ["--wait-for-supervisor", "--confirm-local-profile-save",
             "save-profile", "some", "20", "30", "40", "50"],
            ["--confirm-local-mixer-change", "list-profiles"],
            ["--preview", "list-profiles"],
        )
        for argv in bads:
            with self.subTest(argv=argv):
                with (mock.patch("audiohub.mixer_control.change") as change,
                      mock.patch("audiohub.mixer_control.atomic_json") as write):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            mixer_control.main(argv)
                    self.assertEqual(failed.exception.code, 2)
                    change.assert_not_called()
                    write.assert_not_called()

    def test_custom_profile_cli_preview_then_guarded_apply_uses_existing_paths(self):
        levels = {"master": 40, "music": 25, "laptop": 30, "tablet": 10}
        patch = mixer_control._profile_patch(levels)
        with (mock.patch("audiohub.mixer_control.saved_profile_patch",
                         return_value=patch) as lookup,
              mock.patch("audiohub.mixer_control.preview_change",
                         return_value={"mode": "preview-only"}) as preview,
              mock.patch("audiohub.mixer_control.change",
                         return_value=defaults()) as changed):
            with redirect_stdout(StringIO()):
                mixer_control.main(["--preview", "profile", "home"])
                mixer_control.main(["--confirm-local-mixer-change",
                                    "--if-preview-revision", "v1-" + "a" * 64,
                                    "profile", "home"])
            self.assertEqual(lookup.call_count, 2)
            preview.assert_called_once_with(patch)
            changed.assert_called_once_with(
                patch, confirmed=True, if_revision="v1-" + "a" * 64)

    def test_capture_preview_is_read_only_and_does_not_create_config(self):
        path = self.settings.with_name("volume-profiles.json")
        plan = mixer_control.preview_current_profile(
            "my-levels", path=path, settings_path=self.settings)
        self.assertEqual(plan["mode"], "profile-capture-preview")
        self.assertEqual(plan["name"], "my-levels")
        self.assertEqual(plan["volumes"], {
            "master": 70, "music": 65, "laptop": 50, "tablet": 50})
        self.assertRegex(plan["revision"], r"^v1-[0-9a-f]{64}$")
        self.assertFalse(plan["profile_written"])
        self.assertFalse(plan["mixer_settings_written"])
        self.assertFalse(plan["audible_playback_verified"])
        self.assertFalse(path.parent.exists())

    def test_capture_current_values_saves_only_private_profile_never_active_mixer(self):
        path = self.settings.with_name("volume-profiles.json")
        old = mixer_control.change({
            "master": 23,
            "music": {"volume": 37, "mute": True, "bass": 9, "mid": -2},
            "laptop": {"volume": 18, "mute": True, "treble": 5},
            "tablet": {"volume": 0, "mute": False, "bass": -8},
        }, path=self.settings, confirmed=True)
        mixer_bytes = self.settings.read_bytes()
        preview = mixer_control.preview_current_profile(
            "my-levels", path=path, settings_path=self.settings)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            outcome = mixer_control.capture_current_profile(
                "my-levels", path=path, settings_path=self.settings,
                if_revision=preview["revision"], confirmed=True)
            atomic.assert_called_once()
        self.assertEqual(outcome["profile_saved"], "my-levels")
        self.assertEqual(outcome["volumes"], {
            "master": 23, "music": 37, "laptop": 18, "tablet": 0})
        self.assertFalse(outcome["mixer_settings_written"])
        self.assertFalse(outcome["audible_playback_verified"])
        self.assertEqual(self.settings.read_bytes(), mixer_bytes)
        self.assertEqual(mixer_control.show(path=self.settings), old)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        catalog = mixer_control.list_volume_profiles(path=path)
        self.assertEqual(catalog["profiles"]["my-levels"], outcome["volumes"])
        self.assertEqual(mixer_control.saved_profile_patch(
            "my-levels", path=path), {
            "master": 23, "music": {"volume": 37},
            "laptop": {"volume": 18}, "tablet": {"volume": 0}})

    def test_capture_missing_mixer_settings_uses_guarded_defaults_without_creating_mixer(self):
        path = self.settings.with_name("volume-profiles.json")
        plan = mixer_control.preview_current_profile(
            "first", path=path, settings_path=self.settings)
        result = mixer_control.capture_current_profile(
            "first", path=path, settings_path=self.settings,
            if_revision=plan["revision"], confirmed=True)
        self.assertEqual(result["volumes"], plan["volumes"])
        self.assertFalse(self.settings.exists())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_capture_rejects_intervening_eq_change_and_aba_generation(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.change({"master": 36}, path=self.settings, confirmed=True)
        preview = mixer_control.preview_current_profile(
            "safety", path=path, settings_path=self.settings)
        mixer_control.change({"music": {"bass": 4}},
                             path=self.settings, confirmed=True)
        mixer_bytes = self.settings.read_bytes()
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            with self.assertRaises(mixer_control.StaleMixerPreview):
                mixer_control.capture_current_profile(
                    "safety", path=path, settings_path=self.settings,
                    if_revision=preview["revision"], confirmed=True)
            atomic.assert_not_called()
        self.assertFalse(path.exists())
        self.assertEqual(self.settings.read_bytes(), mixer_bytes)
        new_plan = mixer_control.preview_current_profile(
            "safety", path=path, settings_path=self.settings)
        mixer_control.change({"master": 45}, path=self.settings, confirmed=True)
        mixer_control.change({"master": 36}, path=self.settings, confirmed=True)
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.capture_current_profile(
                "safety", path=path, settings_path=self.settings,
                if_revision=new_plan["revision"], confirmed=True)
        self.assertFalse(path.exists())

    def test_capture_cannot_overwrite_existing_profile_or_bypass_catalog_limit(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "existing", 10, 20, 30, 40, path=path, confirmed=True)
        plan = mixer_control.preview_current_profile
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            plan("existing", path=path, settings_path=self.settings)
        before = path.read_bytes()
        revision = mixer_control._preview_snapshot(path=self.settings)[1]
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.capture_current_profile(
                "existing", path=path, settings_path=self.settings,
                if_revision=revision, confirmed=True)
        self.assertEqual(path.read_bytes(), before)
        for number in range(7):
            mixer_control.save_volume_profile(
                "rest-" + str(number), 20, 20, 20, 20,
                path=path, confirmed=True)
        full = path.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.preview_current_profile(
                "another", path=path, settings_path=self.settings)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.capture_current_profile(
                "another", path=path, settings_path=self.settings,
                if_revision=revision, confirmed=True)
        self.assertEqual(path.read_bytes(), full)

    def test_capture_bad_consent_revision_and_paths_refuse_before_any_write(self):
        path = self.settings.with_name("volume-profiles.json")
        valid = "v1-" + "a" * 64
        for token, approved in ((None, True), ("invalid", True),
                                ("v1-" + "A" * 64, True),
                                (True, True), (valid, False)):
            with self.subTest(token=repr(token), confirmed=approved):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.capture_current_profile(
                        "backup", path=path, settings_path=self.settings,
                        if_revision=token, confirmed=approved)
        for bad in (path.with_name("settings.json"),
                    self.root / "other" / "volume-profiles.json"):
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.capture_current_profile(
                    "backup", path=bad, settings_path=self.settings,
                    if_revision=valid, confirmed=True)
        self.assertFalse(self.settings.parent.exists())

    def test_capture_cli_preview_and_separate_guarded_confirm(self):
        preview = {
            "mode": "profile-capture-preview", "name": "saved", "revision": "v1-" + "a" * 64,
            "volumes": {"master": 25, "music": 25, "laptop": 25, "tablet": 25},
            "profile_written": False, "mixer_settings_written": False,
            "audible_playback_verified": False}
        saved = {"profile_saved": "saved", "volumes": preview["volumes"],
                 "mixer_settings_written": False, "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.preview_current_profile",
                         return_value=preview) as planned,
              mock.patch("audiohub.mixer_control.capture_current_profile",
                         return_value=saved) as capture,
              mock.patch("audiohub.mixer_control.change") as change):
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--preview", "save-current-profile", "saved"])
                self.assertIn('"profile_written": false', output.getvalue())
            planned.assert_called_once_with("saved")
            capture.assert_not_called()
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--confirm-local-profile-save",
                                    "--if-preview-revision", preview["revision"],
                                    "save-current-profile", "saved"])
                self.assertIn('"mixer_settings_written": false', output.getvalue())
            capture.assert_called_once_with(
                "saved", if_revision=preview["revision"], confirmed=True)
            change.assert_not_called()

    def test_capture_cli_stale_is_read_only_and_requires_second_confirmation(self):
        current_plan = {"mode": "profile-capture-preview", "name": "mine",
                        "revision": "v1-" + "b" * 64,
                        "volumes": {"master": 25, "music": 25,
                                    "laptop": 25, "tablet": 25},
                        "profile_written": False, "mixer_settings_written": False,
                        "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.capture_current_profile",
                         side_effect=mixer_control.StaleMixerPreview("PRIVATE")) as saved,
              mock.patch("audiohub.mixer_control.preview_current_profile",
                         return_value=current_plan) as preview,
              mock.patch("audiohub.mixer_control.atomic_json") as write):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
                with self.assertRaises(SystemExit) as rejected:
                    mixer_control.main(["--confirm-local-profile-save",
                                        "--if-preview-revision", "v1-" + "a" * 64,
                                        "save-current-profile", "mine"])
            self.assertEqual(rejected.exception.code, 4)
            saved.assert_called_once_with(
                "mine", if_revision="v1-" + "a" * 64, confirmed=True)
            preview.assert_called_once_with("mine")
            write.assert_not_called()
        data = json.loads(out.getvalue())
        self.assertEqual(data["status"], "profile-capture-stale")
        self.assertFalse(data["profile_written"])
        self.assertEqual(data["fresh_preview"], current_plan)
        self.assertNotIn("PRIVATE", err.getvalue())

    def test_capture_cli_refresh_failure_is_sanitized_and_does_not_apply(self):
        with (mock.patch("audiohub.mixer_control.capture_current_profile",
                         side_effect=mixer_control.StaleMixerPreview("SENSITIVE")),
              mock.patch("audiohub.mixer_control.preview_current_profile",
                         side_effect=mixer_control.MixerControlUnavailable("PRIVATE PATH"))):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
                with self.assertRaises(SystemExit) as rejected:
                    mixer_control.main(["--confirm-local-profile-save",
                                        "--if-preview-revision", "v1-" + "a" * 64,
                                        "save-current-profile", "mine"])
        self.assertEqual(rejected.exception.code, 4)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Fresh preview unavailable", err.getvalue())
        self.assertNotIn("SENSITIVE", err.getvalue())
        self.assertNotIn("PRIVATE PATH", err.getvalue())

    def test_capture_cli_rejects_mixed_or_missing_confirmations(self):
        bad = (
            ["save-current-profile", "mine"],
            ["--confirm-local-profile-save", "save-current-profile", "mine"],
            ["--if-preview-revision", "v1-" + "a" * 64, "save-current-profile", "mine"],
            ["--preview", "--confirm-local-profile-save", "save-current-profile", "mine"],
            ["--preview", "--if-preview-revision", "v1-" + "a" * 64,
             "save-current-profile", "mine"],
            ["--preview", "--confirm-local-mixer-change", "save-current-profile", "mine"],
            ["--confirm-local-profile-save", "--if-preview-revision", "v1-" + "a" * 64,
             "--wait-for-supervisor", "save-current-profile", "mine"],
            ["--confirm-local-profile-save", "--if-preview-revision", "v1-" + "a" * 64,
             "--compare-baseline", "invalid", "save-current-profile", "mine"],
        )
        for argv in bad:
            with self.subTest(args=argv):
                with (mock.patch("audiohub.mixer_control.capture_current_profile") as capture,
                      mock.patch("audiohub.mixer_control.preview_current_profile") as preview,
                      mock.patch("audiohub.mixer_control.change") as changed):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as rejected:
                            mixer_control.main(argv)
                    self.assertEqual(rejected.exception.code, 2)
                    capture.assert_not_called()
                    preview.assert_not_called()
                    changed.assert_not_called()

    def test_wait_for_supervisor_accepts_matching_complete_ack_without_sleep(self):
        saved = defaults()
        observed = {
            "requested": requested_mix_controls(saved), "supervisor": "accepted",
            "pending_controls": [], "supervisor_updated_at": 1001,
            "audible_playback_verified": False,
        }
        with mock.patch("audiohub.mixer_control.application_status",
                        return_value=observed) as status:
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                report = mixer_control.wait_for_supervisor(saved, saved_at=1000)
        self.assertEqual(report["delivery_state"], "accepted")
        self.assertEqual(report["pending_controls"], [])
        self.assertTrue(report["settings_written"])
        self.assertFalse(report["audible_playback_verified"])
        self.assertEqual(report["saved_request"], requested_mix_controls(saved))
        status.assert_called_once_with()
        sleep.assert_not_called()

    def test_wait_for_supervisor_observes_pending_then_acceptance(self):
        saved = defaults()
        saved["master"] = 22
        expected = requested_mix_controls(saved)
        statuses = [
            {"requested": expected, "supervisor": "pending",
             "pending_controls": ["master"]},
            {"requested": expected, "supervisor": "accepted",
             "pending_controls": [], "supervisor_updated_at": 1001},
        ]
        with mock.patch("audiohub.mixer_control.application_status",
                        side_effect=statuses) as status:
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                result = mixer_control.wait_for_supervisor(saved, checks=2, saved_at=1000)
        self.assertEqual(result["delivery_state"], "accepted")
        self.assertEqual(result["pending_controls"], [])
        self.assertEqual(status.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_matching_older_ack_is_not_attributed_to_new_save(self):
        saved = defaults()
        matched_before_write = {
            "requested": requested_mix_controls(saved),
            "supervisor": "accepted", "pending_controls": [],
            "supervisor_updated_at": 999,
        }
        with mock.patch("audiohub.mixer_control.application_status",
                        return_value=matched_before_write) as read:
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                result = mixer_control.wait_for_supervisor(
                    saved, checks=1, saved_at=1000
                )
        self.assertEqual(result["delivery_state"], "pending")
        self.assertIsNone(result["pending_controls"])
        self.assertTrue(result["settings_written"])
        self.assertFalse(result["audible_playback_verified"])
        self.assertEqual(read.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_matching_ack_becomes_valid_only_after_followup_supervisor_poll(self):
        saved = defaults()
        requested = requested_mix_controls(saved)
        older = {"requested": requested, "supervisor": "accepted",
                 "pending_controls": [], "supervisor_updated_at": 1000}
        newer = {**older, "supervisor_updated_at": 1001}
        with mock.patch("audiohub.mixer_control.application_status",
                        side_effect=[older, newer]) as read:
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                result = mixer_control.wait_for_supervisor(
                    saved, checks=2, saved_at=1000
                )
        self.assertEqual(result["delivery_state"], "accepted")
        self.assertEqual(result["pending_controls"], [])
        self.assertEqual(read.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_missing_or_bool_ack_timestamp_never_confirms_postsave(self):
        saved = defaults()
        requested = requested_mix_controls(saved)
        for bogus in (None, True, False, "1002"):
            with self.subTest(timestamp=repr(bogus)):
                observation = {"requested": requested, "supervisor": "accepted",
                               "pending_controls": [],
                               "supervisor_updated_at": bogus}
                with mock.patch("audiohub.mixer_control.application_status",
                                return_value=observation):
                    result = mixer_control.wait_for_supervisor(
                        saved, checks=0, saved_at=1000
                    )
                self.assertEqual(result["delivery_state"], "unavailable")
                self.assertIsNone(result["pending_controls"])
                self.assertFalse(result["audible_playback_verified"])

    def test_wait_for_supervisor_timeout_keeps_unconfirmed_request(self):
        saved = defaults()
        expected = requested_mix_controls(saved)
        status = {"requested": expected, "supervisor": "pending",
                  "pending_controls": ["music.mute"]}
        with mock.patch("audiohub.mixer_control.application_status",
                        return_value=status) as read:
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                result = mixer_control.wait_for_supervisor(saved, checks=2)
        self.assertEqual(result["delivery_state"], "pending")
        self.assertEqual(result["pending_controls"], ["music.mute"])
        self.assertTrue(result["settings_written"])
        self.assertFalse(result["audible_playback_verified"])
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_wait_for_supervisor_unsafe_status_fails_closed(self):
        saved = defaults()
        with mock.patch("audiohub.mixer_control.application_status",
                        side_effect=mixer_control.MixerControlUnavailable("private")) as read:
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                result = mixer_control.wait_for_supervisor(saved, checks=1)
        self.assertEqual(result["delivery_state"], "unavailable")
        self.assertIsNone(result["pending_controls"])
        self.assertTrue(result["settings_written"])
        self.assertEqual(read.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_wait_for_supervisor_detects_concurrent_supersession(self):
        saved = defaults()
        superseding = requested_mix_controls(defaults())
        superseding["master"] = 3
        with mock.patch("audiohub.mixer_control.application_status",
                        return_value={"requested": superseding,
                                      "supervisor": "accepted",
                                      "pending_controls": []}):
            with mock.patch("audiohub.mixer_control.time.sleep") as sleep:
                result = mixer_control.wait_for_supervisor(saved)
        self.assertEqual(result["delivery_state"], "superseded")
        self.assertIsNone(result["pending_controls"])
        self.assertFalse(result["audible_playback_verified"])
        sleep.assert_not_called()

    def test_wait_flag_requires_confirmed_mutation_and_never_previews(self):
        for argv in (
            ["--wait-for-supervisor", "mute-all"],
            ["--wait-for-supervisor", "--preview", "mute-all"],
            ["--wait-for-supervisor", "show"],
            ["--wait-for-supervisor", "status"],
            ["--wait-for-supervisor", "--confirm-local-mixer-change", "status"],
        ):
            with self.subTest(argv=argv):
                with (mock.patch("audiohub.mixer_control.change") as change,
                      mock.patch("audiohub.mixer_control.preview_change") as preview,
                      mock.patch("audiohub.mixer_control.wait_for_supervisor") as wait):
                    with self.assertRaises(SystemExit) as err, redirect_stderr(StringIO()):
                        mixer_control.main(argv)
                    self.assertEqual(err.exception.code, 2)
                    change.assert_not_called()
                    preview.assert_not_called()
                    wait.assert_not_called()

    def test_wait_flag_reports_saved_pending_as_nonzero_without_retrying(self):
        saved = defaults()
        expected = requested_mix_controls(saved)
        report = {"saved_request": expected, "settings_written": True,
                  "delivery_state": "pending", "pending_controls": ["master"],
                  "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.change",
                         return_value=saved) as change,
              mock.patch("audiohub.mixer_control.wait_for_supervisor",
                         return_value=report) as wait):
            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                with self.assertRaises(SystemExit) as err:
                    mixer_control.main(["--confirm-local-mixer-change",
                                        "--wait-for-supervisor", "set-master", "25"])
            self.assertEqual(err.exception.code, 3)
            self.assertIn('"settings_written": true', stdout.getvalue())
            self.assertIn('"delivery_state": "pending"', stdout.getvalue())
            self.assertIn("Settings saved", stderr.getvalue())
            change.assert_called_once_with({"master": 25}, confirmed=True)
            wait.assert_called_once_with(saved)

    def test_wait_flag_success_returns_ack_report_without_claiming_sound(self):
        saved = defaults()
        report = {"saved_request": requested_mix_controls(saved),
                  "settings_written": True, "delivery_state": "accepted",
                  "pending_controls": [], "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.change", return_value=saved) as change,
              mock.patch("audiohub.mixer_control.wait_for_supervisor",
                         return_value=report) as wait):
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--confirm-local-mixer-change",
                                    "--wait-for-supervisor", "mute-all"])
            self.assertIn('"delivery_state": "accepted"', output.getvalue())
            self.assertIn("no audible output was measured", output.getvalue())
            change.assert_called_once_with({
                slot: {"mute": True} for slot in ("music", "laptop", "tablet")
            }, confirmed=True)
            wait.assert_called_once_with(saved)

    def test_local_application_status_accepts_only_current_complete_ack(self):
        runtime_path = self.root / "runtime" / "status.json"
        expected = requested_mix_controls(defaults())
        self.assertEqual(mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )["supervisor"], "unavailable")
        runtime.atomic_json(runtime_path, {
            "updated_at": 995, "usb_route_ready": True,
            "mixer_controls_accepted": expected,
        })
        accepted = mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )
        self.assertEqual(accepted["supervisor"], "accepted")
        self.assertEqual(accepted["supervisor_updated_at"], 995)
        self.assertFalse(accepted["audible_playback_verified"])
        self.assertEqual(accepted["requested"], expected)
        self.assertFalse(self.settings.exists())  # status is read-only
        mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
        pending = mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )
        self.assertEqual(pending["supervisor"], "pending")
        self.assertEqual(pending["requested"]["master"], 30)
        self.assertFalse(pending["audible_playback_verified"])

    def test_pending_diagnostics_name_exact_changed_input_controls(self):
        runtime_path = self.root / "runtime" / "status.json"
        previously_accepted = requested_mix_controls(defaults())
        runtime.atomic_json(runtime_path, {
            "updated_at": 1000, "usb_route_ready": True,
            "mixer_controls_accepted": previously_accepted,
        })
        mixer_control.change({
            "master": 20,
            "music": {"volume": 20},
            "laptop": {"mute": True},
            "tablet": {"volume": 0, "mute": True},
        }, path=self.settings, confirmed=True)
        status = mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )
        self.assertEqual(status["supervisor"], "pending")
        self.assertEqual(status["pending_controls"], [
            "master", "music.volume", "laptop.mute",
            "tablet.volume", "tablet.mute",
        ])
        self.assertFalse(status["audible_playback_verified"])

    def test_equal_acknowledged_settings_have_no_pending_controls(self):
        runtime_path = self.root / "runtime" / "status.json"
        mixer_control.change({"music": {"volume": 50}, "tablet": {"mute": True}},
                             path=self.settings, confirmed=True)
        current = requested_mix_controls(mixer_control.show(path=self.settings))
        runtime.atomic_json(runtime_path, {
            "updated_at": 1000, "usb_route_ready": True,
            "mixer_controls_accepted": current,
        })
        result = mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )
        self.assertEqual(result["supervisor"], "accepted")
        self.assertEqual(result["pending_controls"], [])
        self.assertFalse(result["audible_playback_verified"])

    def test_no_pending_comparison_when_supervisor_evidence_unavailable(self):
        runtime_path = self.root / "runtime" / "status.json"
        expected = requested_mix_controls(defaults())
        for snapshot in (
            None,
            {"updated_at": 1000, "usb_route_ready": False,
             "mixer_controls_accepted": expected},
            {"updated_at": 970, "usb_route_ready": True,
             "mixer_controls_accepted": expected},
            {"updated_at": 1000, "usb_route_ready": True,
             "mixer_controls_accepted": {"master": 70}},
        ):
            if snapshot is not None:
                runtime.atomic_json(runtime_path, snapshot)
            status = mixer_control.application_status(
                path=self.settings, runtime_path=runtime_path, now=1000
            )
            self.assertEqual(status["supervisor"], "unavailable")
            self.assertIsNone(status["pending_controls"])
            self.assertFalse(status["audible_playback_verified"])

    def test_local_status_refuses_stale_untrusted_or_incomplete_claim(self):
        runtime_path = self.root / "runtime" / "status.json"
        expected = requested_mix_controls(defaults())
        snapshot = {"updated_at": 1000, "usb_route_ready": True,
                    "mixer_controls_accepted": expected}
        def check(status, now=1000):
            runtime.atomic_json(runtime_path, status)
            return mixer_control.application_status(
                path=self.settings, runtime_path=runtime_path, now=now
            )["supervisor"]
        self.assertEqual(check(snapshot), "accepted")
        self.assertEqual(check(snapshot, now=1016), "unavailable")
        self.assertEqual(check(snapshot, now=999), "unavailable")
        self.assertEqual(check({**snapshot, "updated_at": True}), "unavailable")
        self.assertEqual(check({**snapshot, "usb_route_ready": False}), "unavailable")
        self.assertEqual(check({**snapshot, "mixer_controls_accepted": None}), "unavailable")
        self.assertEqual(check({
            **snapshot, "mixer_controls_accepted": {"master": 70}
        }), "unavailable")
        # bool compares equal to 1 in Python: never accept type confusion.
        forged = dict(expected)
        forged["master"] = True
        self.assertEqual(check({
            **snapshot, "mixer_controls_accepted": forged
        }), "unavailable")
        target = self.root / "untrusted-status.json"
        target.write_text(json.dumps(snapshot))
        runtime_path.unlink()
        runtime_path.symlink_to(target)
        self.assertEqual(mixer_control.application_status(
            path=self.settings, runtime_path=runtime_path, now=1000
        )["supervisor"], "unavailable")

    def test_local_status_cli_does_not_mutate_or_claim_audio_proof(self):
        payload = {"requested": requested_mix_controls(defaults()),
                   "supervisor": "accepted", "audible_playback_verified": False}
        with mock.patch("audiohub.mixer_control.application_status",
                        return_value=payload) as status:
            with mock.patch("audiohub.mixer_control.change") as change:
                with redirect_stdout(StringIO()) as stdout:
                    mixer_control.main(["status"])
                self.assertIn('"supervisor": "accepted"', stdout.getvalue())
                self.assertIn("no hardware audio was measured", stdout.getvalue())
                status.assert_called_once_with()
                change.assert_not_called()

    def test_supervisor_ack_requires_usb_and_all_three_eq_sinks(self):
        from types import SimpleNamespace
        supervisor = object.__new__(runtime.Supervisor)
        supervisor.settings = defaults()
        supervisor.route_plan = runtime.default_routes()
        supervisor.assignments = {}
        supervisor.loopbacks = {}
        supervisor.retry_state = {}
        supervisor.route_failures_total = 0
        supervisor.output_switch_failures = 0
        self.assertIsNotNone(requested_mix_controls(defaults()))
        graph = {"links_inspected": True,
                 "eq_output_to_usb_direct_link": {c: False for c in ("music", "laptop", "tablet")}}
        captured = []
        ids = {"audiohub.music": 11, "audiohub.laptop": 12, "audiohub.tablet": 13}
        result = SimpleNamespace(returncode=0, stdout=b"[]")
        with (mock.patch("audiohub.runtime.run", return_value=result) as pipe,
              mock.patch("audiohub.runtime.pipewire_nodes", return_value=[]),
              mock.patch("audiohub.runtime.summarize_links", return_value=graph),
              mock.patch("audiohub.runtime.choose_usb_output", return_value={"id": 99}),
              mock.patch("audiohub.runtime.bluetooth_sources", return_value=[]),
              mock.patch("audiohub.runtime.virtual_sinks", return_value=ids),
              mock.patch("audiohub.runtime.load_routes", return_value=runtime.default_routes()),
              mock.patch("audiohub.runtime.read_json", return_value=defaults()),
              mock.patch("audiohub.runtime.atomic_json", side_effect=lambda p, s: captured.append(s)),
              mock.patch.object(supervisor, "_route")):
            supervisor.poll()
            self.assertEqual(captured[-1]["mixer_controls_accepted"],
                             requested_mix_controls(defaults()))
            self.assertTrue(captured[-1]["usb_route_ready"])
            self.assertTrue(any(x.args[0] == "wpctl" for x in pipe.call_args_list))
        captured.clear()
        with (mock.patch("audiohub.runtime.run", return_value=result),
              mock.patch("audiohub.runtime.pipewire_nodes", return_value=[]),
              mock.patch("audiohub.runtime.summarize_links", return_value=graph),
              mock.patch("audiohub.runtime.choose_usb_output", return_value={"id": 99}),
              mock.patch("audiohub.runtime.bluetooth_sources", return_value=[]),
              mock.patch("audiohub.runtime.virtual_sinks", return_value={
                  "audiohub.music": 11, "audiohub.laptop": 12,
              }),
              mock.patch("audiohub.runtime.load_routes", return_value=runtime.default_routes()),
              mock.patch("audiohub.runtime.read_json", return_value=defaults()),
              mock.patch("audiohub.runtime.atomic_json", side_effect=lambda p, s: captured.append(s)),
              mock.patch.object(supervisor, "_route")):
            supervisor.poll()
        self.assertIsNone(captured[-1]["mixer_controls_accepted"])

    def test_computed_supervisor_commands_reflect_saved_levels_and_mutes(self):
        from audiohub.mixer import volume_commands
        mixer_control.change({"master": 20, "music": {"volume": 14},
                              "tablet": {"mute": True}},
                             path=self.settings, confirmed=True)
        current = mixer_control.show(path=self.settings)
        commands = volume_commands(current, {"music": 31, "tablet": 33}, 11)
        self.assertEqual(commands[0][:3], ["wpctl", "set-volume", "11"])
        self.assertIn(["wpctl", "set-volume", "31", "0.14"], commands)
        self.assertIn(["wpctl", "set-mute", "33", "1"], commands)
        self.assertTrue(all(isinstance(a, list) for a in commands))


if __name__ == "__main__":
    unittest.main()
