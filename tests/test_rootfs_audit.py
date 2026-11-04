"""Pre-export image root filesystem checks fail closed before publishing an artifact."""
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_rootfs.py"
spec = importlib.util.spec_from_file_location("audit_rootfs", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class RootfsAuditTests(unittest.TestCase):
    def root(self, base):
        root = Path(base)
        def make(path, content="OK"):
            file = root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        for name in ("__init__.py", "runtime.py", "pairing.py", "mixer.py", "webserver.py"):
            make("opt/audiohub/src/audiohub/" + name)
        for name in ("index.html", "app.js", "styles.css"):
            make("opt/audiohub/web/" + name)
        data = {f"k{n}": "test" for n in range(30)}
        for lang in audit.LANGUAGES:
            make(f"opt/audiohub/web/locales/{lang}.json", json.dumps(data))
        make("etc/passwd", "audiohub:x:1000:1000::/home/audiohub:/bin/bash\n")
        for name, (unit_path, link_path, command) in audit.SERVICES.items():
            make(unit_path, "[Service]\nExecStart=/usr/bin/" + command + "\nRestart=always\nNoNewPrivileges=yes\n")
            link = root / link_path
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to("../" + Path(unit_path).name)
        make("var/lib/systemd/linger/audiohub", "")
        for executable in audit.REQUIRED_BINARIES:
            make("usr/bin/" + executable)
        config = "\n".join(
            'name = libpipewire-module-filter-chain\n node.name = "audiohub.' + channel + '"'
            for channel in audit.CHANNELS
        )
        make("home/audiohub/.config/pipewire/pipewire.conf.d/90-audiohub-eq.conf", config)
        return root

    def test_valid_synthetic_rootfs_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(all(audit.inspect(self.root(tmp)).values()))

    def test_absolute_systemd_symlink_resolves_inside_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            link = root / audit.SERVICES["bluetooth"][1]
            link.unlink()
            link.symlink_to("/" + audit.SERVICES["bluetooth"][0])
            self.assertTrue(audit.inspect(root)["bluetooth_enabled"])

    def test_broken_absolute_symlink_is_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            link = root / audit.SERVICES["bluetooth"][1]
            link.unlink()
            link.symlink_to("/etc/systemd/system/nonexistent.service")
            self.assertFalse(audit.inspect(root)["bluetooth_enabled"])

    def test_missing_eq_fails_closed_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "home/audiohub/.config/pipewire/pipewire.conf.d/90-audiohub-eq.conf").unlink()
            self.assertNotEqual(audit.run(root), 0)
            report = json.loads((root / "usr/share/doc/audiohub/rootfs-preflight.json").read_text())
            self.assertFalse(report["passed"])
            self.assertIn("independent_eq_virtual_sinks", report["failed_checks"])

    def test_ssh_enabled_is_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            make = root / "etc/systemd/system/multi-user.target.wants/ssh.service"
            make.parent.mkdir(parents=True, exist_ok=True)
            make.write_text("service")
            self.assertFalse(audit.inspect(root)["ssh_not_autostarted"])

    def test_untranslated_resource_is_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/web/locales/fr.json").write_text('{"incomplete":"yes"}')
            self.assertFalse(audit.inspect(root)["locale_fr"])

    def test_no_world_writable_eq_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            eq = root / "home/audiohub/.config/pipewire/pipewire.conf.d/90-audiohub-eq.conf"
            eq.chmod(0o666)
            self.assertFalse(audit.inspect(root)["eq_not_world_writable"])


if __name__ == "__main__":
    unittest.main()
