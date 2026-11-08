"""Offline source routing policy integration and security tests."""
import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub import source_routes as routes, runtime
from audiohub.mixer import CHANNELS, defaults


class SourcePolicyTests(unittest.TestCase):
    def setUp(self):
        obj = tempfile.TemporaryDirectory()
        self.addCleanup(obj.cleanup)
        self.root = Path(obj.name)
        self.dir = self.root / "audiohub"

    def test_default_transport_slots(self):
        self.assertEqual(routes.load(self.dir), {
            "schema": routes.SCHEMA, "mode": "auto",
            "lan_slot": "laptop", "bluetooth": {},
        })
        self.assertEqual(routes.lan_target(self.dir), "audiohub.laptop")

    def test_lan_switch_can_target_any_of_three_slots(self):
        for slot in ("music", "tablet", "laptop"):
            with self.subTest(slot=slot):
                routes.set_lan(slot, self.dir)
                self.assertEqual(routes.lan_target(self.dir), "audiohub." + slot)

    def test_manual_bt_assignment_preserves_one_lan_slot(self):
        routes.set_lan("music", self.dir)
        routes.bind_bluetooth("aa:bb:cc:dd:ee:ff", "laptop", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        policy = routes.load(self.dir)
        self.assertEqual(policy["mode"], "manual")
        self.assertEqual(policy["bluetooth"]["AA:BB:CC:DD:EE:FF"], "laptop")
        self.assertEqual(set(policy["bluetooth"].values()),
                         {"laptop", "tablet"})

    def test_conflicting_slots_rejected_without_reset(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        old = routes.load(self.dir)
        with self.assertRaises(ValueError):
            routes.bind_bluetooth("11:22:33:44:55:66", "music", self.dir)
        with self.assertRaises(ValueError):
            routes.set_lan("music", self.dir)
        self.assertEqual(routes.load(self.dir), old)

    def test_swap_lan_with_occupied_bluetooth_slot_is_atomic_and_guarded(self):
        first = "AA:BB:CC:DD:EE:FF"
        second = "11:22:33:44:55:66"
        routes.bind_bluetooth(first, "music", self.dir)
        routes.bind_bluetooth(second, "tablet", self.dir)
        old = routes.load(self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        preview = routes.preview_route("swap-lan", "music", directory=self.dir)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        self.assertFalse(preview["policy_written"])
        self.assertFalse(preview["connected_devices_verified"])
        self.assertEqual(preview["lan_slot_change"],
                         {"from": "laptop", "to": "music"})
        self.assertEqual(preview["proposed"]["lan_slot"], "music")
        self.assertEqual(preview["proposed"]["bluetooth"], {
            first: "laptop", second: "tablet",
        })
        self.assertEqual(preview["bluetooth_bindings_removed"],
                         [{"address": first, "slot": "music"}])
        self.assertEqual(preview["bluetooth_bindings_added"],
                         [{"address": first, "slot": "laptop"}])
        with self.assertRaises(ValueError):
            routes.swap_lan_with_bluetooth("music", self.dir)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        changed = routes.swap_lan_with_bluetooth(
            "music", self.dir, if_revision=preview["revision"])
        self.assertEqual(changed, preview["proposed"])
        self.assertEqual(routes.load(self.dir), changed)
        self.assertEqual(routes.lan_target(self.dir), "audiohub.music")
        self.assertEqual(changed["mode"], old["mode"])
        self.assertEqual(len(changed["bluetooth"]), len(old["bluetooth"]))
        self.assertEqual(stat.S_IMODE(
            (self.dir / routes.FILENAME).stat().st_mode), 0o600)

    def test_swap_lan_requires_one_occupied_manual_bt_target(self):
        for setup, slot in (
            ("auto", "music"),
            ("manual-empty", "music"),
            ("manual-free", "tablet"),
            ("manual-self", "laptop"),
        ):
            with self.subTest(setup=setup):
                folder = self.root / setup
                if setup != "auto":
                    routes.set_mode("manual", folder)
                if setup in ("manual-free", "manual-self"):
                    routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", folder)
                before = ((folder / routes.FILENAME).read_bytes()
                          if folder.exists() else None)
                with self.assertRaises(ValueError):
                    routes.preview_route("swap-lan", slot, directory=folder)
                with self.assertRaises(ValueError):
                    routes._proposed(routes.load(folder), "swap-lan", slot)
                if before is None:
                    self.assertFalse(folder.exists())
                else:
                    self.assertEqual(
                        (folder / routes.FILENAME).read_bytes(), before)

    def test_swap_lan_rejects_stale_and_aba_confirmation_without_write(self):
        mac = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(mac, "music", self.dir)
        preview = routes.preview_route("swap-lan", "music", directory=self.dir)
        routes.update(lambda plan: dict(plan), self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        with self.assertRaises(routes.StaleRoutePreview):
            routes.swap_lan_with_bluetooth(
                "music", self.dir, if_revision=preview["revision"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        self.assertEqual(routes.load(self.dir)["lan_slot"], "laptop")
        with self.assertRaises(ValueError):
            routes.swap_lan_with_bluetooth(
                "music", self.dir, if_revision="r1-" + "Z"*64)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_swap_lan_cli_preview_confirm_and_unapproved_change_refused(self):
        mac = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(mac, "music", self.dir)
        original_preview = routes.preview_route
        original_swap = routes.swap_lan_with_bluetooth
        route_file = self.dir / routes.FILENAME
        before = route_file.read_bytes()
        with (mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, target, slot=None:
                original_preview(action, target, slot, directory=self.dir)),
              mock.patch.object(
                routes, "swap_lan_with_bluetooth",
                side_effect=lambda slot, *, if_revision:
                original_swap(slot, self.dir, if_revision=if_revision)) as writer):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as refused:
                    routes.main(["swap-lan", "music"])
            self.assertEqual(refused.exception.code, 2)
            writer.assert_not_called()
            self.assertEqual(route_file.read_bytes(), before)
            with redirect_stdout(StringIO()) as out:
                routes.main(["--preview", "swap-lan", "music"])
            planned = json.loads(out.getvalue())
            self.assertEqual(planned["proposed"]["lan_slot"], "music")
            self.assertEqual(route_file.read_bytes(), before)
            writer.assert_not_called()
            with redirect_stdout(StringIO()) as out:
                routes.main(["--confirm-local-route-change",
                             "--if-preview-revision", planned["revision"],
                             "swap-lan", "music"])
            self.assertEqual(json.loads(out.getvalue())["lan_slot"], "music")
            writer.assert_called_once_with(
                "music", if_revision=planned["revision"])
        self.assertEqual(routes.load(self.dir)["bluetooth"][mac], "laptop")

    def test_swap_lan_cli_stale_preview_never_retries_or_writes(self):
        mac = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(mac, "music", self.dir)
        planned = routes.preview_route("swap-lan", "music", directory=self.dir)
        routes.update(lambda plan: dict(plan), self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        original_preview = routes.preview_route
        original_swap = routes.swap_lan_with_bluetooth
        with (mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, target, slot=None:
                original_preview(action, target, slot, directory=self.dir)) as preview,
              mock.patch.object(
                routes, "swap_lan_with_bluetooth",
                side_effect=lambda slot, *, if_revision:
                original_swap(slot, self.dir, if_revision=if_revision)) as apply):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as halted:
                    routes.main(["--confirm-local-route-change",
                                 "--if-preview-revision", planned["revision"],
                                 "swap-lan", "music"])
            self.assertEqual(halted.exception.code, 4)
            stale = json.loads(out.getvalue())
            self.assertEqual(stale["status"], "route-preview-stale")
            self.assertFalse(stale["policy_written"])
            self.assertEqual(stale["fresh_preview"]["proposed"]["lan_slot"], "music")
            preview.assert_called_once_with("swap-lan", "music", None)
            apply.assert_called_once()
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_swap_two_occupied_bluetooth_inputs_preserves_lan_and_both_peers(self):
        first, second = "AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"
        routes.bind_bluetooth(first, "music", self.dir)
        routes.bind_bluetooth(second, "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        plan = routes.preview_route("swap-bt", "music", "tablet",
                                    directory=self.dir)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        self.assertFalse(plan["policy_written"])
        self.assertEqual(plan["proposed"]["bluetooth"],
                         {first: "tablet", second: "music"})
        self.assertEqual(plan["proposed"]["lan_slot"], "laptop")
        self.assertEqual(plan["proposed"]["mode"], "manual")
        self.assertEqual(len(plan["bluetooth_bindings_removed"]), 2)
        self.assertEqual(len(plan["bluetooth_bindings_added"]), 2)
        with self.assertRaises(ValueError):
            routes.swap_bluetooth_inputs("music", "tablet", self.dir)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        applied = routes.swap_bluetooth_inputs(
            "music", "tablet", self.dir, if_revision=plan["revision"])
        self.assertEqual(applied, plan["proposed"])
        self.assertEqual(routes.load(self.dir), applied)
        self.assertEqual(routes.lan_target(self.dir), "audiohub.laptop")
        self.assertEqual(stat.S_IMODE(
            (self.dir / routes.FILENAME).stat().st_mode), 0o600)

    def test_swap_two_bluetooth_inputs_rejects_unbound_and_lan_slots(self):
        first = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(first, "music", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        for src, dst in (("music", "tablet"), ("music", "laptop"),
                         ("music", "music"), ("tablet", "laptop")):
            with self.subTest(src=src, dst=dst):
                with self.assertRaises(ValueError):
                    routes.preview_route("swap-bt", src, dst,
                                         directory=self.dir)
                self.assertEqual(
                    (self.dir / routes.FILENAME).read_bytes(), before)
        auto = self.root / "auto-only"
        with self.assertRaises(ValueError):
            routes.preview_route("swap-bt", "music", "tablet",
                                 directory=auto)
        self.assertFalse(auto.exists())

    def test_swap_two_bluetooth_inputs_rejects_aba_and_invalid_revision(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        plan = routes.preview_route("swap-bt", "music", "tablet",
                                    directory=self.dir)
        routes.update(lambda value: dict(value), self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        with self.assertRaises(routes.StaleRoutePreview):
            routes.swap_bluetooth_inputs(
                "music", "tablet", self.dir, if_revision=plan["revision"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        with self.assertRaises(ValueError):
            routes.swap_bluetooth_inputs(
                "music", "tablet", self.dir, if_revision="r1-" + "X"*64)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_swap_two_bluetooth_inputs_cli_preview_guarded_apply_and_no_retry(self):
        first, second = "AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"
        routes.bind_bluetooth(first, "music", self.dir)
        routes.bind_bluetooth(second, "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        original_preview = routes.preview_route
        original_apply = routes.swap_bluetooth_inputs
        with (mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, target, slot=None:
                original_preview(action, target, slot, directory=self.dir)) as preview,
              mock.patch.object(
                routes, "swap_bluetooth_inputs",
                side_effect=lambda first, second, *, if_revision:
                original_apply(first, second, self.dir,
                               if_revision=if_revision)) as apply):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as no_confirmation:
                    routes.main(["swap-bt", "music", "tablet"])
            self.assertEqual(no_confirmation.exception.code, 2)
            apply.assert_not_called()
            with redirect_stdout(StringIO()) as out:
                routes.main(["--preview", "swap-bt", "music", "tablet"])
            plan = json.loads(out.getvalue())
            self.assertFalse(plan["policy_written"])
            self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
            with redirect_stdout(StringIO()) as out:
                routes.main(["--confirm-local-route-change",
                             "--if-preview-revision", plan["revision"],
                             "swap-bt", "music", "tablet"])
            self.assertEqual(
                json.loads(out.getvalue())["bluetooth"],
                {first: "tablet", second: "music"})
            apply.assert_called_once_with("music", "tablet",
                                          if_revision=plan["revision"])
        stale = routes.preview_route("swap-bt", "music", "tablet",
                                     directory=self.dir)
        routes.update(lambda value: dict(value), self.dir)
        current = (self.dir / routes.FILENAME).read_bytes()
        with (mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, target, slot=None:
                original_preview(action, target, slot, directory=self.dir)) as preview,
              mock.patch.object(
                routes, "swap_bluetooth_inputs",
                side_effect=lambda first, second, *, if_revision:
                original_apply(first, second, self.dir, if_revision=if_revision)) as apply):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as halt:
                    routes.main(["--confirm-local-route-change",
                                 "--if-preview-revision", stale["revision"],
                                 "swap-bt", "music", "tablet"])
            self.assertEqual(halt.exception.code, 4)
            self.assertEqual(json.loads(out.getvalue())["status"],
                             "route-preview-stale")
            preview.assert_called_once_with("swap-bt", "music", "tablet")
            apply.assert_called_once()
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), current)

    def test_move_assigned_bluetooth_to_free_input_atomic_and_no_mac_argument(self):
        mac = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(mac, "music", self.dir)
        old = (self.dir / routes.FILENAME).read_bytes()
        preview = routes.preview_route("move-bt", "music", "tablet",
                                       directory=self.dir)
        self.assertEqual(preview["current"]["bluetooth"], {mac: "music"})
        self.assertEqual(preview["proposed"]["bluetooth"], {mac: "tablet"})
        self.assertEqual(preview["proposed"]["lan_slot"], "laptop")
        self.assertFalse(preview["policy_written"])
        self.assertFalse(preview["connected_devices_verified"])
        self.assertFalse(preview["audible_playback_verified"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), old)
        with self.assertRaises(ValueError):
            routes.move_bluetooth_input("music", "tablet", self.dir)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), old)
        applied = routes.move_bluetooth_input(
            "music", "tablet", self.dir, if_revision=preview["revision"])
        self.assertEqual(applied, preview["proposed"])
        self.assertEqual(routes.load(self.dir)["bluetooth"], {mac: "tablet"})
        self.assertEqual(routes.lan_target(self.dir), "audiohub.laptop")
        self.assertEqual(stat.S_IMODE(
            (self.dir / routes.FILENAME).stat().st_mode), 0o600)

    def test_move_bluetooth_rejects_occupied_lan_self_and_auto_without_writes(self):
        first, second = "AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"
        routes.bind_bluetooth(first, "music", self.dir)
        routes.bind_bluetooth(second, "tablet", self.dir)
        old = (self.dir / routes.FILENAME).read_bytes()
        for src, dest in (
            ("music", "music"), ("music", "laptop"),
            ("music", "tablet"), ("laptop", "music"),
            ("tablet", "music"), ("unknown", "music"),
        ):
            with self.subTest(src=src, dest=dest):
                with self.assertRaises(ValueError):
                    routes.preview_route("move-bt", src, dest,
                                         directory=self.dir)
                self.assertEqual((self.dir / routes.FILENAME).read_bytes(), old)
        auto = self.root / "auto-move"
        with self.assertRaises(ValueError):
            routes.preview_route("move-bt", "music", "tablet", directory=auto)
        self.assertFalse(auto.exists())
        free = self.root / "manual-empty"
        routes.set_mode("manual", free)
        before = (free / routes.FILENAME).read_bytes()
        with self.assertRaises(ValueError):
            routes.preview_route("move-bt", "music", "tablet", directory=free)
        self.assertEqual((free / routes.FILENAME).read_bytes(), before)

    def test_move_bluetooth_stale_aba_and_invalid_revision_keep_policy(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        planned = routes.preview_route("move-bt", "music", "tablet",
                                       directory=self.dir)
        routes.update(lambda current: dict(current), self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        with self.assertRaises(routes.StaleRoutePreview):
            routes.move_bluetooth_input(
                "music", "tablet", self.dir, if_revision=planned["revision"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        with self.assertRaises(ValueError):
            routes.move_bluetooth_input(
                "music", "tablet", self.dir, if_revision="r1-" + "G"*64)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_move_bluetooth_cli_private_text_preview_confirmation_and_no_retry(self):
        mac = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(mac, "music", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        original_preview = routes.preview_route
        original_move = routes.move_bluetooth_input
        with (mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, target, slot=None:
                original_preview(action, target, slot, directory=self.dir)) as preview,
              mock.patch.object(
                routes, "move_bluetooth_input",
                side_effect=lambda src, dest, *, if_revision:
                original_move(src, dest, self.dir, if_revision=if_revision)) as move):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as refused:
                    routes.main(["move-bt", "music", "tablet"])
            self.assertEqual(refused.exception.code, 2)
            move.assert_not_called()
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "--preview",
                             "move-bt", "music", "tablet"])
            display = out.getvalue()
            self.assertIn("Move Bluetooth to free input", display)
            self.assertIn("music: Bluetooth source 1", display)
            self.assertIn("tablet: Bluetooth source 1", display)
            self.assertIn("Proposed:", display)
            self.assertNotIn(mac, display)
            self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
            planned = original_preview("move-bt", "music", "tablet",
                                       directory=self.dir)
            self.assertIn(planned["revision"], display)
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as refused:
                    routes.main(["--format", "text", "--confirm-local-route-change",
                                 "--if-preview-revision", planned["revision"],
                                 "move-bt", "music", "tablet"])
            self.assertEqual(refused.exception.code, 2)
            move.assert_not_called()
            with redirect_stdout(StringIO()) as out:
                routes.main(["--confirm-local-route-change",
                             "--if-preview-revision", planned["revision"],
                             "move-bt", "music", "tablet"])
            self.assertEqual(json.loads(out.getvalue())["bluetooth"], {mac: "tablet"})
            move.assert_called_once_with(
                "music", "tablet", if_revision=planned["revision"])
            self.assertEqual(routes.load(self.dir)["bluetooth"], {mac: "tablet"})
            stale = original_preview("move-bt", "tablet", "music",
                                     directory=self.dir)
            routes.update(lambda current: dict(current), self.dir)
            current = (self.dir / routes.FILENAME).read_bytes()
            with redirect_stdout(StringIO()) as out:
                with self.assertRaises(SystemExit) as stopped:
                    routes.main(["--confirm-local-route-change",
                                 "--if-preview-revision", stale["revision"],
                                 "move-bt", "tablet", "music"])
            self.assertEqual(stopped.exception.code, 4)
            self.assertEqual(json.loads(out.getvalue())["status"],
                             "route-preview-stale")
            self.assertEqual((self.dir / routes.FILENAME).read_bytes(), current)
            self.assertEqual(move.call_count, 2)
            self.assertEqual(preview.call_count, 2)

    def test_third_bluetooth_source_is_rejected(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        with self.assertRaises(ValueError):
            routes.bind_bluetooth("22:33:44:55:66:77", "music", self.dir)

    def test_manual_zero_bt_disables_auto_discovery(self):
        routes.set_mode("manual", self.dir)
        self.assertEqual(routes.load(self.dir)["bluetooth"], {})
        self.assertEqual(routes.load(self.dir)["mode"], "manual")
        routes.set_mode("auto", self.dir)
        self.assertEqual(routes.load(self.dir)["mode"], "auto")

    def test_unbind_does_not_reenable_auto(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.unbind_bluetooth("AA:BB:CC:DD:EE:FF", self.dir)
        self.assertEqual(routes.load(self.dir)["mode"], "manual")
        self.assertEqual(routes.load(self.dir)["bluetooth"], {})

    def test_invalid_policy_types_and_unknown_keys(self):
        bad = [
            {}, [], {"schema": routes.SCHEMA, "mode": "auto",
                     "lan_slot": "music", "bluetooth": {"AA:BB:CC:DD:EE:FF": "tablet"}},
            {"schema": routes.SCHEMA, "mode": "manual",
             "lan_slot": "laptop", "bluetooth": {"AA:BB:CC:DD:EE:FF": "laptop"}},
            {"schema": routes.SCHEMA, "mode": "manual",
             "lan_slot": "laptop", "bluetooth": {"AA:BB:CC:DD:EE:FF": "music",
                                                "11:22:33:44:55:66": "music"}},
        ]
        for plan in bad:
            with self.subTest(plan=repr(plan)), self.assertRaises(ValueError):
                routes.validate(plan)

    def test_private_on_disk_permissions(self):
        routes.set_lan("music", self.dir)
        file = self.dir / routes.FILENAME
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        self.assertFalse(any(x.name.endswith(".tmp") for x in self.dir.iterdir()))

    def test_corrupt_policy_fails_closed_and_is_not_overwritten(self):
        routes.set_mode("manual", self.dir)
        file = self.dir / routes.FILENAME
        file.write_text("garbage")
        with self.assertRaises(ValueError):
            routes.load(self.dir)
        with self.assertRaises(ValueError):
            routes.set_lan("music", self.dir)
        self.assertEqual(file.read_text(), "garbage")

    def test_duplicate_top_level_route_keys_fail_closed_without_reset(self):
        routes.set_mode("manual", self.dir)
        path = self.dir / routes.FILENAME
        conflicting = (
            '{"schema":"audiohub-source-routes/1",'
            '"mode":"auto","mode":"manual","lan_slot":"laptop","bluetooth":{}}'
        )
        path.write_text(conflicting)
        with self.assertRaises(ValueError):
            routes.load(self.dir)
        with self.assertRaises(ValueError):
            routes.set_lan("tablet", self.dir)
        self.assertEqual(path.read_text(), conflicting)

    def test_duplicate_bluetooth_address_prevents_last_wins_routing(self):
        routes.set_mode("manual", self.dir)
        path = self.dir / routes.FILENAME
        conflicting = (
            '{"schema":"audiohub-source-routes/1","mode":"manual",'
            '"lan_slot":"laptop","bluetooth":{'
            '"AA:BB:CC:DD:EE:FF":"music",'
            '"AA:BB:CC:DD:EE:FF":"tablet"}}'
        )
        path.write_text(conflicting)
        with self.assertRaises(ValueError):
            routes.load(self.dir)
        self.assertEqual(path.read_text(), conflicting)

    def test_nested_route_json_recursion_cannot_crash_supervisor(self):
        routes.set_mode("manual", self.dir)
        path = self.dir / routes.FILENAME
        body = "[" * 1550 + "0" + "]" * 1550
        self.assertLess(len(body), routes.MAX_FILE_BYTES)
        path.write_text(body)
        with self.assertRaises(ValueError):
            routes.load(self.dir)
        self.assertEqual(path.read_text(), body)

    def test_route_fifo_does_not_block_before_regular_file_check(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("Linux FIFO needed")
        self.dir.mkdir(mode=0o700)
        os.mkfifo(self.dir / routes.FILENAME)
        original_open = os.open

        def safe_open(path, flags, *args, **kwargs):
            if path == routes.FILENAME:
                self.assertTrue(flags & os.O_NONBLOCK, "FIFO must not block")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(routes.os, "open", side_effect=safe_open):
            with self.assertRaises(PermissionError):
                routes.load(self.dir)

    def test_short_private_route_read_is_rejected_not_routed(self):
        routes.set_mode("manual", self.dir)
        with mock.patch.object(routes.os, "read", return_value=b"{}"):
            with self.assertRaises(ValueError):
                routes.load(self.dir)

    def test_ancestor_symlink_never_redirects_policy_read_or_write(self):
        actual = self.root / "actual"
        actual.mkdir()
        safe = actual / "config"
        routes.set_mode("manual", safe)
        before = (safe / routes.FILENAME).read_bytes()
        (self.root / "linked").symlink_to(actual, target_is_directory=True)
        redirected = self.root / "linked" / "config"
        with self.assertRaises(OSError):
            routes.load(redirected)
        with self.assertRaises(OSError):
            routes.set_mode("auto", redirected)
        self.assertEqual((safe / routes.FILENAME).read_bytes(), before)

    def test_ancestor_symlink_never_redirects_directory_creation(self):
        actual = self.root / "actual"
        actual.mkdir()
        (self.root / "linked").symlink_to(actual, target_is_directory=True)
        with self.assertRaises(OSError):
            routes.set_mode("manual", self.root / "linked" / "new")
        self.assertFalse((actual / "new").exists())

    def test_parent_traversal_component_denied_without_writes(self):
        with self.assertRaises(ValueError):
            routes.set_mode("manual", self.root / "folder" / ".." / "outside")
        self.assertFalse((self.root / "outside").exists())

    def test_existing_normal_nested_directory_still_supported(self):
        folder = self.root / "regular" / "nested" / "audiohub"
        routes.set_lan("tablet", folder)
        self.assertEqual(routes.load(folder)["lan_slot"], "tablet")

    def test_file_symlink_rejected(self):
        self.dir.mkdir(mode=0o700)
        private = self.root / "private"
        private.write_text("secret")
        (self.dir / routes.FILENAME).symlink_to(private)
        with self.assertRaises(OSError):
            routes.load(self.dir)
        self.assertEqual(private.read_text(), "secret")

    def test_directory_symlink_rejected(self):
        real = self.root / "real"
        real.mkdir(mode=0o700)
        self.dir.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            routes.load(self.dir)

    def test_overlong_or_world_readable_policy_rejected(self):
        routes.set_lan("music", self.dir)
        file = self.dir / routes.FILENAME
        file.chmod(0o644)
        with self.assertRaises(PermissionError):
            routes.load(self.dir)
        file.chmod(0o600)
        file.write_bytes(b"x" * (routes.MAX_FILE_BYTES + 1))
        with self.assertRaises((ValueError, PermissionError)):
            routes.load(self.dir)

    def test_route_preview_first_bluetooth_warns_auto_to_manual_without_writes(self):
        plan = routes.preview_route(
            "bind-bt", "aa:bb:cc:dd:ee:ff", "music", directory=self.dir)
        self.assertEqual(plan["mode"], "source-route-preview-only")
        self.assertEqual(plan["current"]["mode"], "auto")
        self.assertEqual(plan["proposed"]["mode"], "manual")
        self.assertEqual(plan["proposed"]["bluetooth"],
                         {"AA:BB:CC:DD:EE:FF": "music"})
        self.assertTrue(plan["auto_discovery_would_be_disabled"])
        self.assertTrue(plan["would_change"])
        self.assertEqual(plan["bluetooth_bindings_added"], [
            {"address": "AA:BB:CC:DD:EE:FF", "slot": "music"}])
        self.assertTrue(plan["proposed_slots"]["laptop"]["lan_reserved"])
        self.assertFalse(plan["proposed_slots"]["music"][
            "free_for_manual_assignment"])
        self.assertTrue(plan["proposed_slots"]["tablet"][
            "free_for_manual_assignment"])
        self.assertRegex(plan["revision"], r"^r1-[0-9a-f]{64}$")
        self.assertFalse(plan["connected_devices_verified"])
        self.assertFalse(plan["audible_playback_verified"])
        self.assertFalse(plan["policy_written"])
        self.assertTrue(plan["separate_confirmation_recommended"])
        self.assertFalse(self.dir.exists())

    def test_route_preview_set_lan_explains_slot_shift_and_keeps_original(self):
        routes.set_mode("manual", self.dir)
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        plan = routes.preview_route("set-lan", "tablet", directory=self.dir)
        self.assertEqual(plan["lan_slot_change"],
                         {"from": "laptop", "to": "tablet"})
        self.assertEqual(plan["current"]["lan_slot"], "laptop")
        self.assertEqual(plan["proposed"]["lan_slot"], "tablet")
        self.assertEqual(plan["bluetooth_bindings_removed"], [])
        self.assertEqual(plan["bluetooth_bindings_added"], [])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        self.assertFalse((self.dir / ".source-routes.lock").is_symlink())

    def test_route_preview_auto_mode_clears_manual_bluetooth_bindings_only_in_plan(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        plan = routes.preview_route("mode", "auto", directory=self.dir)
        self.assertEqual(plan["proposed"]["bluetooth"], {})
        self.assertEqual(plan["source_mode_change"],
                         {"from": "manual", "to": "auto"})
        self.assertEqual([x["slot"] for x in plan["bluetooth_bindings_removed"]],
                         ["tablet", "music"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_route_slots_reports_reserved_free_slots_but_no_live_connections(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        occupancy = routes.route_slots(directory=self.dir)
        self.assertEqual(occupancy["free_slots"], [])
        self.assertEqual(occupancy["slots"]["laptop"]["lan_reserved"], True)
        self.assertEqual(occupancy["slots"]["music"]["manual_bluetooth_addresses"],
                         ["AA:BB:CC:DD:EE:FF"])
        self.assertFalse(occupancy["policy_written"])
        self.assertFalse(occupancy["connected_devices_verified"])
        self.assertFalse(occupancy["audible_playback_verified"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_route_preview_conflicting_slot_or_excess_bluetooth_fails_with_no_write(self):
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "music", self.dir)
        routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        bad = (("set-lan", "music", None),
               ("bind-bt", "AA:BB:CC:DD:EE:FF", "laptop"),
               ("bind-bt", "22:33:44:55:66:77", "music"),
               ("unbind-bt", "FF:EE:DD:CC:BB:AA", None),
               ("bind-bt", "bad-address", "music"))
        for action, value, slot in bad:
            with self.subTest(action=action, value=value):
                with self.assertRaises(ValueError):
                    routes.preview_route(action, value, slot,
                                         directory=self.dir)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_route_guarded_apply_changes_only_after_exact_preview_confirmation(self):
        old = routes.preview_route("set-lan", "music", directory=self.dir)
        self.assertFalse(self.dir.exists())
        result = routes.set_lan(
            "music", self.dir, if_revision=old["revision"])
        self.assertEqual(result["lan_slot"], "music")
        self.assertEqual(routes.load(self.dir)["lan_slot"], "music")
        self.assertEqual(stat.S_IMODE((self.dir / routes.FILENAME).stat().st_mode),
                         0o600)
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)

    def test_route_stale_guard_rejects_unrelated_change_under_writer_lock(self):
        routes.set_mode("manual", self.dir)
        plan = routes.preview_route("set-lan", "music", directory=self.dir)
        routes.bind_bluetooth("AA:BB:CC:DD:EE:FF", "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        with self.assertRaises(routes.StaleRoutePreview):
            routes.set_lan("music", self.dir,
                           if_revision=plan["revision"])
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)

    def test_route_stale_guard_detects_same_contents_aba_replacement(self):
        routes.set_mode("manual", self.dir)
        plan = routes.preview_route("set-lan", "music", directory=self.dir)
        original_policy = routes.load(self.dir)
        routes.update(lambda current: dict(current), self.dir)
        self.assertEqual(routes.load(self.dir), original_policy)
        with self.assertRaises(routes.StaleRoutePreview):
            routes.set_lan("music", self.dir,
                           if_revision=plan["revision"])
        self.assertEqual(routes.load(self.dir), original_policy)

    def test_route_preview_detects_concurrent_policy_replacement_during_read(self):
        routes.set_mode("manual", self.dir)
        original_read = routes._read
        def modified_during_read(fd):
            policy = original_read(fd)
            # The simulated writer uses the unpatched loader, so this test
            # models one replacement rather than recursively intercepting it.
            with mock.patch.object(routes, "_read", original_read):
                routes.set_lan("music", self.dir)
            return policy
        with mock.patch.object(routes, "_read", side_effect=modified_during_read):
            with self.assertRaises(ValueError):
                routes.preview_route("mode", "auto", directory=self.dir)
        self.assertEqual(routes.load(self.dir)["lan_slot"], "music")

    def test_route_preview_rejects_bad_revision_and_no_policy_write(self):
        for invalid in (None, "v1-" + "a"*64, "r1-" + "a"*63,
                        "r1-" + "A"*64, "x", True):
            if invalid is None:
                continue
            with self.subTest(token=repr(invalid)):
                with self.assertRaises(ValueError):
                    routes.set_lan("music", self.dir, if_revision=invalid)
                self.assertFalse(self.dir.exists())

    def test_route_cli_preview_and_slots_are_read_only(self):
        demo = {"mode": "source-route-preview-only", "policy_written": False}
        slots = {"mode": "source-slots-read-only", "policy_written": False}
        with (mock.patch.object(routes, "preview_route", return_value=demo) as plan,
              mock.patch.object(routes, "route_slots", return_value=slots) as free,
              mock.patch.object(routes, "bind_bluetooth") as bind,
              mock.patch.object(routes, "set_lan") as lan):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--preview", "bind-bt",
                             "AA:BB:CC:DD:EE:FF", "music"])
            plan.assert_called_once_with("bind-bt", "AA:BB:CC:DD:EE:FF", "music")
            self.assertEqual(json.loads(out.getvalue()), demo)
            with redirect_stdout(StringIO()) as out:
                routes.main(["slots"])
            self.assertEqual(json.loads(out.getvalue()), slots)
            free.assert_called_once()
            bind.assert_not_called()
            lan.assert_not_called()

    def test_private_route_map_text_shows_slots_without_identifiers_or_writes(self):
        mac1, mac2 = "AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"
        routes.bind_bluetooth(mac1, "music", self.dir)
        routes.bind_bluetooth(mac2, "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        original = routes.route_slots
        with (mock.patch.object(
                routes, "route_slots",
                side_effect=lambda: original(self.dir)) as reader,
              mock.patch.object(routes, "update") as writer):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "slots"])
            reader.assert_called_once_with()
            writer.assert_not_called()
        content = out.getvalue()
        self.assertIn("source reservations (read-only)", content)
        self.assertIn("music: Bluetooth source 2", content)
        self.assertIn("laptop: LAN reserved", content)
        self.assertIn("tablet: Bluetooth source 1", content)
        self.assertIn("No connection, PCM or audible speaker", content)
        self.assertNotIn(mac1, content)
        self.assertNotIn(mac2, content)
        self.assertNotIn("r1-", content)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        expected = routes.route_slots(self.dir)
        self.assertEqual(routes.format_route_slots_text(expected).strip(),
                         content.strip())
        self.assertEqual(json.loads(json.dumps(expected)), expected)

    def test_private_route_preview_text_changes_and_exact_revision_without_mac(self):
        mac1, mac2 = "AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"
        routes.bind_bluetooth(mac1, "music", self.dir)
        routes.bind_bluetooth(mac2, "tablet", self.dir)
        before = (self.dir / routes.FILENAME).read_bytes()
        original = routes.preview_route
        with (mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, value, slot=None:
                original(action, value, slot, directory=self.dir)) as reader,
              mock.patch.object(routes, "update") as writer,
              mock.patch.object(routes, "swap_bluetooth_inputs") as apply):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "--preview",
                             "swap-bt", "music", "tablet"])
            reader.assert_called_once_with("swap-bt", "music", "tablet")
            writer.assert_not_called()
            apply.assert_not_called()
        display = out.getvalue()
        preview = routes.preview_route("swap-bt", "music", "tablet",
                                       directory=self.dir)
        self.assertIn(preview["revision"], display)
        self.assertIn("Current:", display)
        self.assertIn("Proposed:", display)
        self.assertIn("music: Bluetooth source 2", display)
        self.assertIn("music: Bluetooth source 1", display)
        self.assertIn("laptop: LAN reserved", display)
        self.assertIn("Change requested: yes", display)
        self.assertIn("No routing policy or devices were changed", display)
        self.assertNotIn(mac1, display)
        self.assertNotIn(mac2, display)
        self.assertEqual((self.dir / routes.FILENAME).read_bytes(), before)
        self.assertEqual(routes.format_route_preview_text(preview).strip(),
                         display.strip())

    def test_route_text_preview_warns_auto_discovery_before_manual_binding(self):
        mac = "AA:BB:CC:DD:EE:FF"
        folder = self.root / "not-yet-configured"
        original = routes.preview_route
        with mock.patch.object(
                routes, "preview_route",
                side_effect=lambda action, value, slot=None:
                original(action, value, slot, directory=folder)):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "--preview",
                             "bind-bt", mac, "music"])
        display = out.getvalue()
        self.assertIn("automatic Bluetooth discovery would be disabled", display)
        self.assertIn("Mode: auto", display)
        self.assertIn("Mode: manual", display)
        self.assertIn("Bluetooth source 1", display)
        self.assertNotIn(mac, display)
        self.assertFalse(folder.exists())
        original_slots = routes.route_slots
        with mock.patch.object(routes, "route_slots",
                               side_effect=lambda: original_slots(folder)):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "slots"])
        self.assertIn("AudioHub current source reservations", out.getvalue())

    def test_private_route_text_renderers_reject_malformed_or_forged_reports(self):
        mac = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(mac, "music", self.dir)
        slots = routes.route_slots(self.dir)
        preview = routes.preview_route("swap-lan", "music",
                                       directory=self.dir)
        for change in (
            lambda x: x["slots"]["music"].update(
                {"manual_bluetooth_addresses": ["FAKE:DEVICE:DATA"]}),
            lambda x: x["slots"]["music"].update(
                {"free_for_manual_assignment": True}),
            lambda x: x.update({"revision": "SECRET\\nINJECT"}),
            lambda x: x.update({"free_slots": ["SECRET"]}),
            lambda x: x.update({"connected_devices_verified": True}),
        ):
            invalid = json.loads(json.dumps(slots))
            change(invalid)
            with self.assertRaises((ValueError, KeyError, TypeError)):
                routes.format_route_slots_text(invalid)
        for change in (
            lambda x: x.update({"revision": "SECRET\\nINJECT"}),
            lambda x: x.update({"would_change": False}),
            lambda x: x["current"].update({"lan_slot": "SECRET"}),
            lambda x: x.update({"action": "SECRET\\nINJECT"}),
            lambda x: x.update({"policy_written": True}),
            lambda x: x["proposed"]["bluetooth"].update({mac: "music"}),
        ):
            invalid = json.loads(json.dumps(preview))
            change(invalid)
            with self.assertRaises((ValueError, KeyError, TypeError)):
                routes.format_route_preview_text(invalid)
        self.assertNotIn(mac, routes.format_route_preview_text(preview))

    def test_route_cli_guarded_apply_and_stale_refresh_never_auto_retry(self):
        preview = {"mode": "source-route-preview-only", "policy_written": False}
        token = "r1-" + "a"*64
        with (mock.patch.object(routes, "set_lan", return_value=routes.defaults()) as apply,
              mock.patch.object(routes, "preview_route", return_value=preview) as plan):
            with redirect_stdout(StringIO()):
                routes.main(["--confirm-local-route-change",
                             "--if-preview-revision", token, "set-lan", "music"])
            apply.assert_called_once_with("music", if_revision=token)
            plan.assert_not_called()
        with (mock.patch.object(routes, "set_lan",
                                side_effect=routes.StaleRoutePreview("PRIVATE")) as apply,
              mock.patch.object(routes, "preview_route", return_value=preview) as plan):
            with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
                with self.assertRaises(SystemExit) as halted:
                    routes.main(["--confirm-local-route-change",
                                 "--if-preview-revision", token, "set-lan", "music"])
            self.assertEqual(halted.exception.code, 4)
            self.assertEqual(json.loads(out.getvalue())["status"], "route-preview-stale")
            self.assertEqual(json.loads(out.getvalue())["fresh_preview"], preview)
            self.assertNotIn("PRIVATE", err.getvalue())
            apply.assert_called_once()
            plan.assert_called_once_with("set-lan", "music", None)

    def test_route_cli_rejects_invalid_mixed_preview_and_confirmation_flags(self):
        token = "r1-" + "a"*64
        bad = (
            ["--preview", "--confirm-local-route-change", "set-lan", "music"],
            ["--preview", "--if-preview-revision", token, "set-lan", "music"],
            ["--confirm-local-route-change", "set-lan", "music"],
            ["--if-preview-revision", token, "set-lan", "music"],
            ["--preview", "show"],
            ["--confirm-local-route-change", "--if-preview-revision", token, "slots"],
        )
        for argv in bad:
            with self.subTest(argv=argv):
                with (mock.patch.object(routes, "update") as writer,
                      mock.patch.object(routes, "preview_route") as preview):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failure:
                            routes.main(argv)
                    self.assertEqual(failure.exception.code, 2)
                    writer.assert_not_called()
                    preview.assert_not_called()


class FakeProcess:
    def __init__(self, alive=True):
        self.alive = alive

    def poll(self):
        return None if self.alive else 1


class LocalSourceStatusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / "private"
        self.file = self.directory / "runtime-status.json"

    def report_file(self, data):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        runtime.atomic_json(self.file, data)

    @staticmethod
    def sample(*, lan_slot="laptop", usb_ready=True):
        mac = "AA:BB:CC:DD:EE:FF"
        sources = [{"address": mac, "name": "bluez_input.test"}]
        assignment = {mac: "music"}
        loops = {mac: ("bluez_input.test", "audiohub.music", FakeProcess())}
        sinks = {"audiohub.music": 5, "audiohub.laptop": 6}
        return runtime.observed_source_slots(
            sources, assignment, loops, sinks, lan_slot=lan_slot,
            policy_valid=True, usb_ready=usb_ready)

    def test_observer_separates_configured_detected_and_running_from_audible(self):
        actual = self.sample()
        self.assertEqual(set(actual), set(CHANNELS))
        self.assertTrue(actual["music"]["bluetooth_assigned"])
        self.assertTrue(actual["music"]["bluetooth_node_observed"])
        self.assertTrue(actual["music"]["managed_loopback_running"])
        self.assertTrue(actual["laptop"]["lan_reserved"])
        self.assertFalse(actual["laptop"]["bluetooth_assigned"])
        self.assertFalse(actual["tablet"]["virtual_sink_observed"])
        self.assertNotIn("AA:BB:CC", str(actual))

    def test_source_status_fresh_shows_evidence_and_unknown_connection(self):
        self.report_file({
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "mac": "AA:BB:CC:DD:EE:FF", "ssid": "SECRET-WIFI",
            "device_id": "SECRET-NODE",
        })
        before = self.file.read_bytes()
        with mock.patch.object(runtime, "atomic_json") as write:
            report = routes.read_source_report(path=self.file, now=105)
            write.assert_not_called()
        self.assertTrue(report["fresh"])
        self.assertTrue(report["observations_available"])
        self.assertEqual(report["status_age_seconds"], 5)
        music = report["inputs"]["music"]
        self.assertEqual(music["configured_role"], "bluetooth_assigned")
        self.assertTrue(music["configured"])
        self.assertTrue(music["bluetooth_source_node_seen"])
        self.assertTrue(music["managed_loopback_process_running"])
        self.assertEqual(music["bluetooth_connected"], "unverified")
        self.assertEqual(music["audio_stream_available"], "unverified")
        self.assertEqual(music["audible_playback"], "unverified")
        self.assertEqual(report["inputs"]["laptop"]["configured_role"], "lan_reserved")
        self.assertIsNone(report["inputs"]["laptop"]["bluetooth_source_node_seen"])
        self.assertIsNone(report["inputs"]["laptop"]["managed_loopback_process_running"])
        self.assertEqual(report["inputs"]["tablet"]["configured_role"], "unassigned")
        self.assertFalse(report["inputs"]["tablet"]["configured"])
        self.assertFalse(report["hardware_verified"])
        self.assertFalse(report["release_ready"])
        self.assertNotIn("AA:BB:CC", json.dumps(report))
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertEqual(self.file.read_bytes(), before)

    def test_pipewire_eq_to_usb_direct_link_is_per_input_topology_only(self):
        self.report_file({
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "pipewire_graph_inspection_available": True,
            "eq_output_usb_direct_links": ["music", "laptop"],
            "raw_node_id": "SECRET-PIPEWIRE-ID",
        })
        before = self.file.read_bytes()
        report = routes.read_source_report(path=self.file, now=102)
        self.assertTrue(report["observations_available"])
        self.assertTrue(report["pipewire_graph_inspection_available"])
        self.assertTrue(report["inputs"]["music"]["eq_to_usb_direct_link_observed"])
        self.assertTrue(report["inputs"]["laptop"]["eq_to_usb_direct_link_observed"])
        self.assertFalse(report["inputs"]["tablet"]["eq_to_usb_direct_link_observed"])
        self.assertEqual(report["inputs"]["music"]["audio_stream_available"], "unverified")
        self.assertEqual(report["inputs"]["music"]["audible_playback"], "unverified")
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertEqual(self.file.read_bytes(), before)

    def test_pipewire_missing_direct_link_does_not_claim_disconnection(self):
        base = {
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "pipewire_graph_inspection_available": True,
            "eq_output_usb_direct_links": [],
        }
        inspected = routes.interpret_source_status(base, now=101)
        self.assertTrue(inspected["pipewire_graph_inspection_available"])
        self.assertFalse(inspected["inputs"]["music"]["eq_to_usb_direct_link_observed"])
        self.assertEqual(inspected["inputs"]["music"]["bluetooth_connected"], "unverified")
        self.assertEqual(inspected["inputs"]["music"]["audio_stream_available"], "unverified")
        unavailable = routes.interpret_source_status({
            **base, "pipewire_graph_inspection_available": False,
        }, now=101)
        self.assertFalse(unavailable["pipewire_graph_inspection_available"])
        self.assertIsNone(unavailable["inputs"]["music"]["eq_to_usb_direct_link_observed"])

    def test_pipewire_graph_link_evidence_rejects_forged_and_stale_data(self):
        base = {
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "pipewire_graph_inspection_available": True,
            "eq_output_usb_direct_links": ["music"],
        }
        for override in (
            {"pipewire_graph_inspection_available": 1},
            {"eq_output_usb_direct_links": ["music", "music"]},
            {"eq_output_usb_direct_links": ["music", "secret-id"]},
            {"eq_output_usb_direct_links": ["music", 1]},
            {"eq_output_usb_direct_links": "music"},
            {"pipewire_graph_inspection_available": False},
            {"updated_at": 50},
            {"route_policy_valid": False},
        ):
            with self.subTest(override=override):
                report = routes.interpret_source_status({**base, **override}, now=103)
                self.assertIsNone(report["pipewire_graph_inspection_available"])
                for slot in CHANNELS:
                    self.assertIsNone(report["inputs"][slot][
                        "eq_to_usb_direct_link_observed"])
                self.assertFalse(report["hardware_verified"])
                self.assertFalse(report["release_ready"])

    def test_local_next_check_triages_real_status_without_audio_claim(self):
        base = {
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "pipewire_graph_inspection_available": True,
            "eq_output_usb_direct_links": ["music"],
        }
        report = routes.interpret_source_status(base, now=102)
        self.assertEqual(report["inputs"]["music"]["next_local_check"],
                         "verify_actual_speaker_audio")
        self.assertEqual(report["inputs"]["laptop"]["next_local_check"],
                         "verify_opt_in_lan_receiver")
        self.assertEqual(report["inputs"]["tablet"]["next_local_check"],
                         "inspect_eq_virtual_sink")
        self.assertEqual(report["inputs"]["music"]["audible_playback"], "unverified")
        self.assertEqual(report["inputs"]["music"]["audio_stream_available"], "unverified")
        self.assertFalse(report["hardware_verified"])
        self.assertFalse(report["release_ready"])
        self.assertEqual(routes.interpret_source_status({}, now=102)[
            "inputs"]["music"]["next_local_check"], "refresh_private_supervisor_status")

        for changes, expected in (
            ({"usb_route_ready": False}, "inspect_usb_default_output"),
            ({"virtual_sink_observed": False}, "inspect_eq_virtual_sink"),
            ({"bluetooth_node_observed": False}, "inspect_bluetooth_pipewire_source"),
            ({"managed_loopback_running": False}, "inspect_managed_loopback"),
        ):
            with self.subTest(changes=changes):
                current = json.loads(json.dumps(base))
                current["source_slot_observations"]["music"].update(changes)
                observed = routes.interpret_source_status(current, now=102)
                self.assertEqual(observed["inputs"]["music"]["next_local_check"],
                                 expected)
        no_edge = routes.interpret_source_status({
            **base, "eq_output_usb_direct_links": [],
        }, now=102)
        self.assertEqual(no_edge["inputs"]["music"]["next_local_check"],
                         "inspect_possible_intermediary_links")
        no_graph = routes.interpret_source_status({
            **base, "pipewire_graph_inspection_available": False,
            "eq_output_usb_direct_links": [],
        }, now=102)
        self.assertEqual(no_graph["inputs"]["music"]["next_local_check"],
                         "inspect_pipewire_graph")
        unassigned = json.loads(json.dumps(base))
        unassigned["source_slot_observations"]["tablet"]["virtual_sink_observed"] = True
        self.assertEqual(routes.interpret_source_status(unassigned, now=102)[
            "inputs"]["tablet"]["next_local_check"], "assign_source_or_leave_unused")

    def test_local_next_check_bluez_false_only_when_explicitly_probed(self):
        from subprocess import CompletedProcess
        mac = self._manual_blue_probe_state()
        before = self.file.read_bytes()
        self.assertEqual(routes.read_source_report(path=self.file, now=102)[
            "inputs"]["music"]["next_local_check"], "inspect_pipewire_graph")
        def disconnected(argv, *, timeout, max_bytes):
            return CompletedProcess(argv, 0,
                                    "Device " + mac + "\n Connected: no\n", "")
        with mock.patch.object(routes, "bounded_command_output",
                               side_effect=disconnected) as query:
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=102)
            query.assert_called_once()
        self.assertEqual(report["inputs"]["music"]["next_local_check"],
                         "inspect_bluetooth_device_connection")
        self.assertFalse(report["inputs"]["music"]["bluez_connected_property"])
        self.assertEqual(report["inputs"]["music"]["audible_playback"], "unverified")
        self.assertEqual(self.file.read_bytes(), before)
        self.assertNotIn(mac, json.dumps(report))

    def test_human_source_status_one_screen_never_claims_audio_or_identity(self):
        report = routes.interpret_source_status({
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
            "pipewire_graph_inspection_available": True,
            "eq_output_usb_direct_links": ["music"],
            "mac": "AA:BB:CC:DD:EE:FF", "password": "SECRET",
        }, now=102)
        out = routes.format_source_status_text(report)
        self.assertIn("Runtime evidence: available", out)
        for slot in CHANNELS:
            self.assertIn(slot + " (", out)
        self.assertIn("EQ-to-USB direct: yes", out)
        self.assertIn("Test actual speaker audio manually", out)
        self.assertIn("BlueZ property: ?", out)
        self.assertIn("not proof of PCM samples or audible sound", out)
        self.assertNotIn("AA:BB:CC", out)
        self.assertNotIn("SECRET", out)
        self.assertNotIn("unverified\":", out)

    def test_human_status_cli_is_opt_in_and_other_commands_refuse_format(self):
        report = routes.interpret_source_status({}, now=101)
        with (mock.patch.object(routes, "read_source_report", return_value=report) as read,
              mock.patch.object(routes, "probe_bluez_connections") as probe,
              mock.patch.object(routes, "update") as write):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "status"])
            text = out.getvalue()
            self.assertIn("Runtime evidence: unknown", text)
            self.assertIn("Refresh private supervisor status", text)
            self.assertEqual(text.count("  Next: "), len(CHANNELS))
            self.assertNotIn("{", text)
            read.assert_called_once_with()
            probe.assert_not_called()
            write.assert_not_called()
        with mock.patch.object(routes, "read_source_report", return_value=report):
            with redirect_stdout(StringIO()) as out:
                routes.main(["status"])
            self.assertEqual(json.loads(out.getvalue()), report)
        for invalid in (
            ["--format", "text", "show"],
            ["--format", "text", "set-lan", "music"],
            ["--format", "text", "--confirm-local-route-change",
             "--if-preview-revision", "r1-" + "a"*64, "set-lan", "music"],
            ["--format", "text", "--preview", "status"],
        ):
            with self.subTest(invalid=invalid):
                with (mock.patch.object(routes, "load") as read_policy,
                      mock.patch.object(routes, "update") as write,
                      mock.patch.object(routes, "probe_bluez_connections") as probe):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as refused:
                            routes.main(invalid)
                    self.assertEqual(refused.exception.code, 2)
                    read_policy.assert_not_called()
                    write.assert_not_called()
                    probe.assert_not_called()

    def test_human_status_bluez_opt_in_and_malicious_report_fail_closed(self):
        report = routes.interpret_source_status({}, now=100)
        report["inputs"]["music"]["bluez_connected_property"] = False
        with mock.patch.object(routes, "probe_bluez_connections",
                               return_value=report) as probe:
            with redirect_stdout(StringIO()) as out:
                routes.main(["--format", "text", "--probe-bluetooth", "status"])
            self.assertIn("BlueZ property: no", out.getvalue())
            probe.assert_called_once_with()
        bad = json.loads(json.dumps(report))
        bad["inputs"]["music"]["next_local_check"] = "SECRET\\nCode"
        with self.assertRaises(ValueError):
            routes.format_source_status_text(bad)
        bad = json.loads(json.dumps(report))
        bad["inputs"]["music"]["eq_to_usb_direct_link_observed"] = "yes SECRET"
        with self.assertRaises(ValueError):
            routes.format_source_status_text(bad)

    def test_source_status_stale_missing_future_and_wrong_type_fail_closed(self):
        for age in (None, 31, -1, 100):
            with self.subTest(age=age):
                raw = {
                    "updated_at": 100 if age is None else 100 - age,
                    "route_policy_valid": True,
                    "source_slot_observations_version": 1,
                    "source_slot_observations": self.sample(),
                }
                if age is None:
                    raw.pop("updated_at")
                report = routes.interpret_source_status(raw, now=100)
                self.assertFalse(report["fresh"])
                self.assertFalse(report["observations_available"])
                for slot in CHANNELS:
                    self.assertEqual(report["inputs"][slot]["configured_role"], "unknown")
                    self.assertIsNone(report["inputs"][slot]["configured"])
                    self.assertIsNone(report["inputs"][slot]["bluetooth_source_node_seen"])
        self.assertFalse(self.directory.exists())
        self.assertFalse(routes.read_source_report(path=self.file, now=100)[
            "observations_available"])
        self.assertFalse(self.directory.exists())

    def test_source_status_rejects_malformed_unsafe_or_forged_positive_fields(self):
        base = {
            "updated_at": 100,
            "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
        }
        for replacement in (
            {"route_policy_valid": "true"},
            {"source_slot_observations_version": True},
            {"source_slot_observations_version": 2},
            {"source_slot_observations": {}},
            {"source_slot_observations": {"music": {"secret": "bad"}}},
        ):
            with self.subTest(replacement=replacement):
                report = routes.interpret_source_status({**base, **replacement}, now=103)
                self.assertFalse(report["observations_available"])
                self.assertIsNone(report["inputs"]["music"]["configured"])
        invalid = json.loads(json.dumps(base))
        invalid["source_slot_observations"]["music"]["bluetooth_node_observed"] = 1
        self.assertFalse(routes.interpret_source_status(invalid, now=103)[
            "observations_available"])
        invalid2 = json.loads(json.dumps(base))
        invalid2["source_slot_observations"]["music"]["lan_reserved"] = True
        self.assertFalse(routes.interpret_source_status(invalid2, now=103)[
            "observations_available"])

    def test_invalid_route_policy_must_not_assert_assignment_or_audio(self):
        state = {
            "updated_at": 100, "route_policy_valid": False,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
        }
        report = routes.interpret_source_status(state, now=100)
        self.assertTrue(report["fresh"])
        self.assertFalse(report["observations_available"])
        self.assertFalse(report["route_policy_valid"])
        self.assertEqual(report["inputs"]["music"]["configured_role"], "unknown")

    def test_read_report_rejects_unprivate_symlinked_and_bad_json_without_creating(self):
        self.directory.mkdir(mode=0o700)
        secret = self.root / "hidden.json"
        secret.write_text('{"password":"LOCAL-PASSWORD"}')
        self.file.symlink_to(secret)
        out = routes.read_source_report(path=self.file, now=100)
        self.assertFalse(out["observations_available"])
        self.assertNotIn("PASSWORD", json.dumps(out))
        self.file.unlink()
        self.file.write_text('{"updated_at":100,"updated_at":100}')
        self.file.chmod(0o600)
        self.assertFalse(routes.read_source_report(path=self.file, now=100)[
            "observations_available"])
        self.file.write_text('{"updated_at":100}')
        self.file.chmod(0o644)
        self.assertFalse(routes.read_source_report(path=self.file, now=100)[
            "observations_available"])

    def test_anonymized_poll_observations_never_report_unmatched_or_invalid_nodes(self):
        mapping = {"AA:BB:CC:DD:EE:FF": "music"}
        bad_sources = [
            {"address": "11:22:33:44:55:66", "name": "bluez_input.a"},
            {"address": "AA:BB:CC:DD:EE:FF", "name": "../untrusted"},
        ]
        report = runtime.observed_source_slots(
            bad_sources, mapping, {}, {"audiohub.music": 1},
            lan_slot="laptop", policy_valid=True, usb_ready=False)
        self.assertTrue(report["music"]["bluetooth_assigned"])
        self.assertFalse(report["music"]["bluetooth_node_observed"])
        self.assertFalse(report["music"]["managed_loopback_running"])
        self.assertFalse(report["music"]["usb_route_ready"])
        self.assertFalse(report["tablet"]["bluetooth_assigned"])

    def test_invalid_route_policy_suppresses_stale_assignments_and_processes(self):
        mac = "AA:BB:CC:DD:EE:FF"
        report = runtime.observed_source_slots(
            [{"address": mac, "name": "bluez_input.demo"}],
            {mac: "music"},
            {mac: ("bluez_input.demo", "audiohub.music", FakeProcess())},
            {"audiohub.music": 1}, lan_slot="laptop",
            policy_valid=False, usb_ready=False)
        self.assertFalse(report["music"]["bluetooth_assigned"])
        self.assertFalse(report["music"]["bluetooth_node_observed"])
        self.assertFalse(report["music"]["managed_loopback_running"])

    def test_dead_loopback_never_counts_as_running_audio(self):
        mac = "AA:BB:CC:DD:EE:FF"
        report = runtime.observed_source_slots(
            [{"address": mac, "name": "bluez_input.demo"}],
            {mac: "music"},
            {mac: ("bluez_input.demo", "audiohub.music", FakeProcess(False))},
            {"audiohub.music": 1}, lan_slot="laptop",
            policy_valid=True, usb_ready=True)
        self.assertTrue(report["music"]["bluetooth_node_observed"])
        self.assertFalse(report["music"]["managed_loopback_running"])

    def test_source_routes_status_command_is_read_only_and_forbids_write_flags(self):
        expected = routes.interpret_source_status({}, now=100)
        with (mock.patch.object(routes, "read_source_report",
                                return_value=expected) as show,
              mock.patch.object(routes, "update") as writer):
            with redirect_stdout(StringIO()) as out:
                routes.main(["status"])
            self.assertEqual(json.loads(out.getvalue()), expected)
            show.assert_called_once()
            writer.assert_not_called()
        token = "r1-" + "a" * 64
        for args in (["--preview", "status"],
                     ["--confirm-local-route-change", "status"],
                     ["--if-preview-revision", token, "status"]):
            with self.subTest(args=args):
                with (mock.patch.object(routes, "read_source_report") as show,
                      mock.patch.object(routes, "update") as writer):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as failed:
                            routes.main(args)
                    self.assertEqual(failed.exception.code, 2)
                    show.assert_not_called()
                    writer.assert_not_called()

    def test_runtime_poll_writes_observed_slots_but_not_device_identifiers(self):
        from audiohub import runtime as live
        from unittest.mock import Mock
        from audiohub.source_routes import defaults as route_defaults
        mac = "AA:BB:CC:DD:EE:FF"
        supervisor = live.Supervisor.__new__(live.Supervisor)
        supervisor.settings = defaults()
        supervisor.assignments = {mac: "music"}
        supervisor.loopbacks = {mac: ("bluez_input.demo", "audiohub.music", FakeProcess())}
        supervisor.retry_state = {}
        supervisor.route_failures_total = 0
        supervisor.output_switch_failures = 0
        supervisor.last_default = None
        supervisor.route_plan = route_defaults()
        supervisor.route_policy_valid = True
        sources = [{"address": mac, "name": "bluez_input.demo"}]
        sinks = {"audiohub.music": 11, "audiohub.laptop": 12,
                 "audiohub.tablet": 13}
        links = {"inspection_available": True, "links_inspected": 1,
                 "eq_output_to_usb_direct_link": {
                     slot: slot == "music" for slot in CHANNELS}}
        responses = Mock(returncode=0, stdout="[]")
        with (mock.patch.object(live, "run", return_value=responses),
              mock.patch.object(live, "pipewire_nodes", return_value=[]),
              mock.patch.object(live, "summarize_links", return_value=links),
              mock.patch.object(live, "choose_usb_output", return_value={"id": 10}),
              mock.patch.object(live, "bluetooth_sources", return_value=sources),
              mock.patch.object(live, "virtual_sinks", return_value=sinks),
              mock.patch.object(live, "load_routes", return_value=route_defaults()),
              mock.patch.object(live, "read_json", return_value=defaults()),
              mock.patch.object(live, "volume_commands", return_value=[]),
              mock.patch.object(supervisor, "_route"),
              mock.patch.object(live, "atomic_json") as save):
            supervisor.poll()
        save.assert_called_once()
        data = save.call_args.args[1]
        self.assertEqual(data["source_slot_observations_version"], 1)
        self.assertTrue(data["pipewire_graph_inspection_available"])
        self.assertEqual(data["eq_output_usb_direct_links"], ["music"])
        self.assertTrue(data["source_slot_observations"]["music"][
            "bluetooth_node_observed"])
        self.assertTrue(data["source_slot_observations"]["music"][
            "managed_loopback_running"])
        self.assertTrue(data["source_slot_observations"]["laptop"][
            "lan_reserved"])
        self.assertNotIn(mac, json.dumps(data))
        self.assertNotIn("bluez_input.demo", json.dumps(data))




    def _manual_blue_probe_state(self, *, second=False, status_age=100):
        first = "AA:BB:CC:DD:EE:FF"
        routes.bind_bluetooth(first, "music", self.directory)
        if second:
            routes.bind_bluetooth("11:22:33:44:55:66", "tablet", self.directory)
        observations = self.sample()
        if second:
            observations["tablet"]["bluetooth_assigned"] = True
        self.report_file({
            "updated_at": status_age, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": observations,
        })
        return first

    def test_bluez_connected_parser_accepts_only_exact_device_and_one_boolean(self):
        mac = "AA:BB:CC:DD:EE:FF"
        self.assertTrue(routes._bluez_connected_property(
            "Device " + mac + " (public) Name\n    Connected: yes\n", mac))
        self.assertFalse(routes._bluez_connected_property(
            "Device " + mac + "\n\tConnected: no\n", mac))
        for invalid in (
            "Device 11:22:33:44:55:66\n Connected: yes\n",
            "Device " + mac + "\n Connected: yes\nConnected: no\n",
            "Device " + mac + "\n Connected: YES\n",
            "Device " + mac + "\n Connected: yes\nDevice " + mac + "\n",
            "Device " + mac + "\n Connected: yes\nDevice 11:22:33:44:55:66\n",
            "Device " + mac + "\n Paired: yes\n",
            "Device " + mac + "\x00 Connected: yes\n",
            "x" * 4097,
            None,
            11,
        ):
            with self.subTest(invalid=str(invalid)[:25]):
                self.assertIsNone(routes._bluez_connected_property(invalid, mac))

    def test_bluez_probe_two_manual_slots_reports_true_and_false_without_identifiers(self):
        from subprocess import CompletedProcess
        self._manual_blue_probe_state(second=True)
        before_policy = (self.directory / routes.FILENAME).read_bytes()
        before_status = self.file.read_bytes()
        calls = []
        def runner(argv, *, timeout, max_bytes):
            calls.append(argv)
            self.assertEqual(argv[:2], ("bluetoothctl", "info"))
            self.assertEqual(timeout, 3)
            self.assertEqual(max_bytes, 4096)
            response = "yes" if argv[2] == "AA:BB:CC:DD:EE:FF" else "no"
            return CompletedProcess(argv, 0,
                                    "Device " + argv[2] + "\n    Connected: "
                                    + response + "\n", "")
        with (mock.patch.object(routes, "bounded_command_output",
                                side_effect=runner),
              mock.patch.object(routes, "update") as writer):
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=102)
            writer.assert_not_called()
        self.assertEqual(report["bluez_probe"], "manual_assignments_queried")
        self.assertTrue(report["inputs"]["music"]["bluez_connected_property"])
        self.assertFalse(report["inputs"]["tablet"]["bluez_connected_property"])
        self.assertIsNone(report["inputs"]["laptop"]["bluez_connected_property"])
        self.assertEqual(report["inputs"]["music"]["bluetooth_connected"], "unverified")
        self.assertEqual(report["inputs"]["music"]["audio_stream_available"], "unverified")
        self.assertEqual(report["inputs"]["music"]["audible_playback"], "unverified")
        self.assertEqual(len(calls), 2)
        self.assertEqual((self.directory / routes.FILENAME).read_bytes(),
                         before_policy)
        self.assertEqual(self.file.read_bytes(), before_status)
        self.assertNotIn("AA:BB:CC", json.dumps(report))
        self.assertNotIn("11:22:33", json.dumps(report))

    def test_bluez_probe_fails_closed_when_transport_cannot_be_read(self):
        from subprocess import CompletedProcess
        self._manual_blue_probe_state()
        with mock.patch.object(routes, "bounded_command_output",
                               return_value=CompletedProcess(
                                   ["bluetoothctl"], 1, "Connected: yes", "SECRET")):
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=105)
        self.assertEqual(report["bluez_probe"], "manual_assignments_queried")
        self.assertIsNone(report["inputs"]["music"]["bluez_connected_property"])
        self.assertNotIn("SECRET", json.dumps(report))
        with mock.patch.object(routes, "bounded_command_output", return_value=None):
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=105)
        self.assertIsNone(report["inputs"]["music"]["bluez_connected_property"])

    def test_bluez_probe_never_calls_bluetoothctl_for_stale_runtime(self):
        self._manual_blue_probe_state(status_age=100)
        with mock.patch.object(routes, "bounded_command_output") as call:
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=131)
            call.assert_not_called()
        self.assertEqual(report["bluez_probe"], "runtime_evidence_unavailable")
        self.assertFalse(report["observations_available"])

    def test_bluez_probe_auto_mode_does_not_assume_current_device_assignments(self):
        self.report_file({
            "updated_at": 100, "route_policy_valid": True,
            "source_slot_observations_version": 1,
            "source_slot_observations": self.sample(),
        })
        with mock.patch.object(routes, "bounded_command_output") as call:
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=102)
            call.assert_not_called()
        self.assertEqual(report["bluez_probe"], "automatic_assignments_not_probed")
        self.assertIsNone(report["inputs"]["music"]["bluez_connected_property"])

    def test_bluez_probe_refuses_mismatched_policy_and_runtime_mappings(self):
        self._manual_blue_probe_state(second=True)
        report_data = runtime.read_json(self.file, {})
        report_data["source_slot_observations"]["tablet"][
            "bluetooth_assigned"] = False
        self.report_file(report_data)
        with mock.patch.object(routes, "bounded_command_output") as call:
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=102)
            call.assert_not_called()
        self.assertEqual(report["bluez_probe"], "runtime_policy_mismatch")
        self.assertIsNone(report["inputs"]["music"]["bluez_connected_property"])

    def test_bluez_probe_discards_results_after_policy_aba_replacement(self):
        from subprocess import CompletedProcess
        self._manual_blue_probe_state()
        def replacing(argv, *, timeout, max_bytes):
            routes.update(lambda current: dict(current), self.directory)
            return CompletedProcess(argv, 0,
                                    "Device " + argv[2] + "\n Connected: yes\n", "")
        with mock.patch.object(routes, "bounded_command_output",
                               side_effect=replacing):
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=102)
        self.assertEqual(report["bluez_probe"], "policy_changed_during_probe")
        self.assertIsNone(report["inputs"]["music"]["bluez_connected_property"])

    def test_bluez_probe_unsafe_private_policy_is_unknown_and_never_queried(self):
        self._manual_blue_probe_state()
        path = self.directory / routes.FILENAME
        path.chmod(0o644)
        with mock.patch.object(routes, "bounded_command_output") as call:
            report = routes.probe_bluez_connections(
                directory=self.directory, status_path=self.file, now=102)
            call.assert_not_called()
        self.assertEqual(report["bluez_probe"], "policy_unavailable")
        self.assertIsNone(report["inputs"]["music"]["bluez_connected_property"])

    def test_bluez_probe_status_flag_is_local_read_only_and_not_implicit(self):
        expected = routes.interpret_source_status({}, now=100)
        expected["bluez_probe"] = "manual_assignments_queried"
        with (mock.patch.object(routes, "probe_bluez_connections",
                                return_value=expected) as probe,
              mock.patch.object(routes, "update") as writer):
            with redirect_stdout(StringIO()) as out:
                routes.main(["--probe-bluetooth", "status"])
            self.assertEqual(json.loads(out.getvalue()), expected)
            probe.assert_called_once_with()
            writer.assert_not_called()
        for args in (
            ["--probe-bluetooth", "slots"],
            ["--probe-bluetooth", "show"],
            ["--probe-bluetooth", "mode", "manual"],
            ["--probe-bluetooth", "set-lan", "music"],
            ["--probe-bluetooth", "--preview", "status"],
            ["--probe-bluetooth", "--confirm-local-route-change", "status"],
        ):
            with self.subTest(args=args):
                with (mock.patch.object(routes, "bounded_command_output") as query,
                      mock.patch.object(routes, "update") as write):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as rejected:
                            routes.main(args)
                    self.assertEqual(rejected.exception.code, 2)
                    query.assert_not_called()
                    write.assert_not_called()
