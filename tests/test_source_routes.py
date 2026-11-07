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
from audiohub import source_routes as routes


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
