"""Private AudioHub channel label model and source UI regression tests."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from audiohub import input_profiles as p

class InputProfiles(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"audiohub"

    def test_generic_defaults(self):
        self.assertEqual(p.load_labels(self.root),
            {"music":"Input 1","laptop":"Input 2","tablet":"Input 3"})

    def test_names_persist_on_private_console(self):
        p.set_label("music","Wohnzimmer-TV",self.root)
        p.set_label("laptop","Konsole & PC",self.root)
        p.set_label("tablet","Café 🎵",self.root)
        self.assertEqual(p.load_labels(self.root)["laptop"],"Konsole & PC")

    def test_rejects_bad_names(self):
        for value in (""," ", "X"*33, "<script>", "A>B",
                      "line\nname", "a\u202eb", None, True, []):
            with self.subTest(value=repr(value)),self.assertRaises(ValueError):
                p.validate_name(value)

    def test_duplicate_names_rejected(self):
        p.set_label("music","TV",self.root)
        with self.assertRaises(ValueError):
            p.set_label("laptop","tv",self.root)

    def test_unknown_channel_denied(self):
        with self.assertRaises(ValueError):
            p.set_label("evil","New",self.root)

    def test_private_atomic_storage(self):
        p.set_label("music","TV",self.root)
        f=self.root/p.FILENAME
        self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode),0o700)
        p.set_label("music","Console",self.root)
        self.assertEqual(p.load_labels(self.root)["music"],"Console")

    def test_corruption_fails_closed(self):
        p.set_label("music","TV",self.root)
        f=self.root/p.FILENAME
        f.write_text("invalid!")
        with self.assertRaises(ValueError):
            p.load_labels(self.root)
        with self.assertRaises(ValueError):
            p.set_label("tablet","Radio",self.root)
        self.assertEqual(f.read_text(),"invalid!")

    def test_ancestor_symlink_rejected_for_private_label_read_and_write(self):
        real = self.root.parent / "actual"
        real.mkdir()
        safe = real / "config"
        p.set_label("music", "Original", safe)
        before = (safe / p.FILENAME).read_bytes()
        (self.root.parent / "linked").symlink_to(real, target_is_directory=True)
        redirected = self.root.parent / "linked" / "config"
        with self.assertRaises(OSError):
            p.load_labels(redirected)
        with self.assertRaises(OSError):
            p.set_label("music", "Altered", redirected)
        self.assertEqual((safe / p.FILENAME).read_bytes(), before)

    def test_ancestor_symlink_cannot_create_new_profile_directory(self):
        real = self.root.parent / "actual"
        real.mkdir()
        (self.root.parent / "linked").symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            p.set_label("music", "Altered", self.root.parent / "linked" / "new")
        self.assertFalse((real / "new").exists())

    def test_profile_parent_traversal_denied_before_creation(self):
        with self.assertRaises(ValueError):
            p.set_label("music", "Altered", self.root.parent / "nested" / ".." / "new")
        self.assertFalse((self.root.parent / "new").exists())

    def test_nested_regular_profile_directories_still_work(self):
        folder = self.root.parent / "regular" / "nested" / "config"
        p.set_label("tablet", "Tablet", folder)
        self.assertEqual(p.load_labels(folder)["tablet"], "Tablet")

    def test_symlink_and_world_readable_rejected(self):
        self.root.mkdir(mode=0o700)
        path=self.root/p.FILENAME
        external=self.root.parent/"outside"
        external.write_text("secret")
        path.symlink_to(external)
        with self.assertRaises(OSError):
            p.load_labels(self.root)
        self.assertEqual(external.read_text(),"secret")
        path.unlink()
        p.set_label("music","TV",self.root)
        path.chmod(0o644)
        with self.assertRaises(PermissionError):
            p.load_labels(self.root)

    def test_duplicate_private_profile_fields_are_refused_without_reset(self):
        p.set_label("music", "TV", self.root)
        path = self.root / p.FILENAME
        ambiguous = (
            '{"schema":"audiohub-input-labels/1","labels":{'
            '"music":"Display 1","music":"Display 2",'
            '"laptop":"Display 3","tablet":"Display 4"}}'
        )
        path.write_text(ambiguous)
        with self.assertRaises(ValueError):
            p.load_labels(self.root)
        with self.assertRaises(ValueError):
            p.set_label("music", "Changed", self.root)
        self.assertEqual(path.read_text(), ambiguous)

    def test_duplicate_root_profile_schema_rejected(self):
        p.set_label("music", "TV", self.root)
        path = self.root / p.FILENAME
        path.write_text(
            '{"schema":"outdated","schema":"audiohub-input-labels/1",'
            '"labels":{"music":"TV","laptop":"PC","tablet":"Phone"}}'
        )
        with self.assertRaises(ValueError):
            p.load_labels(self.root)

    def test_nested_profile_json_recursion_returns_controlled_value_error(self):
        p.set_label("music", "TV", self.root)
        path = self.root / p.FILENAME
        document = "[" * 1010 + "0" + "]" * 1010
        self.assertLess(len(document), p.MAX_BYTES)
        path.write_text(document)
        with self.assertRaises(ValueError):
            p.load_labels(self.root)

    def test_profile_fifo_never_blocks_before_regular_file_validation(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("Linux FIFO needed")
        self.root.mkdir(mode=0o700)
        os.mkfifo(self.root / p.FILENAME)
        original_open = os.open

        def guarded_open(path, flags, *args, **kwargs):
            if path == p.FILENAME:
                self.assertTrue(flags & os.O_NONBLOCK, "FIFO must not block")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(p.os, "open", side_effect=guarded_open):
            with self.assertRaises(PermissionError):
                p.load_labels(self.root)

    def test_short_profile_read_fails_closed(self):
        p.set_label("music", "TV", self.root)
        with mock.patch.object(p.os, "read", return_value=b"{}"):
            with self.assertRaises(ValueError):
                p.load_labels(self.root)

    def test_web_remains_preview_without_post_api(self):
        js=(ROOT/"web/app.js").read_text()
        self.assertIn("audiohub.preview.input-labels.v1",js)
        self.assertIn("localStorage.setItem",js)
        self.assertIn("nameInput.addEventListener",js)
        self.assertNotIn("innerHTML",js)
        self.assertNotIn('method: "POST"',js)

    def test_five_locales_have_all_inputs(self):
        keys={"input1","input2","input3","inputName",
              "sourceHint1","sourceHint2","sourceHint3",
              "invalidInputName","previewNamesOnly"}
        for code in ("en","de","es","fr","it"):
            data=json.loads((ROOT/"web/locales"/(code+".json")).read_text())
            self.assertTrue(keys.issubset(data),code)

if __name__=="__main__":
    unittest.main()
