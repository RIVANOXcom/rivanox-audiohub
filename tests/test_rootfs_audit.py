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
        make("opt/audiohub/src/audiohub/runtime.py", "\\n".join((
            '("music", "tablet")',
            '"--capture", source',
            '"--playback", "audiohub." + channel',
            'usb_ready = bool(selected and selected.returncode == 0)',
            'self._route(sources, sinks if usb_ready else {})',
        )))
        make("etc/wireplumber/wireplumber.conf.d/90-audiohub.conf", "\\n".join((
            "bluez5.roles = [ a2dp_sink ]",
            'node.name = "~bluez_input.*"',
            "bluez5.media-source-role = input",
            "monitor.bluez.rules = [",
        )))
        make("opt/audiohub/src/audiohub/mixer.py", "\\n".join((
            "def mix_gain_budget(settings):",
            "def effective_master_gain(settings):",
            "return min(1.0, 1.0 / worst_case)",
            "str(effective_master_gain(settings))",
        )))
        audio_runtime = root / "opt/audiohub/src/audiohub/runtime.py"
        audio_runtime.write_text(audio_runtime.read_text() +
            '\\neffective_master_gain(self.settings)\\n"effective_master_percent"\\n')
        make("opt/audiohub/src/audiohub/network_laptop.py", "\\n".join((
            'TARGET = "audiohub.laptop"',
            '"--target=" + TARGET',
            "validate_options(sender_ip, bind_ip, port, unsafe_lan_test)",
            'parser.add_argument("--unsafe-lan-test", action="store_true"',
            '"10.0.0.0/8"',
        )))
        make("opt/audiohub/src/audiohub/network_buffer.py", "\\n".join((
            "MAX_BUFFER_PACKETS = 16",
            "MAX_PCM_PACKET_BYTES = 1152",
            "self._packets.popleft()",
        )))
        make("opt/audiohub/src/audiohub/input_profiles.py", "\\n".join((
            'SLOTS = ("music", "laptop", "tablet")',
            "MAX_NAME_CHARS = 32",
            "O_NOFOLLOW",
            "fcntl.flock",
        )))
        make("opt/audiohub/src/audiohub/status_bind.py",
             'LOOPBACK = "127.0.0.1"\\n'
             'values.get("AUDIOHUB_STATUS_BIND_IP", LOOPBACK)\\n'
             'values.get("AUDIOHUB_UNSAFE_STATUS_LAN") != "YES"\\n')
        make("opt/audiohub/src/audiohub/webserver.py",
             "from .status_bind import select_bind_address\\n"
             "ThreadingHTTPServer((select_bind_address(), 8765), Handler)\\n"
             "def do_POST(self):\\nRead-only preview\\n")
        make("opt/audiohub/src/audiohub/firstboot_diag.py",
             'OUTPUT_NAME = "AUDIOHUB-TEST-REPORT.json"')
        for name in ("index.html", "app.js", "styles.css"):
            make("opt/audiohub/web/" + name)
        make("opt/audiohub/web/app.js", "\\n".join((
            "audiohub.preview.input-labels.v1",
            "localStorage.setItem",
            "nameInput.addEventListener",
        )))
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

    def test_missing_bluetooth_input_role_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            conf = root / "etc/wireplumber/wireplumber.conf.d/90-audiohub.conf"
            conf.write_text(conf.read_text().replace(
                "bluez5.media-source-role = input", "bluez5.media-source-role = playback"
            ))
            self.assertFalse(audit.inspect(root)["bluetooth_input_role_configured"])

    def test_missing_usb_gate_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/runtime.py"
            source.write_text(source.read_text().replace(
                'self._route(sources, sinks if usb_ready else {})',
                'self._route(sources, sinks)'
            ))
            self.assertFalse(audit.inspect(root)["managed_eq_routing_and_usb_gate"])

    def test_missing_wireplumber_config_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "etc/wireplumber/wireplumber.conf.d/90-audiohub.conf").unlink()
            self.assertFalse(audit.inspect(root)["bluetooth_input_role_configured"])

    def test_missing_gain_budget_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            mixer = root / "opt/audiohub/src/audiohub/mixer.py"
            mixer.write_text(mixer.read_text().replace(
                "str(effective_master_gain(settings))", "str(settings['master'])"
            ))
            self.assertFalse(audit.inspect(root)["conservative_mix_gain_installed"])

    def test_missing_effective_master_diagnostics_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            runtime = root / "opt/audiohub/src/audiohub/runtime.py"
            runtime.write_text(runtime.read_text().replace(
                "effective_master_gain(self.settings)", "self.settings['master']"
            ))
            self.assertFalse(audit.inspect(root)["conservative_mix_gain_installed"])

    def test_missing_dormant_windows_receiver_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/src/audiohub/network_laptop.py").unlink()
            checks = audit.inspect(root)
            self.assertFalse(checks["source_network_laptop.py"])
            self.assertFalse(checks["laptop_manual_receiver_packaged"])

    def test_missing_receiver_optin_guard_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/network_laptop.py"
            source.write_text(source.read_text().replace(
                'validate_options(sender_ip, bind_ip, port, unsafe_lan_test)',
                'sender_ip, bind_ip, port'
            ))
            self.assertFalse(audit.inspect(root)["laptop_manual_receiver_packaged"])

    def test_unsafe_network_receiver_service_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            bad = root / "etc/systemd/system/audiohub-laptop.service"
            bad.write_text(
                "[Service]\\nExecStart=/usr/bin/python3 -m "
                "audiohub.network_laptop --unsafe-lan-test\\n"
            )
            self.assertFalse(audit.inspect(root)["laptop_receiver_not_autostarted"])

    def test_bounded_laptop_buffer_required_for_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            buf = root / "opt/audiohub/src/audiohub/network_buffer.py"
            buf.write_text(buf.read_text().replace(
                "MAX_BUFFER_PACKETS = 16", "MAX_BUFFER_PACKETS = 65536"
            ))
            self.assertFalse(audit.inspect(root)["laptop_manual_receiver_packaged"])

    def test_missing_input_names_model_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/src/audiohub/input_profiles.py").unlink()
            self.assertFalse(audit.inspect(root)["editable_names_offline_no_public_api"])

    def test_missing_client_only_rename_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/web/app.js").write_text("display only")
            self.assertFalse(audit.inspect(root)["editable_names_offline_no_public_api"])

    def test_nonread_only_web_api_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            web = root / "opt/audiohub/src/audiohub/webserver.py"
            web.write_text(web.read_text().replace("Read-only preview", "owner write API"))
            self.assertFalse(audit.inspect(root)["editable_names_offline_no_public_api"])

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
