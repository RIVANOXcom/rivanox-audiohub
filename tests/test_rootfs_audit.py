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
        for name in ("__init__.py", "runtime.py", "pairing.py", "mixer.py"):
            make("opt/audiohub/src/audiohub/" + name)
        make("opt/audiohub/src/audiohub/status_bind.py",
             'LOOPBACK = "127.0.0.1"\\n'
             'values.get("AUDIOHUB_STATUS_BIND_IP", LOOPBACK)\\n'
             'values.get("AUDIOHUB_UNSAFE_STATUS_LAN") != "YES"\\n')
        make("opt/audiohub/src/audiohub/webserver.py",
             "from .status_bind import select_bind_address\\n"
             "ThreadingHTTPServer((select_bind_address(), 8765), Handler)\\n")
        make("opt/audiohub/src/audiohub/firstboot_diag.py",
             'OUTPUT_NAME = "AUDIOHUB-TEST-REPORT.json"')
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
        diag_unit = "etc/systemd/system/audiohub-firstboot-diag.service"
        make(diag_unit, (
            "[Unit]\\nConditionPathIsMountPoint=/boot/firmware\\n"
            "[Service]\\nExecStart=/usr/bin/python3 -m audiohub.firstboot_diag\\n"
            "PrivateNetwork=yes\\nNoNewPrivileges=yes\\nProtectSystem=strict\\n"
            "ReadWritePaths=/boot/firmware\\n"
        ))
        enabled = root / (
            "etc/systemd/system/multi-user.target.wants/audiohub-firstboot-diag.service"
        )
        enabled.parent.mkdir(parents=True, exist_ok=True)
        enabled.symlink_to("../audiohub-firstboot-diag.service")
        make("var/lib/systemd/linger/audiohub", "")
        for executable in audit.REQUIRED_BINARIES:
            make("usr/bin/" + executable)
        config = "\n".join(
            'name = libpipewire-module-filter-chain\n node.name = "audiohub.' + channel + '"'
            for channel in audit.CHANNELS
        )
        make("home/audiohub/.config/pipewire/pipewire.conf.d/90-audiohub-eq.conf", config)
        return root

    def test_unchecked_status_web_listener_prevents_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            web = root / "opt/audiohub/src/audiohub/webserver.py"
            web.write_text('ThreadingHTTPServer(("0.0.0.0", 8765), Handler)\\n')
            self.assertFalse(audit.inspect(root)["status_web_uses_guarded_bind"])
            self.assertNotEqual(audit.run(root), 0)

    def test_missing_status_bind_policy_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/src/audiohub/status_bind.py").unlink()
            checks = audit.inspect(root)
            self.assertFalse(checks["status_loopback_default"])
            self.assertFalse(checks["source_status_bind.py"])

    def test_service_unsafe_lan_opt_in_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            service = root / audit.SERVICES["status"][0]
            service.write_text(
                service.read_text() + "Environment=AUDIOHUB_UNSAFE_STATUS_LAN=YES\\n"
            )
            self.assertFalse(audit.inspect(root)["status_service_no_unsafe_lan_opt_in"])

    def test_missing_offline_diag_agent_fails_image_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/src/audiohub/firstboot_diag.py").unlink()
            self.assertFalse(audit.inspect(root)["source_firstboot_diag.py"])
            self.assertFalse(audit.inspect(root)["offline_diag_no_network_clients"])

    def test_offline_diag_must_not_enable_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            unit = root / "etc/systemd/system/audiohub-firstboot-diag.service"
            unit.write_text(unit.read_text().replace("PrivateNetwork=yes", "PrivateNetwork=no"))
            self.assertFalse(audit.inspect(root)["offline_diag_unit_sandboxed"])

    def test_offline_diag_must_be_enabled_in_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            link = root / (
                "etc/systemd/system/multi-user.target.wants/audiohub-firstboot-diag.service"
            )
            link.unlink()
            self.assertFalse(audit.inspect(root)["offline_diag_enabled"])

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
