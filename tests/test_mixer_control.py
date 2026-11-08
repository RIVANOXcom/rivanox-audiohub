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

    def test_copy_eq_transfers_three_bands_atomically_but_no_other_controls(self):
        before = mixer_control.change({
            "master": 21,
            "music": {"bass": 7, "mid": -4, "treble": 3,
                      "volume": 19, "mute": True},
            "laptop": {"bass": -1, "mid": 1, "treble": -3,
                       "volume": 41, "mute": False},
            "tablet": {"bass": -2, "mid": 3, "treble": -6,
                       "volume": 24, "mute": False},
        }, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        patch, revision = mixer_control.copy_input_eq_patch(
            "music", "tablet", path=self.settings)
        self.assertEqual(patch, {"tablet": {
            "bass": 7, "mid": -4, "treble": 3}})
        plan = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual(plan["revision"], revision)
        self.assertEqual([x["band"] for x in plan["eq_changes"]],
                         ["bass", "mid", "treble"])
        self.assertEqual(plan["would_change"], [])
        self.assertFalse(plan["eq_live_applied"])
        self.assertEqual(self.settings.read_bytes(), raw)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            saved = mixer_control.change(
                patch, path=self.settings, confirmed=True,
                if_revision=revision)
            atomic.assert_called_once()
        for band in ("bass", "mid", "treble"):
            self.assertEqual(saved["tablet"][band], before["music"][band])
        self.assertEqual(saved["tablet"]["volume"], before["tablet"]["volume"])
        self.assertEqual(saved["tablet"]["mute"], before["tablet"]["mute"])
        self.assertEqual(saved["laptop"], before["laptop"])
        self.assertEqual(saved["music"], before["music"])
        self.assertEqual(saved["master"], before["master"])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_copy_eq_cli_preview_then_separate_exact_revision_confirm(self):
        mixer_control.change({
            "music": {"bass": 8, "mid": -3, "treble": 1, "mute": True},
            "laptop": {"volume": 13, "bass": -2},
        }, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        original_copy = mixer_control.copy_input_eq_patch
        original_preview = mixer_control.preview_change
        original_change = mixer_control.change
        with (mock.patch(
                "audiohub.mixer_control.copy_input_eq_patch",
                side_effect=lambda source, destination:
                original_copy(source, destination, path=self.settings)),
              mock.patch(
                "audiohub.mixer_control.preview_change",
                side_effect=lambda patch, **kwargs:
                original_preview(patch, path=self.settings, **kwargs)),
              mock.patch(
                "audiohub.mixer_control.change",
                side_effect=lambda patch, **kwargs:
                original_change(patch, path=self.settings, **kwargs)) as writer):
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--preview", "copy-eq", "music", "laptop"])
            preview = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(preview["eq_operation"], "copy-eq")
            self.assertEqual(preview["copy_source"], "music")
            self.assertEqual(preview["target_input"], "laptop")
            self.assertTrue(preview["eq_staging_separate"])
            self.assertEqual(len(preview["eq_changes"]), 3)
            self.assertFalse(preview["eq_live_applied"])
            self.assertFalse(preview["settings_written"])
            writer.assert_not_called()
            self.assertEqual(self.settings.read_bytes(), raw)
            with redirect_stdout(StringIO()) as output:
                mixer_control.main([
                    "--confirm-local-mixer-change",
                    "--if-preview-revision", preview["revision"],
                    "copy-eq", "music", "laptop",
                ])
            saved = json.loads(output.getvalue().splitlines()[0])
            self.assertTrue(saved["requested_eq_settings_saved"])
            self.assertFalse(saved["pipewire_eq_staged"])
            self.assertFalse(saved["pipewire_eq_live_applied"])
            self.assertTrue(saved["settings"]["music"]["mute"])
            self.assertEqual(saved["settings"]["laptop"]["bass"], 8)
            self.assertEqual(saved["settings"]["laptop"]["mid"], -3)
            self.assertEqual(saved["settings"]["laptop"]["treble"], 1)
            self.assertEqual(saved["settings"]["laptop"]["volume"], 13)
            writer.assert_called_once_with(
                {"laptop": {"bass": 8, "mid": -3, "treble": 1}},
                confirmed=True, if_revision=preview["revision"])

    def test_swap_eq_exchanges_two_curves_atomically_and_preserves_all_else(self):
        before = mixer_control.change({
            "master": 19,
            "music": {"bass": 8, "mid": -4, "treble": 2,
                      "volume": 31, "mute": True},
            "tablet": {"bass": -3, "mid": 1, "treble": -7,
                       "volume": 18, "mute": False},
            "laptop": {"bass": 5, "mid": 3, "treble": 0,
                       "volume": 27, "mute": True},
        }, path=self.settings, confirmed=True)
        original_bytes = self.settings.read_bytes()
        patch, revision = mixer_control.swap_input_eq_patch(
            "music", "tablet", path=self.settings)
        self.assertEqual(patch, {
            "music": {"bass": -3, "mid": 1, "treble": -7},
            "tablet": {"bass": 8, "mid": -4, "treble": 2},
        })
        plan = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual(plan["revision"], revision)
        self.assertEqual(len(plan["eq_changes"]), 6)
        self.assertEqual(plan["planned_changes"], [])
        self.assertFalse(plan["eq_live_applied"])
        self.assertEqual(self.settings.read_bytes(), original_bytes)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as writer:
            after = mixer_control.change(
                patch, path=self.settings, confirmed=True,
                if_revision=revision)
            writer.assert_called_once()
        for band in ("bass", "mid", "treble"):
            self.assertEqual(after["music"][band], before["tablet"][band])
            self.assertEqual(after["tablet"][band], before["music"][band])
        for slot in ("music", "tablet"):
            for field in ("volume", "mute"):
                self.assertEqual(after[slot][field], before[slot][field])
        self.assertEqual(after["laptop"], before["laptop"])
        self.assertEqual(after["master"], before["master"])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_swap_eq_cli_review_and_separate_exact_revision_confirmation(self):
        mixer_control.change({
            "music": {"bass": 6, "mid": -2, "treble": 3, "mute": True},
            "laptop": {"bass": -5, "mid": 4, "treble": 1, "volume": 13},
        }, path=self.settings, confirmed=True)
        original = self.settings.read_bytes()
        real_swap = mixer_control.swap_input_eq_patch
        real_preview = mixer_control.preview_change
        real_change = mixer_control.change
        with (mock.patch(
                "audiohub.mixer_control.swap_input_eq_patch",
                side_effect=lambda left, right:
                real_swap(left, right, path=self.settings)),
              mock.patch(
                "audiohub.mixer_control.preview_change",
                side_effect=lambda patch, **kwargs:
                real_preview(patch, path=self.settings, **kwargs)),
              mock.patch(
                "audiohub.mixer_control.change",
                side_effect=lambda patch, **kwargs:
                real_change(patch, path=self.settings, **kwargs)) as writer):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["--preview", "swap-eq", "music", "laptop"])
            preview = json.loads(out.getvalue().splitlines()[0])
            self.assertEqual(preview["eq_operation"], "swap-eq")
            self.assertEqual(preview["swap_inputs"], ["music", "laptop"])
            self.assertTrue(preview["eq_staging_separate"])
            self.assertEqual(len(preview["eq_changes"]), 6)
            self.assertEqual(preview["would_change"], [])
            self.assertFalse(preview["settings_written"])
            self.assertFalse(preview["eq_live_applied"])
            self.assertEqual(self.settings.read_bytes(), original)
            writer.assert_not_called()
            with redirect_stdout(StringIO()) as out:
                mixer_control.main([
                    "--confirm-local-mixer-change",
                    "--if-preview-revision", preview["revision"],
                    "swap-eq", "music", "laptop",
                ])
            saved = json.loads(out.getvalue().splitlines()[0])
            self.assertTrue(saved["requested_eq_settings_saved"])
            self.assertFalse(saved["pipewire_eq_staged"])
            self.assertFalse(saved["pipewire_eq_live_applied"])
            self.assertEqual(saved["settings"]["music"]["bass"], -5)
            self.assertEqual(saved["settings"]["laptop"]["bass"], 6)
            self.assertEqual(saved["settings"]["music"]["mute"], True)
            self.assertEqual(saved["settings"]["laptop"]["volume"], 13)
            writer.assert_called_once_with({
                "music": {"bass": -5, "mid": 4, "treble": 1},
                "laptop": {"bass": 6, "mid": -2, "treble": 3},
            }, confirmed=True, if_revision=preview["revision"])

    def test_swap_eq_invalid_preview_and_stale_aba_never_write(self):
        for invalid in (None, True, 1, "", "unknown", "music;rm"):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.swap_input_eq_patch(
                        invalid, "music", path=self.settings)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.swap_input_eq_patch(
                "music", "music", path=self.settings)
        self.assertFalse(self.settings.parent.exists())
        for command in (
            ["swap-eq", "music", "tablet"],
            ["--confirm-local-mixer-change", "swap-eq", "music", "tablet"],
            ["--preview", "--confirm-local-mixer-change",
             "swap-eq", "music", "tablet"],
            ["--preview", "--if-preview-revision", "v1-" + "a"*64,
             "swap-eq", "music", "tablet"],
            ["--preview", "swap-eq", "music", "music"],
            ["--preview", "swap-eq", "music", "private/secret"],
            ["--preview", "swap-eq", "music", "tablet", "extra"],
            ["--preview", "--compare-baseline", "b1-fake",
             "swap-eq", "music", "tablet"],
            ["--wait-for-supervisor", "--confirm-local-mixer-change",
             "--if-preview-revision", "v1-" + "a"*64,
             "swap-eq", "music", "tablet"],
        ):
            with (self.subTest(command=command),
                  mock.patch("audiohub.mixer_control.change") as writer,
                  redirect_stdout(StringIO()) as out,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main(command)
                self.assertEqual(failed.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                writer.assert_not_called()
            self.assertFalse(self.settings.parent.exists())
        real_swap = mixer_control.swap_input_eq_patch
        real_preview = mixer_control.preview_change
        real_change = mixer_control.change
        with (mock.patch(
                "audiohub.mixer_control.swap_input_eq_patch",
                side_effect=lambda a, b: real_swap(a, b, path=self.settings)),
              mock.patch(
                "audiohub.mixer_control.preview_change",
                side_effect=lambda patch, **kw:
                real_preview(patch, path=self.settings, **kw)),
              mock.patch(
                "audiohub.mixer_control.change",
                side_effect=lambda patch, **kw:
                real_change(patch, path=self.settings, **kw))):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["--preview", "swap-eq", "music", "tablet"])
            revision = json.loads(out.getvalue().splitlines()[0])["revision"]
            # New generations must reject an old preview, even after values
            # are restored (A -> B -> A). The stale handler is read-only.
            real_change({"music": {"bass": 2}},
                        path=self.settings, confirmed=True)
            real_change({"music": {"bass": 0}},
                        path=self.settings, confirmed=True)
            snapshot = self.settings.read_bytes()
            with (redirect_stdout(StringIO()) as out,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main([
                        "--confirm-local-mixer-change",
                        "--if-preview-revision", revision,
                        "swap-eq", "music", "tablet",
                    ])
            self.assertEqual(failed.exception.code, 4)
            report = json.loads(out.getvalue().splitlines()[0])
            self.assertEqual(report["status"], "eq-swap-stale")
            self.assertFalse(report["settings_written"])
            self.assertEqual(report["fresh_preview"]["eq_operation"], "swap-eq")
            self.assertNotEqual(report["fresh_preview"]["revision"], revision)
            self.assertEqual(self.settings.read_bytes(), snapshot)

    def test_reset_eq_neutralizes_one_input_only_in_single_confirmed_update(self):
        original = mixer_control.change({
            "master": 12,
            "music": {"bass": 6, "mid": 2, "treble": -7, "mute": True,
                      "volume": 19},
            "laptop": {"bass": -3, "mid": 5, "treble": 2},
        }, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        patch = mixer_control.reset_input_eq_patch("music")
        plan = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual(len(plan["eq_changes"]), 3)
        self.assertEqual(plan["would_change"], [])
        self.assertEqual(self.settings.read_bytes(), before)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            actual = mixer_control.change(
                patch, path=self.settings, confirmed=True,
                if_revision=plan["revision"])
            atomic.assert_called_once()
        self.assertEqual({band: actual["music"][band] for band in
                          ("bass", "mid", "treble")},
                         {"bass": 0, "mid": 0, "treble": 0})
        for field in ("volume", "mute"):
            self.assertEqual(actual["music"][field], original["music"][field])
        for field in ("master", "laptop", "tablet"):
            self.assertEqual(actual[field], original[field])
        original_preview, original_change = (
            mixer_control.preview_change, mixer_control.change
        )
        with (mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=lambda patch, **kw:
                         original_preview(patch, path=self.settings, **kw)),
              mock.patch("audiohub.mixer_control.change",
                         side_effect=lambda patch, **kw:
                         original_change(patch, path=self.settings, **kw))):
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--preview", "reset-eq", "music"])
            report = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(report["eq_operation"], "reset-eq")
            self.assertEqual(report["target_input"], "music")
            self.assertEqual(report["eq_changes"], [])
            self.assertFalse(report["eq_live_applied"])
            self.assertFalse(report["settings_written"])

    def test_copy_reset_eq_invalid_or_stale_never_write_or_leak(self):
        for bad in (None, True, 1, "", "random;source", "MUSIC"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.reset_input_eq_patch(bad)
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.copy_input_eq_patch(bad, "tablet",
                                                       path=self.settings)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.copy_input_eq_patch("music", "music",
                                               path=self.settings)
        self.assertFalse(self.settings.parent.exists())
        for command in (
            ["copy-eq", "music", "tablet"],
            ["reset-eq", "music"],
            ["--confirm-local-mixer-change", "copy-eq", "music", "tablet"],
            ["--confirm-local-mixer-change", "reset-eq", "music"],
            ["--preview", "--confirm-local-mixer-change",
             "copy-eq", "music", "tablet"],
            ["--preview", "--if-preview-revision", "v1-" + "a"*64,
             "reset-eq", "music"],
            ["--preview", "copy-eq", "music", "music"],
            ["--preview", "copy-eq", "music", "private/secret"],
            ["--preview", "reset-eq", "private/secret"],
            ["--preview", "copy-eq", "music", "tablet", "extra"],
        ):
            with (self.subTest(command=command),
                  mock.patch("audiohub.mixer_control.change") as writer,
                  redirect_stdout(StringIO()) as output,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as err:
                    mixer_control.main(command)
                self.assertEqual(err.exception.code, 2)
                self.assertEqual(output.getvalue(), "")
                writer.assert_not_called()
            self.assertFalse(self.settings.parent.exists())
        mixer_control.change({"music": {"bass": 3}},
                             path=self.settings, confirmed=True)
        old = mixer_control.preview_change(
            {"tablet": {"bass": 3}}, path=self.settings)["revision"]
        mixer_control.change({"music": {"bass": 4}},
                             path=self.settings, confirmed=True)
        mixer_control.change({"music": {"bass": 3}},
                             path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.change({"tablet": {"bass": 3}},
                                 path=self.settings, confirmed=True,
                                 if_revision=old)
        self.assertEqual(self.settings.read_bytes(), raw)

    def test_fixed_eq_sound_presets_have_reviewable_bounded_values(self):
        expected = {
            "warm": {"bass": 3, "mid": 0, "treble": -1},
            "voice": {"bass": -2, "mid": 3, "treble": 1},
            "detail": {"bass": 0, "mid": 1, "treble": 3},
        }
        self.assertEqual(set(mixer_control.EQ_PRESET_CURVES), set(expected))
        for preset, curve in expected.items():
            with self.subTest(profile=preset):
                self.assertEqual(mixer_control.eq_preset_patch("music", preset),
                                 {"music": curve})
                self.assertTrue(all(type(v) is int and -12 <= v <= 12
                                    for v in curve.values()))
        for invalid_slot in ("unknown", "music;sh", None, 0, True, []):
            with self.subTest(slot=repr(invalid_slot)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.eq_preset_patch(invalid_slot, "warm")
        for invalid_profile in ("flat", "WARM", "voice;id", "", None, True, []):
            with self.subTest(profile=repr(invalid_profile)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.eq_preset_patch("music", invalid_profile)
        self.assertFalse(self.settings.parent.exists())

    def test_eq_sound_preset_is_one_private_atomic_change_never_live_eq(self):
        before = mixer_control.change({
            "master": 23,
            "music": {"volume": 19, "mute": True, "bass": -8,
                      "mid": 5, "treble": -3},
            "laptop": {"bass": 7, "mid": -4, "treble": 2,
                       "volume": 22, "mute": False},
            "tablet": {"volume": 17, "mute": True, "treble": 6},
        }, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        patch = mixer_control.eq_preset_patch("music", "voice")
        plan = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual(plan["mode"], "preview-only")
        self.assertFalse(plan["settings_written"])
        self.assertFalse(plan["eq_live_applied"])
        self.assertEqual(self.settings.read_bytes(), raw)
        self.assertEqual([v["band"] for v in plan["eq_changes"]],
                         ["bass", "mid", "treble"])
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as writer:
            saved = mixer_control.change(
                patch, path=self.settings, confirmed=True,
                if_revision=plan["revision"])
            writer.assert_called_once()
        self.assertEqual({band: saved["music"][band]
                          for band in ("bass", "mid", "treble")},
                         {"bass": -2, "mid": 3, "treble": 1})
        self.assertEqual(saved["music"]["volume"], before["music"]["volume"])
        self.assertEqual(saved["music"]["mute"], before["music"]["mute"])
        self.assertEqual(saved["master"], before["master"])
        self.assertEqual(saved["laptop"], before["laptop"])
        self.assertEqual(saved["tablet"], before["tablet"])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_eq_sound_preset_cli_review_confirm_and_aba_stale_guard(self):
        mixer_control.change({
            "music": {"bass": -3, "mid": -2, "treble": 2, "mute": True},
            "tablet": {"bass": 5, "mid": -6, "treble": 7},
        }, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        original_preview, original_change = (
            mixer_control.preview_change, mixer_control.change)
        with (mock.patch(
                "audiohub.mixer_control.preview_change",
                side_effect=lambda patch, **kw:
                    original_preview(patch, path=self.settings, **kw)),
              mock.patch(
                "audiohub.mixer_control.change",
                side_effect=lambda patch, **kw:
                    original_change(patch, path=self.settings, **kw)) as writer):
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--preview", "eq-preset", "music", "warm"])
            result = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(result["eq_operation"], "eq-preset")
            self.assertEqual(result["eq_preset"], "warm")
            self.assertEqual(result["preset_curve_db"],
                             {"bass": 3, "mid": 0, "treble": -1})
            self.assertTrue(result["preset_not_calibrated"])
            self.assertTrue(result["eq_staging_separate"])
            self.assertFalse(result["settings_written"])
            self.assertFalse(result["eq_live_applied"])
            self.assertEqual(self.settings.read_bytes(), raw)
            writer.assert_not_called()
            with redirect_stdout(StringIO()) as output:
                mixer_control.main([
                    "--confirm-local-mixer-change", "--if-preview-revision",
                    result["revision"], "eq-preset", "music", "warm",
                ])
            saved = json.loads(output.getvalue().splitlines()[0])
            self.assertTrue(saved["requested_eq_settings_saved"])
            self.assertFalse(saved["pipewire_eq_staged"])
            self.assertFalse(saved["pipewire_eq_live_applied"])
            self.assertEqual(saved["settings"]["music"]["bass"], 3)
            self.assertEqual(saved["settings"]["music"]["mid"], 0)
            self.assertEqual(saved["settings"]["music"]["treble"], -1)
            self.assertTrue(saved["settings"]["music"]["mute"])
            self.assertEqual(saved["settings"]["tablet"]["bass"], 5)
            writer.assert_called_once_with({
                "music": {"bass": 3, "mid": 0, "treble": -1},
            }, confirmed=True, if_revision=result["revision"])
        stale = mixer_control.preview_change(
            mixer_control.eq_preset_patch("music", "detail"),
            path=self.settings)["revision"]
        mixer_control.change({"master": 34}, path=self.settings, confirmed=True)
        mixer_control.change({"master": 70}, path=self.settings, confirmed=True)
        current = self.settings.read_bytes()
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.change(
                mixer_control.eq_preset_patch("music", "detail"),
                path=self.settings, confirmed=True, if_revision=stale)
        self.assertEqual(self.settings.read_bytes(), current)

    def test_eq_sound_preset_invalid_actions_do_not_write_or_claim_success(self):
        for args in (
            ["eq-preset", "music", "warm"],
            ["--confirm-local-mixer-change", "eq-preset", "music", "warm"],
            ["--if-preview-revision", "v1-" + "a" * 64,
             "eq-preset", "music", "warm"],
            ["--preview", "--confirm-local-mixer-change",
             "eq-preset", "music", "warm"],
            ["--preview", "--if-preview-revision", "v1-" + "a" * 64,
             "eq-preset", "music", "warm"],
            ["--preview", "--wait-for-supervisor", "eq-preset", "music", "warm"],
            ["--preview", "eq-preset", "invalid", "warm"],
            ["--preview", "eq-preset", "music", "WARM"],
            ["--preview", "eq-preset", "music", "voice;whoami"],
            ["--preview", "eq-preset", "music"],
            ["--preview", "eq-preset", "music", "warm", "extra"],
        ):
            with (self.subTest(args=args),
                  mock.patch("audiohub.mixer_control.change") as writer,
                  redirect_stdout(StringIO()) as stdout,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main(args)
                self.assertEqual(failed.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                writer.assert_not_called()
        self.assertFalse(self.settings.parent.exists())

    def test_set_eq_curve_one_generation_changes_only_selected_input_bands(self):
        before = mixer_control.change({
            "master": 28,
            "music": {"bass": 4, "mid": -3, "treble": 2,
                      "volume": 19, "mute": True},
            "laptop": {"bass": 2, "mid": 1, "treble": -2,
                       "volume": 42, "mute": False},
            "tablet": {"volume": 37, "mute": True},
        }, path=self.settings, confirmed=True)
        patch = {"music": {"bass": -6, "mid": 5, "treble": -1}}
        raw = self.settings.read_bytes()
        plan = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual([x["band"] for x in plan["eq_changes"]],
                         ["bass", "mid", "treble"])
        self.assertEqual(plan["planned_changes"], [])
        self.assertFalse(plan["eq_live_applied"])
        self.assertFalse(plan["settings_written"])
        self.assertEqual(self.settings.read_bytes(), raw)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as writer:
            saved = mixer_control.change(patch, path=self.settings,
                                         confirmed=True,
                                         if_revision=plan["revision"])
            writer.assert_called_once()
        self.assertEqual(
            {band: saved["music"][band] for band in ("bass", "mid", "treble")},
            {"bass": -6, "mid": 5, "treble": -1})
        for field in ("volume", "mute"):
            self.assertEqual(saved["music"][field], before["music"][field])
        self.assertEqual(saved["master"], before["master"])
        self.assertEqual(saved["laptop"], before["laptop"])
        self.assertEqual(saved["tablet"], before["tablet"])
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_set_eq_curve_cli_preview_and_separate_confirm_without_live_eq(self):
        mixer_control.change({
            "music": {"bass": 3, "mid": -1, "treble": 5,
                      "mute": True, "volume": 29},
            "tablet": {"bass": 9, "mid": -8, "treble": -2},
        }, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        preview = mixer_control.preview_change
        change = mixer_control.change
        with (mock.patch(
                "audiohub.mixer_control.preview_change",
                side_effect=lambda patch, **kw:
                preview(patch, path=self.settings, **kw)),
              mock.patch(
                "audiohub.mixer_control.change",
                side_effect=lambda patch, **kw:
                change(patch, path=self.settings, **kw)) as writer):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main([
                    "--preview", "set-eq-curve", "music", "-12", "0", "12"
                ])
            plan = json.loads(out.getvalue().splitlines()[0])
            self.assertEqual(plan["eq_operation"], "set-eq-curve")
            self.assertEqual(plan["target_input"], "music")
            self.assertTrue(plan["eq_staging_separate"])
            self.assertEqual(len(plan["eq_changes"]), 3)
            self.assertEqual(plan["would_change"], [])
            self.assertFalse(plan["eq_live_applied"])
            writer.assert_not_called()
            self.assertEqual(self.settings.read_bytes(), raw)
            with redirect_stdout(StringIO()) as out:
                mixer_control.main([
                    "--confirm-local-mixer-change", "--if-preview-revision",
                    plan["revision"], "set-eq-curve", "music", "-12", "0", "12"
                ])
            saved = json.loads(out.getvalue().splitlines()[0])
            self.assertTrue(saved["requested_eq_settings_saved"])
            self.assertFalse(saved["pipewire_eq_staged"])
            self.assertFalse(saved["pipewire_eq_live_applied"])
            self.assertEqual(saved["settings"]["music"]["bass"], -12)
            self.assertEqual(saved["settings"]["music"]["mid"], 0)
            self.assertEqual(saved["settings"]["music"]["treble"], 12)
            self.assertTrue(saved["settings"]["music"]["mute"])
            self.assertEqual(saved["settings"]["music"]["volume"], 29)
            self.assertEqual(saved["settings"]["tablet"]["bass"], 9)
            writer.assert_called_once_with({
                "music": {"bass": -12, "mid": 0, "treble": 12},
            }, confirmed=True, if_revision=plan["revision"])

    def test_set_eq_curve_invalid_and_aba_stale_never_write(self):
        for command in (
            ["set-eq-curve", "music", "1", "2", "3"],
            ["--confirm-local-mixer-change",
             "set-eq-curve", "music", "1", "2", "3"],
            ["--preview", "--confirm-local-mixer-change",
             "set-eq-curve", "music", "1", "2", "3"],
            ["--preview", "--if-preview-revision", "v1-" + "a" * 64,
             "set-eq-curve", "music", "1", "2", "3"],
            ["--preview", "set-eq-curve", "music", "13", "0", "0"],
            ["--preview", "set-eq-curve", "tablet", "-13", "0", "0"],
            ["--preview", "set-eq-curve", "music", "1", "0", "100"],
            ["--preview", "set-eq-curve", "invalid", "1", "2", "3"],
            ["--preview", "set-eq-curve", "music", "1", "2"],
            ["--preview", "set-eq-curve", "music", "1", "2", "3", "4"],
        ):
            with (self.subTest(command=command),
                  mock.patch("audiohub.mixer_control.change") as writer,
                  redirect_stdout(StringIO()) as stdout,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main(command)
                self.assertEqual(failed.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                writer.assert_not_called()
            self.assertFalse(self.settings.parent.exists())
        current = mixer_control.change(
            {"music": {"bass": 2, "mid": -2, "treble": 2}},
            path=self.settings, confirmed=True)
        old = mixer_control.preview_change(
            {"music": {"bass": 3, "mid": -3, "treble": 3}},
            path=self.settings)["revision"]
        mixer_control.change({"music": {"bass": 4}},
                             path=self.settings, confirmed=True)
        mixer_control.change({"music": {"bass": current["music"]["bass"]}},
                             path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.change(
                {"music": {"bass": 3, "mid": -3, "treble": 3}},
                path=self.settings, confirmed=True, if_revision=old)
        self.assertEqual(self.settings.read_bytes(), raw)

    def test_set_eq_preview_and_exact_confirm_stage_only_requested_band(self):
        before = mixer_control.change({
            "master": 30,
            "music": {"volume": 25, "mute": True, "mid": 2},
            "tablet": {"volume": 15, "bass": -3},
        }, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        original_preview, original_change = mixer_control.preview_change, mixer_control.change
        with (mock.patch(
                "audiohub.mixer_control.preview_change",
                side_effect=lambda patch, **kw:
                original_preview(patch, path=self.settings, **kw)) as preview,
              mock.patch(
                "audiohub.mixer_control.change",
                side_effect=lambda patch, **kw:
                original_change(patch, path=self.settings, **kw)) as write):
            with redirect_stdout(StringIO()) as output:
                mixer_control.main(["--preview", "set-eq", "music", "treble", "-5"])
            plan = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(plan["eq_changes"], [{
                "source": "music", "band": "treble",
                "before": 0, "after": -5}])
            self.assertEqual(plan["would_change"], [])
            self.assertFalse(plan["eq_live_applied"])
            self.assertFalse(plan["settings_written"])
            self.assertEqual(self.settings.read_bytes(), raw)
            preview.assert_called_once_with({"music": {"treble": -5}})
            write.assert_not_called()
            with redirect_stdout(StringIO()) as output:
                mixer_control.main([
                    "--confirm-local-mixer-change",
                    "--if-preview-revision", plan["revision"],
                    "set-eq", "music", "treble", "-5",
                ])
            committed = json.loads(output.getvalue().splitlines()[0])
            self.assertTrue(committed["requested_eq_settings_saved"])
            self.assertFalse(committed["pipewire_eq_staged"])
            self.assertFalse(committed["pipewire_eq_live_applied"])
            self.assertEqual(committed["settings"]["music"]["treble"], -5)
            write.assert_called_once_with({"music": {"treble": -5}},
                                          confirmed=True,
                                          if_revision=plan["revision"])
        actual = mixer_control.show(path=self.settings)
        self.assertEqual(actual["music"]["treble"], -5)
        self.assertEqual(actual["music"]["mid"], before["music"]["mid"])
        self.assertEqual(actual["master"], 30)
        self.assertEqual(actual["tablet"], before["tablet"])
        self.assertTrue(actual["music"]["mute"])

    def test_set_eq_requires_revision_and_bounded_channel_band_without_write(self):
        before = mixer_control.change({"music": {"volume": 15}},
                                      path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        bad_cases = [
            ["set-eq", "music", "bass", "4"],
            ["--confirm-local-mixer-change", "set-eq", "music", "bass", "4"],
            ["--if-preview-revision", "v1-" + "0"*64,
             "set-eq", "music", "bass", "4"],
            ["--preview", "--confirm-local-mixer-change",
             "set-eq", "music", "bass", "4"],
            ["--preview", "set-eq", "music", "bass", "13"],
            ["--preview", "set-eq", "music", "mid", "-13"],
            ["--preview", "set-eq", "music", "mid", "1.5"],
            ["--preview", "set-eq", "music", "invalid", "1"],
            ["--preview", "set-eq", "incorrect", "bass", "1"],
        ]
        for args in bad_cases:
            with (self.subTest(args=args),
                  mock.patch("audiohub.mixer_control.change") as write,
                  redirect_stdout(StringIO()) as out,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as exc:
                    mixer_control.main(args)
                self.assertEqual(exc.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                write.assert_not_called()
            self.assertEqual(self.settings.read_bytes(), raw)
        revision = mixer_control.preview_change(
            {"music": {"bass": 4}}, path=self.settings)["revision"]
        mixer_control.change({"tablet": {"mid": 1}}, path=self.settings,
                             confirmed=True)
        stale = self.settings.read_bytes()
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.change({"music": {"bass": 4}},
                                 path=self.settings, confirmed=True,
                                 if_revision=revision)
        self.assertEqual(self.settings.read_bytes(), stale)

    def test_isolate_input_mutes_other_two_atomically_but_never_unmutes_selected(self):
        original = mixer_control.change({
            "master": 17,
            "music": {"volume": 22, "bass": 3, "mute": False},
            "laptop": {"volume": 14, "treble": -2, "mute": False},
            "tablet": {"volume": 36, "mid": 4, "mute": True},
        }, path=self.settings, confirmed=True)
        before = self.settings.read_bytes()
        selected = "tablet"
        patch = mixer_control.isolate_input_patch(selected)
        self.assertEqual(patch, {
            "music": {"mute": True}, "laptop": {"mute": True}
        })
        preview = mixer_control.preview_change(patch, path=self.settings)
        self.assertEqual(preview["would_change"], [
            "music.mute", "laptop.mute"
        ])
        self.assertTrue(preview["after"]["tablet"]["mute"])
        self.assertEqual(self.settings.read_bytes(), before)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            result = mixer_control.change(
                patch, path=self.settings, confirmed=True,
                if_revision=preview["revision"])
            atomic.assert_called_once()
        for slot in ("music", "laptop"):
            self.assertTrue(result[slot]["mute"])
        self.assertTrue(result["tablet"]["mute"], "Never unmute isolated slot")
        self.assertEqual(result["master"], original["master"])
        for slot in ("music", "laptop", "tablet"):
            for field in ("volume", "bass", "mid", "treble"):
                self.assertEqual(result[slot][field], original[slot][field])
        self.assertEqual(mixer_control.show(path=self.settings), result)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(set(self.settings.parent.iterdir()),
                         {self.settings,
                          self.settings.parent / mixer_control.LOCK_NAME})

    def test_isolate_input_readonly_cli_and_exact_revision_confirm_flow(self):
        mixer_control.change({
            "master": 25,
            "music": {"volume": 20, "mute": False, "bass": 3},
            "laptop": {"volume": 22, "mute": False},
            "tablet": {"volume": 17, "mute": True},
        }, path=self.settings, confirmed=True)
        original = self.settings.read_bytes()
        original_preview = mixer_control.preview_change
        original_change = mixer_control.change
        with (mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=lambda patch, **kw:
                         original_preview(patch, path=self.settings, **kw)) as preview_call,
              mock.patch("audiohub.mixer_control.change",
                         side_effect=lambda patch, **kw:
                         original_change(patch, path=self.settings, **kw)) as change_call):
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main(["--preview", "isolate-input", "music"])
            preview = json.loads(stdout.getvalue().splitlines()[0])
            self.assertEqual(preview["mode"], "preview-only")
            self.assertEqual(preview["would_change"], ["laptop.mute"])
            self.assertFalse(preview["settings_written"])
            self.assertFalse(preview["supervisor_applied"])
            self.assertFalse(preview["audible_playback_verified"])
            self.assertEqual(self.settings.read_bytes(), original)
            change_call.assert_not_called()
            preview_call.assert_called_once_with({
                "laptop": {"mute": True}, "tablet": {"mute": True}
            })
            revision = preview["revision"]
            with redirect_stdout(StringIO()) as out:
                mixer_control.main([
                    "--confirm-local-mixer-change",
                    "--if-preview-revision", revision,
                    "isolate-input", "music",
                ])
            applied = json.loads(out.getvalue().splitlines()[0])
            self.assertFalse(applied["music"]["mute"])
            self.assertTrue(applied["laptop"]["mute"])
            self.assertTrue(applied["tablet"]["mute"])
            self.assertEqual(applied["music"]["bass"], 3)
            change_call.assert_called_once_with({
                "laptop": {"mute": True}, "tablet": {"mute": True}
            }, confirmed=True, if_revision=revision)

    def test_isolate_input_refuses_unreviewed_apply_and_stale_aba_without_writes(self):
        self.assertFalse(self.settings.parent.exists())
        for command in (
            ["isolate-input", "music"],
            ["--confirm-local-mixer-change", "isolate-input", "music"],
            ["--if-preview-revision", "v1-" + "a"*64, "isolate-input", "music"],
            ["--preview", "--confirm-local-mixer-change", "isolate-input", "music"],
            ["--preview", "--if-preview-revision", "v1-" + "a"*64,
             "isolate-input", "music"],
            ["--preview", "--wait-for-supervisor", "isolate-input", "music"],
            ["--confirm-local-profile-save", "--preview", "isolate-input", "music"],
            ["--preview", "isolate-input", "unknown"],
            ["--preview", "isolate-input", "music", "laptop"],
        ):
            with (self.subTest(command=command),
                  mock.patch("audiohub.mixer_control.change") as writer,
                  redirect_stdout(StringIO()) as stdout,
                  redirect_stderr(StringIO())):
                with self.assertRaises(SystemExit) as stopped:
                    mixer_control.main(command)
                self.assertEqual(stopped.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                writer.assert_not_called()
            self.assertFalse(self.settings.parent.exists())

        for invalid in ("UNKNOWN", "music;touch", 22, True, None, ""):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(
                    mixer_control.MixerControlUnavailable):
                mixer_control.isolate_input_patch(invalid)
        before = mixer_control.change(
            {"master": 30, "music": {"mute": False}},
            path=self.settings, confirmed=True)
        preview = mixer_control.preview_change(
            mixer_control.isolate_input_patch("music"), path=self.settings)
        # ABA value reversion must not permit the old approval token.
        mixer_control.change(
            {"master": 40}, path=self.settings, confirmed=True)
        mixer_control.change(
            {"master": 30}, path=self.settings, confirmed=True)
        self.assertEqual(mixer_control.show(path=self.settings), before)
        snapshot = self.settings.read_bytes()
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.change(mixer_control.isolate_input_patch("music"),
                                 path=self.settings, confirmed=True,
                                 if_revision=preview["revision"])
        self.assertEqual(self.settings.read_bytes(), snapshot)

    def test_isolation_is_noop_when_other_two_already_muted_and_no_auto_unmute(self):
        original = mixer_control.change({
            "music": {"mute": True, "volume": 13},
            "laptop": {"mute": True, "volume": 15},
            "tablet": {"mute": True, "volume": 17},
        }, path=self.settings, confirmed=True)
        planned = mixer_control.preview_change(
            mixer_control.isolate_input_patch("laptop"), path=self.settings)
        self.assertEqual(planned["would_change"], [])
        self.assertTrue(all(planned["after"][slot]["mute"]
                            for slot in ("music", "laptop", "tablet")))
        self.assertEqual(mixer_control.show(path=self.settings), original)

    def test_restore_isolation_recovers_only_two_original_mutes_atomically(self):
        original = mixer_control.change({
            "master": 23,
            "music": {"volume": 20, "bass": 4, "mute": True},
            "laptop": {"volume": 15, "mid": -3, "mute": False},
            "tablet": {"volume": 35, "treble": 2, "mute": False},
        }, path=self.settings, confirmed=True)
        isolate = mixer_control.preview_change(
            mixer_control.isolate_input_patch("music"), path=self.settings)
        saved_baseline = isolate["comparison_baseline"]
        mixer_control.change(
            mixer_control.isolate_input_patch("music"),
            path=self.settings, confirmed=True,
            if_revision=isolate["revision"])
        isolated_bytes = self.settings.read_bytes()
        restored_plan = mixer_control.preview_restore_isolation(
            "music", saved_baseline, path=self.settings)
        self.assertEqual(self.settings.read_bytes(), isolated_bytes)
        self.assertEqual(restored_plan["mode"], "preview-only")
        self.assertEqual(restored_plan["operation"], "isolation-restore-preview")
        self.assertEqual(restored_plan["source"], "music")
        self.assertEqual(restored_plan["scope"], "two-other-input-mutes-only")
        self.assertEqual(restored_plan["baseline_trust"],
                         "operator_supplied_not_authenticated")
        self.assertTrue(restored_plan["selected_input_mute_preserved"])
        self.assertEqual(restored_plan["would_change"], [
            "laptop.mute", "tablet.mute"])
        self.assertTrue(restored_plan["before"]["music"]["mute"])
        self.assertTrue(restored_plan["after"]["music"]["mute"])
        self.assertFalse(restored_plan["settings_written"])
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as atomic:
            result = mixer_control.restore_isolation(
                "music", saved_baseline, path=self.settings, confirmed=True,
                if_revision=restored_plan["revision"])
            atomic.assert_called_once()
        self.assertEqual(result, original)
        self.assertTrue(result["music"]["mute"],
                        "A previously muted selected input stays muted")
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.assertEqual(mixer_control.show(path=self.settings), original)

    def test_restore_isolation_cli_requires_exact_reviewed_generation(self):
        mixer_control.change({
            "master": 31, "music": {"mute": False},
            "laptop": {"mute": True}, "tablet": {"mute": False},
        }, path=self.settings, confirmed=True)
        iso = mixer_control.preview_change(
            mixer_control.isolate_input_patch("music"), path=self.settings)
        mixer_control.change(
            mixer_control.isolate_input_patch("music"),
            path=self.settings, confirmed=True,
            if_revision=iso["revision"])
        original_bytes = self.settings.read_bytes()
        baseline = iso["comparison_baseline"]
        real_preview = mixer_control.preview_restore_isolation
        real_restore = mixer_control.restore_isolation
        with (mock.patch(
                "audiohub.mixer_control.preview_restore_isolation",
                side_effect=lambda slot, token, **kw:
                real_preview(slot, token, path=kw.get("path", self.settings))) as preview,
              mock.patch("audiohub.mixer_control.restore_isolation",
                         side_effect=lambda slot, token, **kw:
                         real_restore(slot, token, path=self.settings, **kw)) as restore):
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main(["--preview", "restore-isolation",
                                    "music", baseline])
            planned = json.loads(stdout.getvalue().splitlines()[0])
            self.assertEqual(planned["would_change"], ["tablet.mute"])
            self.assertEqual(self.settings.read_bytes(), original_bytes)
            preview.assert_called_once_with("music", baseline)
            restore.assert_not_called()
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main([
                    "--confirm-local-mixer-change",
                    "--if-preview-revision", planned["revision"],
                    "restore-isolation", "music", baseline,
                ])
            result = json.loads(stdout.getvalue().splitlines()[0])
            self.assertFalse(result["music"]["mute"])
            self.assertTrue(result["laptop"]["mute"])
            self.assertFalse(result["tablet"]["mute"])
            restore.assert_called_once_with(
                "music", baseline, confirmed=True,
                if_revision=planned["revision"])

    def test_restore_isolation_fails_closed_on_intervening_master_eq_or_mute(self):
        original = mixer_control.change({
            "master": 30,
            "music": {"mute": False, "bass": 1},
            "laptop": {"volume": 15, "mute": False},
            "tablet": {"mute": False, "treble": 2},
        }, path=self.settings, confirmed=True)
        start = mixer_control.preview_change(
            mixer_control.isolate_input_patch("music"), path=self.settings)
        baseline = start["comparison_baseline"]
        mixer_control.change(
            mixer_control.isolate_input_patch("music"),
            path=self.settings, confirmed=True,
            if_revision=start["revision"])
        preview = mixer_control.preview_restore_isolation(
            "music", baseline, path=self.settings)
        # Even a no-op-looking ABA replacement is another settings generation.
        mixer_control.change({"master": 55}, path=self.settings, confirmed=True)
        mixer_control.change({"master": 30}, path=self.settings, confirmed=True)
        raw = self.settings.read_bytes()
        with self.assertRaises(mixer_control.StaleMixerPreview):
            mixer_control.restore_isolation(
                "music", baseline, path=self.settings, confirmed=True,
                if_revision=preview["revision"])
        self.assertEqual(self.settings.read_bytes(), raw)
        for foreign in (
                {"master": 21},
                {"music": {"bass": 8}},
                {"music": {"mute": True}},
                {"laptop": {"volume": 88}},
                {"laptop": {"mute": False}},
        ):
            with self.subTest(foreign=foreign):
                mixer_control.change(foreign, path=self.settings, confirmed=True)
                before = self.settings.read_bytes()
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.preview_restore_isolation(
                        "music", baseline, path=self.settings)
                self.assertEqual(self.settings.read_bytes(), before)
                # Restore the original isolated settings by an independent
                # test-only writer; never done automatically by the product.
                mixer_control.change(original, path=self.settings, confirmed=True)
                mixer_control.change(
                    mixer_control.isolate_input_patch("music"),
                    path=self.settings, confirmed=True)

    def test_restore_isolation_invalid_token_or_flags_never_touch_settings(self):
        initial = mixer_control.preview_change(
            mixer_control.isolate_input_patch("music"), path=self.settings)
        baseline = initial["comparison_baseline"]
        for args in (
            ["restore-isolation", "music", baseline],
            ["--confirm-local-mixer-change", "restore-isolation", "music", baseline],
            ["--if-preview-revision", "v1-" + "a"*64,
             "restore-isolation", "music", baseline],
            ["--preview", "--confirm-local-mixer-change",
             "restore-isolation", "music", baseline],
            ["--preview", "--if-preview-revision", "v1-" + "a"*64,
             "restore-isolation", "music", baseline],
            ["--preview", "--wait-for-supervisor",
             "restore-isolation", "music", baseline],
            ["--preview", "--confirm-local-profile-save",
             "restore-isolation", "music", baseline],
            ["--preview", "--compare-baseline", baseline,
             "restore-isolation", "music", baseline],
            ["--preview", "restore-isolation", "unknown", baseline],
            ["--preview", "restore-isolation", "music", "b1-$PRIVATE_MAC"],
            ["--preview", "restore-isolation", "music", baseline, "tablet"],
        ):
            with (self.subTest(args=args),
                  mock.patch("audiohub.mixer_control.change") as writer,
                  redirect_stdout(StringIO()) as stdout,
                  redirect_stderr(StringIO()) as stderr):
                with self.assertRaises(SystemExit) as invalid:
                    mixer_control.main(args)
                self.assertEqual(invalid.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn("PRIVATE_MAC", stderr.getvalue())
                writer.assert_not_called()
            self.assertFalse(self.settings.parent.exists())
        for token in (True, 5, "", "b1-X", "b1-../SECRET"):
            with self.subTest(token=repr(token)), self.assertRaises(
                    mixer_control.MixerControlUnavailable):
                mixer_control.preview_restore_isolation(
                    "music", token, path=self.settings)
            self.assertFalse(self.settings.parent.exists())

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
                         return_value={
                             "mode": "preview-only",
                             "before": requested_mix_controls(defaults()),
                             "after": requested_mix_controls(
                                 mixer_control.patch_settings(defaults(), patch)),
                         }) as preview,
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

    def test_copy_profile_preview_is_read_only_and_has_private_catalog_revision(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile("original", 27, 38, 49, 12,
                                          path=profile_path, confirmed=True)
        catalog_before = profile_path.read_bytes()
        with mock.patch("audiohub.mixer_control.atomic_json") as write:
            plan = mixer_control.preview_profile_copy(
                "original", "alternate", path=profile_path)
            write.assert_not_called()
        self.assertEqual(plan["mode"], "profile-copy-preview")
        self.assertEqual(plan["volumes"], {
            "master": 27, "music": 38, "laptop": 49, "tablet": 12})
        self.assertRegex(plan["profile_revision"], r"^p1-[0-9a-f]{64}$")
        self.assertFalse(plan["profile_written"])
        self.assertTrue(plan["source_unchanged"])
        self.assertFalse(plan["mixer_settings_written"])
        self.assertFalse(plan["audible_playback_verified"])
        self.assertEqual(profile_path.read_bytes(), catalog_before)
        self.assertFalse(self.settings.exists())

    def test_copy_profile_locked_save_preserves_source_and_active_mixer(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile("first", 25, 35, 45, 15,
                                          path=profile_path, confirmed=True)
        existing = mixer_control.change({
            "master": 72,
            "music": {"volume": 62, "mute": True, "bass": 6},
            "laptop": {"mute": True, "mid": -3},
            "tablet": {"treble": 5}}, path=self.settings, confirmed=True)
        mixer_bytes = self.settings.read_bytes()
        plan = mixer_control.preview_profile_copy(
            "first", "second", path=profile_path)
        with mock.patch("audiohub.mixer_control.atomic_json",
                        wraps=mixer_control.atomic_json) as write:
            report = mixer_control.copy_volume_profile(
                "first", "second", path=profile_path,
                if_profile_revision=plan["profile_revision"], confirmed=True)
            write.assert_called_once()
        self.assertEqual(report["profile_copied_from"], "first")
        self.assertEqual(report["profile_saved"], "second")
        self.assertFalse(report["mixer_settings_written"])
        self.assertTrue(report["source_unchanged"])
        self.assertEqual(report["volumes"], plan["volumes"])
        self.assertEqual(stat.S_IMODE(profile_path.stat().st_mode), 0o600)
        catalog = mixer_control.list_volume_profiles(path=profile_path)["profiles"]
        self.assertEqual(catalog["first"], plan["volumes"])
        self.assertEqual(catalog["second"], plan["volumes"])
        self.assertEqual(self.settings.read_bytes(), mixer_bytes)
        self.assertEqual(mixer_control.show(path=self.settings), existing)

    def test_copy_profile_stale_on_any_catalog_change_and_aba_generation(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile("first", 25, 35, 45, 15,
                                          path=profile_path, confirmed=True)
        old = mixer_control.preview_profile_copy(
            "first", "second", path=profile_path)
        mixer_control.save_volume_profile("someone-else", 30, 30, 30, 30,
                                          path=profile_path, confirmed=True)
        saved_bytes = profile_path.read_bytes()
        with mock.patch("audiohub.mixer_control.atomic_json") as write:
            with self.assertRaises(mixer_control.StaleProfilePreview):
                mixer_control.copy_volume_profile(
                    "first", "second", path=profile_path,
                    if_profile_revision=old["profile_revision"], confirmed=True)
            write.assert_not_called()
        self.assertEqual(profile_path.read_bytes(), saved_bytes)
        # Even a writer that replaces the same canonical file contents
        # advances its generation and invalidates the earlier plan.
        new = mixer_control.preview_profile_copy(
            "first", "second", path=profile_path)
        catalog = mixer_control.list_volume_profiles(path=profile_path)
        mixer_control.atomic_json(profile_path, catalog)
        with self.assertRaises(mixer_control.StaleProfilePreview):
            mixer_control.copy_volume_profile(
                "first", "second", path=profile_path,
                if_profile_revision=new["profile_revision"], confirmed=True)
        self.assertNotIn("second", mixer_control.list_volume_profiles(
            path=profile_path)["profiles"])

    def test_copy_profile_invalid_source_or_destination_and_full_cap_refused(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        self.assertEqual(mixer_control.list_volume_profiles(
            path=profile_path)["profiles"], {})
        for source, destination in (("missing", "new"), ("same", "same"),
                                     ("../path", "other"), ("missing", "also")):
            with self.subTest(source=source, destination=destination):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.preview_profile_copy(
                        source, destination, path=profile_path)
        self.assertFalse(profile_path.parent.exists())
        mixer_control.save_volume_profile("first", 25, 25, 25, 25,
                                          path=profile_path, confirmed=True)
        mixer_control.save_volume_profile("second", 40, 40, 40, 40,
                                          path=profile_path, confirmed=True)
        for pair in (("missing", "new"), ("first", "first"),
                     ("first", "second"), ("first", "../path")):
            with self.subTest(pair=pair):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.preview_profile_copy(*pair, path=profile_path)
        for index in range(6):
            mixer_control.save_volume_profile(
                "rest-" + str(index), 20, 20, 20, 20,
                path=profile_path, confirmed=True)
        before = profile_path.read_bytes()
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.preview_profile_copy("first", "last", path=profile_path)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.copy_volume_profile(
                "first", "last", path=profile_path,
                if_profile_revision="p1-" + "a" * 64, confirmed=True)
        self.assertEqual(profile_path.read_bytes(), before)

    def test_copy_profile_refuses_invalid_revision_or_missing_confirmation(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        for token, confirmed in ((None, True), ("p1-", True),
                                 ("p1-" + "A" * 64, True),
                                 ("p1-" + "a" * 63, True),
                                 ("v1-" + "a" * 64, True),
                                 ("p1-" + "a" * 64, False)):
            with self.subTest(token=repr(token), confirmed=confirmed):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.copy_volume_profile(
                        "source", "new", path=profile_path,
                        if_profile_revision=token, confirmed=confirmed)
        self.assertFalse(profile_path.parent.exists())

    def test_copy_profile_invalid_private_state_does_not_overwrite_any_file(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        profile_path.parent.mkdir(mode=0o700)
        target = self.root / "sensitive-data.json"
        target.write_text("PRIVATE-DATA")
        profile_path.symlink_to(target)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.preview_profile_copy("first", "second",
                                               path=profile_path)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.copy_volume_profile(
                "first", "second", path=profile_path,
                if_profile_revision="p1-" + "a" * 64, confirmed=True)
        self.assertEqual(target.read_text(), "PRIVATE-DATA")
        profile_path.unlink()
        for raw in (b'{', b'{"version":1,"profiles":{},"unexpected":"SECRET"}',
                    b'{"version":1,"profiles":{},"profiles":{}}'):
            profile_path.write_bytes(raw)
            profile_path.chmod(0o600)
            before = profile_path.read_bytes()
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.preview_profile_copy("first", "second",
                                                   path=profile_path)
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.copy_volume_profile(
                    "first", "second", path=profile_path,
                    if_profile_revision="p1-" + "a" * 64, confirmed=True)
            self.assertEqual(profile_path.read_bytes(), before)

    def test_copy_profile_cli_preview_then_separate_explicit_save(self):
        plan = {
            "mode": "profile-copy-preview",
            "profile_revision": "p1-" + "a" * 64,
            "source": "original", "destination": "alternate",
            "volumes": {"master": 20, "music": 35, "laptop": 25, "tablet": 0},
            "profile_written": False, "source_unchanged": True,
            "mixer_settings_written": False,
            "audible_playback_verified": False}
        result = {"profile_copied_from": "original", "profile_saved": "alternate",
                  "volumes": plan["volumes"], "mixer_settings_written": False,
                  "source_unchanged": True, "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.preview_profile_copy",
                         return_value=plan) as preview,
              mock.patch("audiohub.mixer_control.copy_volume_profile",
                         return_value=result) as copy,
              mock.patch("audiohub.mixer_control.change") as apply):
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main(["--preview", "copy-profile",
                                    "original", "alternate"])
            self.assertIn('"profile_written": false', stdout.getvalue())
            preview.assert_called_once_with("original", "alternate")
            copy.assert_not_called()
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main(["--confirm-local-profile-save",
                                    "--if-profile-revision", plan["profile_revision"],
                                    "copy-profile", "original", "alternate"])
            copy.assert_called_once_with(
                "original", "alternate", confirmed=True,
                if_profile_revision=plan["profile_revision"])
            apply.assert_not_called()
            self.assertIn('"source_unchanged": true', stdout.getvalue())

    def test_copy_profile_cli_stale_returns_only_fresh_read_only_copy_plan(self):
        plan = {
            "mode": "profile-copy-preview",
            "profile_revision": "p1-" + "b" * 64,
            "source": "original", "destination": "alternate",
            "volumes": {"master": 20, "music": 35, "laptop": 25, "tablet": 0},
            "profile_written": False, "source_unchanged": True,
            "mixer_settings_written": False,
            "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.copy_volume_profile",
                         side_effect=mixer_control.StaleProfilePreview("PRIVATE")) as copy,
              mock.patch("audiohub.mixer_control.preview_profile_copy",
                         return_value=plan) as preview,
              mock.patch("audiohub.mixer_control.atomic_json") as write):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main(["--confirm-local-profile-save",
                                        "--if-profile-revision", "p1-" + "a" * 64,
                                        "copy-profile", "original", "alternate"])
            self.assertEqual(failed.exception.code, 4)
            copy.assert_called_once()
            preview.assert_called_once_with("original", "alternate")
            write.assert_not_called()
        reply = json.loads(out.getvalue())
        self.assertEqual(reply["status"], "profile-copy-stale")
        self.assertFalse(reply["profile_written"])
        self.assertEqual(reply["fresh_preview"], plan)
        self.assertNotIn("PRIVATE", err.getvalue())

    def test_copy_profile_cli_missing_or_mixed_consent_refused_without_writing(self):
        bad = (
            ["copy-profile", "first", "second"],
            ["--confirm-local-profile-save", "copy-profile", "first", "second"],
            ["--if-profile-revision", "p1-" + "a" * 64,
             "copy-profile", "first", "second"],
            ["--preview", "--confirm-local-profile-save",
             "copy-profile", "first", "second"],
            ["--preview", "--if-profile-revision", "p1-" + "a" * 64,
             "copy-profile", "first", "second"],
            ["--confirm-local-profile-save", "--if-preview-revision",
             "v1-" + "a" * 64, "copy-profile", "first", "second"],
            ["--confirm-local-profile-save", "--if-profile-revision",
             "p1-" + "a" * 64, "--wait-for-supervisor",
             "copy-profile", "first", "second"],
            ["--if-profile-revision", "p1-" + "a" * 64, "list-profiles"],
            ["--if-profile-revision", "p1-" + "a" * 64,
             "save-profile", "first", "20", "30", "40", "50"],
        )
        for argv in bad:
            with self.subTest(argv=argv):
                with (mock.patch("audiohub.mixer_control.copy_volume_profile") as copy,
                      mock.patch("audiohub.mixer_control.atomic_json") as write):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            mixer_control.main(argv)
                    self.assertEqual(failed.exception.code, 2)
                    copy.assert_not_called()
                    write.assert_not_called()

    def test_copy_profile_cli_stale_refresh_failure_sanitizes_private_details(self):
        with (mock.patch("audiohub.mixer_control.copy_volume_profile",
                         side_effect=mixer_control.StaleProfilePreview("PRIVATE-PATH")),
              mock.patch("audiohub.mixer_control.preview_profile_copy",
                         side_effect=mixer_control.MixerControlUnavailable("PRIVATE-VALUES"))):
            with redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as error:
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main([
                        "--confirm-local-profile-save",
                        "--if-profile-revision", "p1-" + "a" * 64,
                        "copy-profile", "first", "second"])
            self.assertEqual(failed.exception.code, 4)
            self.assertEqual(output.getvalue(), "")
            self.assertNotIn("PRIVATE-VALUES", error.getvalue())
            self.assertNotIn("PRIVATE-PATH", error.getvalue())
            self.assertIn("Fresh preview unavailable", error.getvalue())

    def test_compare_profiles_reports_only_changed_levels_and_signed_deltas(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "quietroom", 25, 60, 40, 0, path=profile_path, confirmed=True)
        mixer_control.save_volume_profile(
            "movie", 45, 20, 40, 80, path=profile_path, confirmed=True)
        profile_bytes = profile_path.read_bytes()
        current = mixer_control.change({
            "master": 71, "music": {"mute": True, "bass": -4},
            "laptop": {"mute": True, "mid": 5}, "tablet": {"treble": 9},
        }, path=self.settings, confirmed=True)
        mixer_bytes = self.settings.read_bytes()
        with mock.patch("audiohub.mixer_control.atomic_json") as write:
            result = mixer_control.compare_volume_profiles(
                "quietroom", "movie", path=profile_path)
            write.assert_not_called()
        self.assertEqual(result["mode"], "profile-compare-only")
        self.assertEqual(result["left"], "quietroom")
        self.assertEqual(result["right"], "movie")
        self.assertEqual(result["left_volumes"], {
            "master": 25, "music": 60, "laptop": 40, "tablet": 0})
        self.assertEqual(result["right_volumes"], {
            "master": 45, "music": 20, "laptop": 40, "tablet": 80})
        self.assertEqual(result["differences"], [
            {"control": "master", "left": 25, "right": 45, "delta": 20},
            {"control": "music", "left": 60, "right": 20, "delta": -40},
            {"control": "tablet", "left": 0, "right": 80, "delta": 80},
        ])
        self.assertFalse(result["same_levels"])
        self.assertRegex(result["profile_revision"], r"^p1-[0-9a-f]{64}$")
        self.assertFalse(result["profile_written"])
        self.assertFalse(result["mixer_settings_written"])
        self.assertFalse(result["audible_playback_verified"])
        self.assertEqual(profile_path.read_bytes(), profile_bytes)
        self.assertEqual(self.settings.read_bytes(), mixer_bytes)
        self.assertEqual(mixer_control.show(path=self.settings), current)

    def test_compare_profiles_equal_levels_distinct_names_reports_empty_changes(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "first", 20, 30, 40, 50, path=profile_path, confirmed=True)
        mixer_control.save_volume_profile(
            "second", 20, 30, 40, 50, path=profile_path, confirmed=True)
        result = mixer_control.compare_volume_profiles(
            "first", "second", path=profile_path)
        self.assertTrue(result["same_levels"])
        self.assertEqual(result["differences"], [])
        self.assertEqual(result["left_volumes"], result["right_volumes"])
        self.assertFalse(self.settings.exists())

    def test_compare_profiles_reverses_signed_deltas_without_modifying_catalog(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "alpha", 10, 20, 30, 40, path=profile_path, confirmed=True)
        mixer_control.save_volume_profile(
            "beta", 60, 70, 80, 90, path=profile_path, confirmed=True)
        before = profile_path.read_bytes()
        forward = mixer_control.compare_volume_profiles(
            "alpha", "beta", path=profile_path)
        reverse = mixer_control.compare_volume_profiles(
            "beta", "alpha", path=profile_path)
        self.assertEqual(forward["profile_revision"], reverse["profile_revision"])
        self.assertEqual([entry["delta"] for entry in forward["differences"]],
                         [50, 50, 50, 50])
        self.assertEqual([entry["delta"] for entry in reverse["differences"]],
                         [-50, -50, -50, -50])
        self.assertEqual(profile_path.read_bytes(), before)

    def test_compare_profiles_missing_catalog_does_not_create_directory_or_lock(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.compare_volume_profiles(
                "first", "second", path=profile_path)
        self.assertFalse(profile_path.parent.exists())

    def test_compare_profiles_rejects_missing_names_and_untrusted_fields(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        for left, right in (("first", "first"), ("../outside", "second"),
                            ("first", "name_unsafe"), ("ü", "second"),
                            ("first", "second")):
            with self.subTest(left=left, right=right):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.compare_volume_profiles(
                        left, right, path=profile_path)
        self.assertFalse(profile_path.parent.exists())
        mixer_control.save_volume_profile(
            "first", 20, 30, 40, 50, path=profile_path, confirmed=True)
        data = profile_path.read_bytes()
        for pair in (("first", "second"), ("second", "first"),
                     ("first", "first")):
            with self.subTest(pair=pair):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.compare_volume_profiles(
                        *pair, path=profile_path)
        self.assertEqual(profile_path.read_bytes(), data)

    def test_compare_profiles_corrupt_symlink_and_unprivate_catalog_fail_closed(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        sensitive = self.root / "sensitive-profile.json"
        sensitive.write_text("PRIVATE-SECRET")
        profile_path.parent.mkdir(mode=0o700)
        profile_path.symlink_to(sensitive)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.compare_volume_profiles(
                "first", "second", path=profile_path)
        self.assertEqual(sensitive.read_text(), "PRIVATE-SECRET")
        profile_path.unlink()
        for payload in (b"{", b'{"version":1,"profiles":{"first":{}}}',
                        b'{"version":1,"profiles":{},"secret":"PRIVATE"}'):
            profile_path.write_bytes(payload)
            profile_path.chmod(0o600)
            original = profile_path.read_bytes()
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.compare_volume_profiles(
                    "first", "second", path=profile_path)
            self.assertEqual(profile_path.read_bytes(), original)
        profile_path.write_text('{"version":1,"profiles":{}}')
        profile_path.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.compare_volume_profiles(
                "first", "second", path=profile_path)

    def test_compare_profiles_detects_catalog_generation_change_during_read(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "first", 10, 20, 30, 40, path=profile_path, confirmed=True)
        mixer_control.save_volume_profile(
            "second", 40, 30, 20, 10, path=profile_path, confirmed=True)
        original = mixer_control._profile_catalog
        def replace_during_read(path, dirfd):
            snapshot = original(path, dirfd)
            mixer_control.atomic_json(profile_path, snapshot)
            return snapshot
        with mock.patch("audiohub.mixer_control._profile_catalog",
                        side_effect=replace_during_read) as catalog:
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.compare_volume_profiles(
                    "first", "second", path=profile_path)
            catalog.assert_called_once()
        self.assertFalse(self.settings.exists())

    def test_compare_profiles_cli_is_read_only_and_displays_signed_changes(self):
        result = {
            "mode": "profile-compare-only",
            "left": "first", "right": "second",
            "left_volumes": {"master": 10, "music": 20, "laptop": 30, "tablet": 40},
            "right_volumes": {"master": 10, "music": 20, "laptop": 50, "tablet": 40},
            "differences": [
                {"control": "laptop", "left": 30, "right": 50, "delta": 20}],
            "same_levels": False, "profile_revision": "p1-" + "a" * 64,
            "profile_written": False, "mixer_settings_written": False,
            "audible_playback_verified": False}
        with (mock.patch("audiohub.mixer_control.compare_volume_profiles",
                         return_value=result) as compare,
              mock.patch("audiohub.mixer_control.atomic_json") as writer,
              mock.patch("audiohub.mixer_control.change") as mixer):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["compare-profiles", "first", "second"])
            compare.assert_called_once_with("first", "second")
            writer.assert_not_called()
            mixer.assert_not_called()
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["differences"][0]["delta"], 20)
        self.assertFalse(payload["mixer_settings_written"])

    def test_compare_profiles_cli_rejects_every_write_or_preview_switch(self):
        flags = (
            ["--preview"],
            ["--confirm-local-mixer-change"],
            ["--confirm-local-profile-save"],
            ["--wait-for-supervisor"],
            ["--if-preview-revision", "v1-" + "a" * 64],
            ["--if-profile-revision", "p1-" + "a" * 64],
            ["--compare-baseline", "b1-unsafe"],
        )
        for prefix in flags:
            with self.subTest(prefix=prefix):
                with (mock.patch("audiohub.mixer_control.compare_volume_profiles") as compare,
                      mock.patch("audiohub.mixer_control.atomic_json") as writer,
                      mock.patch("audiohub.mixer_control.change") as mixer):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as fail:
                            mixer_control.main(prefix + [
                                "compare-profiles", "first", "second"])
                    self.assertEqual(fail.exception.code, 2)
                    compare.assert_not_called()
                    writer.assert_not_called()
                    mixer.assert_not_called()

    def test_compare_profiles_cli_sanitizes_private_read_failures(self):
        with mock.patch("audiohub.mixer_control.compare_volume_profiles",
                        side_effect=mixer_control.MixerControlUnavailable(
                            "PRIVATE-UNTRUSTED-FILENAME")):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
                with self.assertRaises(SystemExit) as fail:
                    mixer_control.main(["compare-profiles", "first", "second"])
        self.assertEqual(fail.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("not changed or unavailable", err.getvalue())
        self.assertNotIn("PRIVATE-UNTRUSTED-FILENAME", err.getvalue())

    def test_compare_profile_to_current_displays_signed_level_deltas_without_writes(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "cinema", 25, 60, 40, 0, path=path, confirmed=True)
        mixer_control.change({
            "master": 45, "music": {"volume": 20, "mute": True, "bass": 6},
            "laptop": {"volume": 40, "mute": True, "treble": 3},
            "tablet": {"volume": 80, "mid": -4},
        }, path=self.settings, confirmed=True)
        profile_bytes, mixer_bytes = path.read_bytes(), self.settings.read_bytes()
        with mock.patch("audiohub.mixer_control.atomic_json") as write:
            result = mixer_control.compare_profile_to_current(
                "cinema", path=path, settings_path=self.settings)
            write.assert_not_called()
        self.assertEqual(result["mode"], "profile-vs-current-only")
        self.assertEqual(result["profile"], "cinema")
        self.assertEqual(result["saved_volumes"], {
            "master": 25, "music": 60, "laptop": 40, "tablet": 0})
        self.assertEqual(result["current_volumes"], {
            "master": 45, "music": 20, "laptop": 40, "tablet": 80})
        self.assertEqual(result["differences"], [
            {"control": "master", "saved": 25, "current": 45, "delta": 20},
            {"control": "music", "saved": 60, "current": 20, "delta": -40},
            {"control": "tablet", "saved": 0, "current": 80, "delta": 80},
        ])
        self.assertFalse(result["same_levels"])
        self.assertRegex(result["profile_revision"], r"^p1-[0-9a-f]{64}$")
        self.assertRegex(result["mixer_revision"], r"^v1-[0-9a-f]{64}$")
        self.assertFalse(result["profile_written"])
        self.assertFalse(result["mixer_settings_written"])
        self.assertFalse(result["audible_playback_verified"])
        self.assertEqual(path.read_bytes(), profile_bytes)
        self.assertEqual(self.settings.read_bytes(), mixer_bytes)

    def test_compare_profile_to_current_equal_levels_show_no_differences(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "defaultmix", 70, 65, 50, 50, path=path, confirmed=True)
        result = mixer_control.compare_profile_to_current(
            "defaultmix", path=path, settings_path=self.settings)
        self.assertEqual(result["differences"], [])
        self.assertTrue(result["same_levels"])
        self.assertFalse(self.settings.exists())

    def test_compare_profile_to_current_defaults_are_requested_not_actual_audio(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "quiet", 15, 25, 25, 25, path=path, confirmed=True)
        result = mixer_control.compare_profile_to_current(
            "quiet", path=path, settings_path=self.settings)
        self.assertEqual(result["current_volumes"], {
            "master": 70, "music": 65, "laptop": 50, "tablet": 50})
        self.assertEqual([d["delta"] for d in result["differences"]],
                         [55, 40, 25, 25])
        self.assertFalse(result["audible_playback_verified"])
        self.assertFalse(self.settings.exists())

    def test_compare_profile_to_current_absent_catalog_never_creates_config(self):
        path = self.settings.with_name("volume-profiles.json")
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.compare_profile_to_current(
                "missing", path=path, settings_path=self.settings)
        self.assertFalse(path.parent.exists())

    def test_compare_profile_to_current_missing_invalid_name_and_insecure_catalog(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "known", 20, 30, 40, 50, path=path, confirmed=True)
        before = path.read_bytes()
        for name in ("missing", "../private", "UPPER", "a_b", ""):
            with self.subTest(name=name):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.compare_profile_to_current(
                        name, path=path, settings_path=self.settings)
        self.assertEqual(path.read_bytes(), before)
        path.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.compare_profile_to_current(
                "known", path=path, settings_path=self.settings)

    def test_compare_profile_to_current_rejects_settings_replacement_during_read(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "cinema", 20, 30, 40, 50, path=path, confirmed=True)
        mixer_control.change({"master": 21}, path=self.settings, confirmed=True)
        original = mixer_control._state_with_revision
        def replace_during_read(p, dirfd):
            snapshot = original(p, dirfd)
            if p.name == "settings.json":
                mixer_control.atomic_json(self.settings,
                                          mixer_control.show(path=self.settings))
            return snapshot
        with mock.patch("audiohub.mixer_control._state_with_revision",
                        side_effect=replace_during_read) as read:
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.compare_profile_to_current(
                    "cinema", path=path, settings_path=self.settings)
            read.assert_called_once()
        self.assertEqual(mixer_control.list_volume_profiles(path=path)[
            "profiles"]["cinema"]["master"], 20)

    def test_compare_profile_to_current_rejects_catalog_replacement_during_read(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "cinema", 20, 30, 40, 50, path=path, confirmed=True)
        original = mixer_control._state_with_revision
        def replace_catalog_during_read(p, dirfd):
            snapshot = original(p, dirfd)
            if p.name == "settings.json":
                catalog = mixer_control.list_volume_profiles(path=path)
                mixer_control.atomic_json(path, catalog)
            return snapshot
        with mock.patch("audiohub.mixer_control._state_with_revision",
                        side_effect=replace_catalog_during_read):
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.compare_profile_to_current(
                    "cinema", path=path, settings_path=self.settings)
        self.assertFalse(self.settings.exists())

    def test_compare_profile_to_current_rejects_unrelated_config_paths(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "cinema", 20, 30, 40, 50, path=path, confirmed=True)
        for target, settings in (
            (path, self.root / "other" / "settings.json"),
            (self.settings, self.settings),
            (path, path),
        ):
            with self.subTest(target=str(target), settings=str(settings)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.compare_profile_to_current(
                        "cinema", path=target, settings_path=settings)

    def test_compare_profile_to_current_cli_is_read_only_and_valid(self):
        report = {
            "mode": "profile-vs-current-only", "profile": "cinema",
            "saved_volumes": {"master": 20, "music": 30, "laptop": 40, "tablet": 50},
            "current_volumes": {"master": 40, "music": 30, "laptop": 40, "tablet": 50},
            "differences": [
                {"control": "master", "saved": 20, "current": 40, "delta": 20}],
            "same_levels": False, "profile_revision": "p1-" + "a" * 64,
            "mixer_revision": "v1-" + "b" * 64,
            "profile_written": False, "mixer_settings_written": False,
            "audible_playback_verified": False,
        }
        with (mock.patch("audiohub.mixer_control.compare_profile_to_current",
                         return_value=report) as compare,
              mock.patch("audiohub.mixer_control.atomic_json") as write,
              mock.patch("audiohub.mixer_control.change") as change):
            with redirect_stdout(StringIO()) as stdout:
                mixer_control.main(["compare-profile-current", "cinema"])
            compare.assert_called_once_with("cinema")
            write.assert_not_called()
            change.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["differences"],
                         report["differences"])

    def test_compare_profile_to_current_cli_rejects_every_mutation_switch(self):
        for prefix in (
            ["--preview"], ["--confirm-local-mixer-change"],
            ["--confirm-local-profile-save"], ["--wait-for-supervisor"],
            ["--if-preview-revision", "v1-" + "a" * 64],
            ["--if-profile-revision", "p1-" + "a" * 64],
            ["--compare-baseline", "b1-no"],
        ):
            with self.subTest(flags=prefix):
                with (mock.patch("audiohub.mixer_control.compare_profile_to_current") as compare,
                      mock.patch("audiohub.mixer_control.atomic_json") as write,
                      mock.patch("audiohub.mixer_control.change") as change):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as fail:
                            mixer_control.main(prefix + [
                                "compare-profile-current", "cinema"])
                    self.assertEqual(fail.exception.code, 2)
                    compare.assert_not_called()
                    write.assert_not_called()
                    change.assert_not_called()

    def test_profile_choice_impact_explains_requested_volume_changes_and_mutes(self):
        prior = defaults()
        prior["master"] = 70
        prior["music"].update(volume=60, mute=True, bass=8)
        prior["laptop"].update(volume=40, mute=False, mid=-6)
        prior["tablet"].update(volume=10, mute=True, treble=7)
        mixer_control.change(prior, path=self.settings, confirmed=True)
        patch = mixer_control._profile_patch({
            "master": 25, "music": 35, "laptop": 50, "tablet": 10})
        plan = mixer_control.preview_change(patch, path=self.settings)
        impact = mixer_control._profile_selection_impact(plan, "cinema")
        self.assertEqual(impact["profile"], "cinema")
        self.assertEqual(impact["master"],
                         {"previous": 70, "requested": 25, "delta": -45})
        self.assertEqual([row["delta"] for row in impact["sources"]],
                         [-25, 10, 0])
        self.assertEqual(impact["muted_sources_remaining_muted"],
                         ["music", "tablet"])
        self.assertEqual([row["volume_change_while_muted"]
                          for row in impact["sources"]], [True, False, False])
        self.assertEqual([row["stays_muted"] for row in impact["sources"]],
                         [True, False, True])
        self.assertTrue(impact["changed"])
        self.assertTrue(impact["mute_states_preserved"])
        self.assertTrue(impact["stored_eq_preserved"])
        self.assertTrue(impact["separate_confirmation_required"])
        self.assertTrue(impact["requested_levels_only"])
        self.assertFalse(impact["audible_playback_verified"])
        self.assertEqual(mixer_control.show(path=self.settings), prior)

    def test_profile_choice_impact_unchanged_levels_explain_still_muted(self):
        current = defaults()
        current["music"]["mute"] = True
        mixer_control.change({"music": {"mute": True}},
                             path=self.settings, confirmed=True)
        levels = {"master": current["master"],
                  **{slot: current[slot]["volume"] for slot in
                     ("music", "laptop", "tablet")}}
        plan = mixer_control.preview_change(mixer_control._profile_patch(levels),
                                            path=self.settings)
        impact = mixer_control._profile_selection_impact(plan, "same")
        self.assertFalse(impact["changed"])
        self.assertEqual(impact["muted_sources_remaining_muted"], ["music"])
        self.assertEqual([row["delta"] for row in impact["sources"]], [0, 0, 0])
        self.assertFalse(impact["sources"][0]["volume_change_while_muted"])
        self.assertFalse(plan["settings_written"])

    def test_profile_choice_impact_rejects_any_unmute_in_preview(self):
        plan = mixer_control.preview_change({"music": {"mute": False}},
                                            path=self.settings)
        bad = dict(plan)
        bad["after"] = {**plan["after"], "music": {
            "volume": plan["after"]["music"]["volume"], "mute": True}}
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control._profile_selection_impact(bad, "cinema")

    def test_profile_choice_cli_preview_renders_impact_without_writing(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "cinema", 30, 25, 45, 15, path=profile_path, confirmed=True)
        mixer_control.change({"music": {"mute": True}, "tablet": {"mute": True}},
                             path=self.settings, confirmed=True)
        original_settings = self.settings.read_bytes()
        original_profiles = profile_path.read_bytes()
        real_preview = mixer_control.preview_change
        real_lookup = mixer_control.saved_profile_patch
        def preview_local(patch, *, baseline=None):
            return real_preview(patch, path=self.settings, baseline=baseline)
        def lookup_local(name):
            return real_lookup(name, path=profile_path)
        with (mock.patch("audiohub.mixer_control.saved_profile_patch",
                         side_effect=lookup_local),
              mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=preview_local) as preview,
              mock.patch("audiohub.mixer_control.atomic_json") as write,
              mock.patch("audiohub.mixer_control.change") as change):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["--preview", "profile", "cinema"])
            preview.assert_called_once()
            write.assert_not_called()
            change.assert_not_called()
        result = json.loads(out.getvalue().splitlines()[0])
        impact = result["profile_impact"]
        self.assertEqual(impact["profile"], "cinema")
        self.assertEqual(impact["muted_sources_remaining_muted"],
                         ["music", "tablet"])
        self.assertTrue(impact["sources"][0]["volume_change_while_muted"])
        self.assertTrue(impact["separate_confirmation_required"])
        self.assertFalse(result["settings_written"])
        self.assertEqual(self.settings.read_bytes(), original_settings)
        self.assertEqual(profile_path.read_bytes(), original_profiles)

    def test_profile_choice_stale_guard_refreshes_impact_read_only(self):
        profile_path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "cinema", 20, 30, 40, 50, path=profile_path, confirmed=True)
        patch = mixer_control.saved_profile_patch("cinema", path=profile_path)
        old = mixer_control.preview_change(patch, path=self.settings)
        mixer_control.change({"music": {"mute": True, "volume": 12}},
                             path=self.settings, confirmed=True)
        settings_before = self.settings.read_bytes()
        profile_before = profile_path.read_bytes()
        real_change = mixer_control.change
        real_preview = mixer_control.preview_change
        def changed(patch, *, confirmed=False, if_revision=None):
            return real_change(patch, path=self.settings, confirmed=confirmed,
                               if_revision=if_revision)
        def preview_local(patch, *, baseline=None):
            return real_preview(patch, path=self.settings, baseline=baseline)
        with (mock.patch("audiohub.mixer_control.saved_profile_patch",
                         return_value=patch),
              mock.patch("audiohub.mixer_control.change", side_effect=changed) as save,
              mock.patch("audiohub.mixer_control.preview_change",
                         side_effect=preview_local),
              mock.patch("audiohub.mixer_control.atomic_json") as write):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as failed:
                    mixer_control.main([
                        "--confirm-local-mixer-change", "--if-preview-revision",
                        old["revision"], "profile", "cinema"])
            self.assertEqual(failed.exception.code, 4)
            save.assert_called_once()
            write.assert_not_called()
        payload = json.loads(out.getvalue())
        impact = payload["fresh_preview"]["profile_impact"]
        self.assertTrue(impact["sources"][0]["stays_muted"])
        self.assertTrue(impact["sources"][0]["volume_change_while_muted"])
        self.assertTrue(impact["separate_confirmation_required"])
        self.assertFalse(payload["settings_written"])
        self.assertEqual(self.settings.read_bytes(), settings_before)
        self.assertEqual(profile_path.read_bytes(), profile_before)

    def test_profile_choice_impact_is_not_attached_to_builtin_presets(self):
        plan = mixer_control.preview_change(mixer_control.preset_patch("quiet"),
                                            path=self.settings)
        self.assertNotIn("profile_impact", plan)
        with mock.patch("audiohub.mixer_control.preview_change",
                        return_value=plan) as preview:
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["--preview", "preset", "quiet"])
            preview.assert_called_once()
        rendered = json.loads(out.getvalue().splitlines()[0])
        self.assertNotIn("profile_impact", rendered)

    def test_profile_choices_empty_private_directory_is_read_only(self):
        path = self.settings.with_name("volume-profiles.json")
        result = mixer_control.profile_selection_overview(
            path=path, settings_path=self.settings)
        self.assertEqual(result["mode"], "profile-choices-read-only")
        self.assertEqual(result["profile_count"], 0)
        self.assertEqual(result["profiles"], [])
        self.assertEqual(result["profile_limit"], 8)
        self.assertEqual(result["current_requested_volumes"], {
            "master": 70, "music": 65, "laptop": 50, "tablet": 50})
        self.assertIsNone(result["profile_revision"])
        self.assertRegex(result["mixer_revision"], r"^v1-[a-f0-9]{64}$")
        self.assertTrue(result["apply_requires_separate_confirmation"])
        self.assertFalse(result["profile_written"])
        self.assertFalse(result["mixer_settings_written"])
        self.assertFalse(result["audible_playback_verified"])
        self.assertFalse(path.parent.exists())

    def test_profile_choices_read_only_sorted_impacts_and_retained_mutes(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "z-work", 30, 50, 40, 20, path=path, confirmed=True)
        mixer_control.save_volume_profile(
            "a-night", 15, 25, 30, 40, path=path, confirmed=True)
        mixer_control.change({
            "master": 30,
            "music": {"volume": 50, "mute": True, "bass": 6},
            "laptop": {"volume": 60, "mute": False, "mid": -5},
            "tablet": {"volume": 40, "mute": True, "treble": 7},
        }, path=self.settings, confirmed=True)
        before_settings = self.settings.read_bytes()
        before_profiles = path.read_bytes()
        with mock.patch("audiohub.mixer_control.atomic_json") as writes:
            result = mixer_control.profile_selection_overview(
                path=path, settings_path=self.settings)
            writes.assert_not_called()
        self.assertEqual([row["name"] for row in result["profiles"]],
                         ["a-night", "z-work"])
        self.assertEqual(result["profile_count"], 2)
        self.assertEqual(result["current_requested_volumes"], {
            "master": 30, "music": 50, "laptop": 60, "tablet": 40})
        night, work = result["profiles"]
        self.assertEqual(night["requested_volumes"], {
            "master": 15, "music": 25, "laptop": 30, "tablet": 40})
        self.assertEqual(night["deltas_from_current"], {
            "master": -15, "music": -25, "laptop": -30, "tablet": 0})
        self.assertEqual(night["would_change"], ["master", "music", "laptop"])
        self.assertEqual(night["muted_sources_remaining_muted"],
                         ["music", "tablet"])
        self.assertEqual(night["volume_changes_while_muted"], ["music"])
        self.assertFalse(night["already_matches"])
        self.assertEqual(work["deltas_from_current"], {
            "master": 0, "music": 0, "laptop": -20, "tablet": -20})
        self.assertEqual(work["would_change"], ["laptop", "tablet"])
        self.assertEqual(work["volume_changes_while_muted"], ["tablet"])
        self.assertRegex(result["profile_revision"], r"^p1-[a-f0-9]{64}$")
        self.assertRegex(result["mixer_revision"], r"^v1-[a-f0-9]{64}$")
        self.assertEqual(result["preview_selected_with"], "--preview profile NAME")
        self.assertTrue(result["mute_states_preserved"])
        self.assertTrue(result["stored_eq_preserved"])
        self.assertTrue(result["apply_requires_separate_confirmation"])
        self.assertEqual(self.settings.read_bytes(), before_settings)
        self.assertEqual(path.read_bytes(), before_profiles)

    def test_profile_choices_exact_match_can_remain_muted(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "current", 70, 65, 50, 50, path=path, confirmed=True)
        mixer_control.change({"music": {"mute": True}},
                             path=self.settings, confirmed=True)
        result = mixer_control.profile_selection_overview(
            path=path, settings_path=self.settings)
        choice = result["profiles"][0]
        self.assertTrue(choice["already_matches"])
        self.assertEqual(choice["would_change"], [])
        self.assertEqual(choice["muted_sources_remaining_muted"], ["music"])
        self.assertEqual(choice["volume_changes_while_muted"], [])
        self.assertFalse(result["mixer_settings_written"])

    def test_profile_choices_rejects_catalog_generation_replacement_during_read(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "first", 20, 30, 40, 50, path=path, confirmed=True)
        real_read = mixer_control._state_with_revision
        def replace_catalog(settings_path, dirfd):
            result = real_read(settings_path, dirfd)
            snapshot = mixer_control.list_volume_profiles(path=path)
            mixer_control.atomic_json(path, snapshot)
            return result
        with mock.patch("audiohub.mixer_control._state_with_revision",
                        side_effect=replace_catalog) as read:
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.profile_selection_overview(
                    path=path, settings_path=self.settings)
            read.assert_called_once()
        self.assertFalse(self.settings.exists())

    def test_profile_choices_rejects_mixer_generation_replacement_during_read(self):
        path = self.settings.with_name("volume-profiles.json")
        mixer_control.save_volume_profile(
            "first", 20, 30, 40, 50, path=path, confirmed=True)
        mixer_control.change({"master": 29}, path=self.settings, confirmed=True)
        real_read = mixer_control._state_with_revision
        def replace_settings(settings_path, dirfd):
            result = real_read(settings_path, dirfd)
            mixer_control.atomic_json(self.settings,
                                      mixer_control.show(path=self.settings))
            return result
        with mock.patch("audiohub.mixer_control._state_with_revision",
                        side_effect=replace_settings):
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.profile_selection_overview(
                    path=path, settings_path=self.settings)

    def test_profile_choices_rejects_corrupt_symlink_and_unsafe_catalog(self):
        path = self.settings.with_name("volume-profiles.json")
        path.parent.mkdir(mode=0o700)
        private = self.root / "private.txt"
        private.write_text("PRIVATE-DATA")
        path.symlink_to(private)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.profile_selection_overview(
                path=path, settings_path=self.settings)
        self.assertEqual(private.read_text(), "PRIVATE-DATA")
        path.unlink()
        for payload in (b"{", b'{"version":1,"profiles":{"x":{}}}',
                        b'{"version":1,"profiles":{},"secret":"bad"}'):
            path.write_bytes(payload)
            path.chmod(0o600)
            before = path.read_bytes()
            with self.assertRaises(mixer_control.MixerControlUnavailable):
                mixer_control.profile_selection_overview(
                    path=path, settings_path=self.settings)
            self.assertEqual(path.read_bytes(), before)
        path.write_text('{"version":1,"profiles":{}}')
        path.chmod(0o644)
        with self.assertRaises(mixer_control.MixerControlUnavailable):
            mixer_control.profile_selection_overview(
                path=path, settings_path=self.settings)

    def test_profile_choices_refuses_unrelated_directory_or_file_names(self):
        path = self.settings.with_name("volume-profiles.json")
        for catalog, settings_path in (
            (self.settings, self.settings),
            (path, self.root / "other" / "settings.json"),
            (path.with_name("profiles-other.json"), self.settings),
        ):
            with self.subTest(catalog=str(catalog), settings=str(settings_path)):
                with self.assertRaises(mixer_control.MixerControlUnavailable):
                    mixer_control.profile_selection_overview(
                        path=catalog, settings_path=settings_path)
        self.assertFalse(path.parent.exists())

    def test_profile_choices_cli_read_only_and_no_implicit_save(self):
        report = {
            "mode": "profile-choices-read-only", "profiles": [
                {"name": "cinema", "requested_volumes": {
                    "master": 20, "music": 30, "laptop": 40, "tablet": 50}}],
            "profile_count": 1, "profile_limit": 8,
            "profile_written": False, "mixer_settings_written": False,
            "audible_playback_verified": False,
        }
        with (mock.patch("audiohub.mixer_control.profile_selection_overview",
                         return_value=report) as choices,
              mock.patch("audiohub.mixer_control.atomic_json") as write,
              mock.patch("audiohub.mixer_control.change") as change):
            with redirect_stdout(StringIO()) as out:
                mixer_control.main(["profile-choices"])
            choices.assert_called_once_with()
            write.assert_not_called()
            change.assert_not_called()
        self.assertEqual(json.loads(out.getvalue()), report)

    def test_profile_choices_cli_rejects_confirmation_or_write_related_flags(self):
        for prefix in (
            ["--preview"], ["--confirm-local-mixer-change"],
            ["--confirm-local-profile-save"], ["--wait-for-supervisor"],
            ["--if-preview-revision", "v1-" + "a" * 64],
            ["--if-profile-revision", "p1-" + "a" * 64],
            ["--compare-baseline", "b1-no"],
        ):
            with self.subTest(flags=prefix):
                with (mock.patch("audiohub.mixer_control.profile_selection_overview") as choices,
                      mock.patch("audiohub.mixer_control.atomic_json") as write):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failure:
                            mixer_control.main(prefix + ["profile-choices"])
                    self.assertEqual(failure.exception.code, 2)
                    choices.assert_not_called()
                    write.assert_not_called()

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
