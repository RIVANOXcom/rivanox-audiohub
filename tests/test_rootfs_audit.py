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
        make("opt/audiohub/src/audiohub/pairing.py", "\n".join((
            "AUTHORIZATION_TTL = 45",
            "def authorized_pairing_signal(",
            "def authorize_pending(self, device):",
            "def changed(self, interface, change, invalidated, path=None):",
            "self.pending_authorizations.pop(path, None)",
            'if ((invalidated and "Paired" in invalidated)',
            'or ("Paired" in change and not change["Paired"])):',
            'if not change.get("Paired"):',
            'bus_name="org.bluez"',
            'device.Get("org.bluez.Device1", "Paired")',
            "if not self.allowed() or not (",
            'raise Rejected("Untrusted device")',
            "self.authorize_pending(device)",
            "self.deadline = float(BOOT_WINDOW)",
            'self.adapter.Set("org.bluez.Adapter1", "PairableTimeout", dbus.UInt32(BOOT_WINDOW))',
            'self.adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(BOOT_WINDOW))',
            'self.adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(False))',
            'self.adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(False))',
            "@dbus.service.method",
            "def Cancel(self):",
            "# BlueZ canceled the current agent request;",
            "self.pending_authorizations.clear()",
            "def main():",
        )))
        make("opt/audiohub/src/audiohub/runtime.py", "\\n".join((
            "channel not in CHANNELS",
            '"--capture", source',
            '"--playback", "audiohub." + channel',
            'usb_ready = bool(selected and selected.returncode == 0)',
            "    def poll(self):",
            "for args in volume_commands(",
            "applied = run(*args)",
            "if applied is None or applied.returncode != 0:",
            'raise RuntimeError("AudioHub mixer control failed")',
            "self._stop_all_managed_routes()",
            'self._route(sources if self.route_policy_valid else [],'
            'sinks if (usb_ready and self.route_policy_valid) else {})',
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
            "def volume_commands(settings, sink_ids, output_id=None):",
            "if output_id is not None:",
            "for channel in CHANNELS:",
        )))
        # Minimum installed runtime private-state read/write safety markers.
        runtime_path = root / "opt/audiohub/src/audiohub/runtime.py"
        runtime_path.write_text(runtime_path.read_text() + "\n".join((
            "MAX_RUNTIME_JSON_BYTES = 32 * 1024",
            "MAX_RUNTIME_JSON_DEPTH = 64",
            "MAX_RUNTIME_JSON_VALUES = 8192",
            "def _unique_state_json_members(pairs):",
            "object_pairs_hook=_unique_state_json_members",
            "parse_constant=_reject_state_json_constant",
            "parse_float=_finite_state_json_float",
            "math.isfinite(value)",
            "def _private_state_shape_bounded(data):",
            "not _private_state_shape_bounded(value)",
            "except (OSError, ValueError, TypeError, UnicodeError, RecursionError):",
            "def _private_parent_fd(path, *, create=False):",
            "os.O_NOFOLLOW", "os.O_NONBLOCK",
            "os.O_EXCL", "secrets.token_hex(12)",
            "stat.S_ISREG", "os.replace(name, path.name",
            "os.fsync(dirfd)",
            "def _stop_all_managed_routes(self):",
            "def poll_safely(self):",
            "self._stop_all_managed_routes()",
            "self.poll_safely()",
            "from .process_capture import bounded_command_output",
            "bounded_command_output(args, timeout=timeout)",
        )))
        audio_runtime = root / "opt/audiohub/src/audiohub/runtime.py"
        audio_runtime.write_text(audio_runtime.read_text() +
            '\\neffective_master_gain(self.settings)\\n"effective_master_percent"\\n'
            'load_routes(CONFIG)\\nplan["mode"] == "manual"\\n'
            'channel != getattr(self, "route_plan", default_routes())["lan_slot"]\\n'
            'self.route_policy_valid = False\\n'
            'summarize_links(result.stdout\\n'
            '"eq_output_usb_direct_links"\\n'
            '"pipewire_links_inspected"\\n')
        make("opt/audiohub/src/audiohub/network_laptop.py", "\\n".join((
            'TARGET = "audiohub.laptop"',
            '"--target=" + target',
            "target = lan_target()",
            "if lan_target() != target:",
            "check_audio_target(target)",
            "player_command(target)",
            "validate_options(sender_ip, bind_ip, port, unsafe_lan_test)",
            'parser.add_argument("--unsafe-lan-test", action="store_true"',
            '"10.0.0.0/8"',
            "from .process_capture import bounded_command_output",
            'bounded_command_output(("pw-dump",), timeout=5)',
            '("wpctl", "set-default", str(output["id"])), timeout=5,',
            "if result is None or result.returncode != 0:",
            "if selected is None or selected.returncode != 0:",
        )))
        make("opt/audiohub/src/audiohub/network_buffer.py", "\\n".join((
            "MAX_BUFFER_PACKETS = 16",
            "MAX_PCM_PACKET_BYTES = 1152",
            "self._packets.popleft()",
        )))
        make("opt/audiohub/src/audiohub/source_routes.py", "\\n".join((
            'FILENAME = "source-routes.json"',
            'MAX_FILE_BYTES = 4096',
            'os.O_NOFOLLOW',
            'fcntl.flock',
            'if slot in used:',
            'def lan_target(directory=None):',
            "os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW",
            "if len(raw) != st.st_size:",
            "object_pairs_hook=_unique_route_members",
            "parse_constant=_reject_route_constant",
            "except (UnicodeError, ValueError, RecursionError):",
            'dirfd = os.open("/", flags)',
            'for component in path.parts[1:]:',
            'nextfd = os.open(component, flags, dir_fd=dirfd)',
            'if ".." in path.parts:',
            'os.mkdir(component, mode=0o700, dir_fd=dirfd)',
            'if dirfd is not None:',
        )))
        make("opt/audiohub/src/audiohub/audio_graph.py", "\\n".join((
            "_parse_pipewire_graph,",
            "graph = _parse_pipewire_graph(raw)",
            "def summarize_links(raw):"
            "_conflicting_node_ids(nodes)",
            '"PipeWire:Interface:Link"',
            '"output-node-id"',
            '"input-node-id"',
            '"release_ready": False',
        )))
        make("opt/audiohub/src/audiohub/manual_acceptance.py", "\\n".join((
            'from .hardware_preflight import probe',
            '"hardware_accepted": False',
            '"ownership_authenticated": False',
            '"legal_redistribution_approved": False',
            '"model_c_license_effective": False',
            '"release_ready": False',
            '"persisted": False',
            '"operator_observations": observations',
            'MAX_INPUT_ATTEMPTS = 3',
        )))
        make("opt/audiohub/src/audiohub/hardware_preflight.py",
             'from .audio_graph import summarize_links\\n'
             'bounded_command_output(("pw-dump",), timeout=5)\\n'
             '_conflicting_node_ids(nodes)')
        make("opt/audiohub/src/audiohub/process_capture.py", "\\n".join((
            "MAX_COMMAND_STDOUT_BYTES = 4 * 1024 * 1024",
            "selectors.DefaultSelector()",
            "max_bytes + 1 - len(output)",
            "start_new_session=True",
            "shell=False",
            "os.killpg(",
            "stderr=subprocess.DEVNULL",
        )))
        make("opt/audiohub/src/audiohub/discovery.py", "\\n".join((
            "MAX_PIPEWIRE_GRAPH_BYTES = 4 * 1024 * 1024",
            "MAX_PIPEWIRE_GRAPH_OBJECTS = 8192",
            "MAX_PIPEWIRE_JSON_DEPTH = 64",
            "MAX_PIPEWIRE_GRAPH_VALUES = 262144",
            "def _pipewire_graph_shape_bounded(data):",
            "if len(item) + len(todo) + seen > MAX_PIPEWIRE_GRAPH_VALUES:",
            "return raw if _pipewire_graph_shape_bounded(raw) else None",
            "def _unique_pipewire_members(pairs):",
            "object_pairs_hook=_unique_pipewire_members",
            "parse_constant=_reject_pipewire_constant",
            "parse_float=_finite_pipewire_float",
            "math.isfinite(value)",
            "except (UnicodeError, TypeError, ValueError, RecursionError):",
            "data = _parse_pipewire_graph(raw)",
            "def _conflicting_node_ids(nodes):"
            "if ident in seen:",
            "if _conflicting_node_ids(nodes):",
            "conflicted.add(name_mac)",
            'return [source for source in result if source["address"] not in conflicted]',
            "ambiguous.add(name)",
            "return {} if ambiguous else found",
        )))
        make("opt/audiohub/src/audiohub/input_profiles.py", "\\n".join((
            'SLOTS = ("music", "laptop", "tablet")',
            "MAX_NAME_CHARS = 32",
            "O_NOFOLLOW",
            "fcntl.flock",
            "os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW",
            "if len(data) != meta.st_size:",
            "object_pairs_hook=_unique_profile_members",
            "parse_constant=_reject_profile_constant",
            "except (UnicodeError, ValueError, RecursionError):",
            'dirfd = os.open("/", flags)',
            'for component in path.parts[1:]:',
            'nextfd = os.open(component, flags, dir_fd=dirfd)',
            'if ".." in path.parts:',
            'os.mkdir(component, mode=0o700, dir_fd=dirfd)',
            'if dirfd is not None:',
            "dirfd = _safe_dir(directory, create=True)",
        )))
        make("opt/audiohub/src/audiohub/status_bind.py",
             'LOOPBACK = "127.0.0.1"\\n'
             'values.get("AUDIOHUB_STATUS_BIND_IP", LOOPBACK)\\n'
             'values.get("AUDIOHUB_UNSAFE_STATUS_LAN") != "YES"\\n')
        make("opt/audiohub/src/audiohub/webserver.py",
             "from .status_bind import select_bind_address\\n"
             "BoundedStatusHTTPServer((select_bind_address(), 8765), Handler)\\n"
             "def do_POST(self):\\nRead-only preview\\n"
             "STATIC_MAX_BYTES = 512 * 1024\\n"
             "STATUS_MAX_BYTES = 32 * 1024\\n"
             "os.O_NOFOLLOW\\nos.O_NONBLOCK\\nstat.S_ISREG\\n"
             "read_public_status()\\n"
            "MAX_STATUS_CLIENTS = 8\\n"
            "CLIENT_READ_TIMEOUT_SECONDS = 5\\n"
            "class BoundedStatusHTTPServer(ThreadingHTTPServer):\\n"
            "threading.BoundedSemaphore(MAX_STATUS_CLIENTS)\\n"
            "self._client_slots.acquire(blocking=False)\\n"
            "self.shutdown_request(request)\\n"
            "def process_request_thread(self, request, client_address):\\n"
            "self._client_slots.release()\\n"
            "conn.settimeout(CLIENT_READ_TIMEOUT_SECONDS)\\n"
            "def log_message(self, format, *args):\\n"
            "server = BoundedStatusHTTPServer(\\n"
             "def _bounded_regular_bytes(path, limit, *, private_owner=None):\\n"
             "parent.st_uid != private_owner\\n"
             "stat.S_IMODE(parent.st_mode) & 0o077\\n"
             "info.st_uid != private_owner\\n"
             "info.st_nlink != 1\\n"
             "stat.S_IMODE(info.st_mode) & 0o077\\n"
             "private_owner=os.geteuid()\\n"
             "_bounded_regular_bytes(WEBROOT / filename, STATIC_MAX_BYTES)\\n")
        web_fixture = root / "opt/audiohub/src/audiohub/webserver.py"
        web_fixture.write_text(web_fixture.read_text() + "\\n".join((
            "decoded = json.loads(",
            'body.decode("utf-8")',
            "except (UnicodeError, ValueError, RecursionError):",
            "path = urlsplit(self.path).path",
            "except ValueError:",
            "def _unique_json_object(pairs):",
            "if key in result:",
            'raise ValueError("duplicate status JSON member")',
            "object_pairs_hook=_unique_json_object",
            "def _reject_json_constant(_value):",
            "parse_constant=_reject_json_constant",
            "CLIENT_MAX_LIFETIME_SECONDS = 15",
            "threading.Timer(",
            "watchdog.start()",
            "watchdog.cancel()",
            "request.shutdown(socket.SHUT_RDWR)",
            "def handle_error(self, request, client_address):",
            "def _finite_status_json_float(number):",
            "math.isfinite(value)",
            "parse_float=_finite_status_json_float",
        )))
        make("opt/audiohub/src/audiohub/firstboot_diag.py",
             'OUTPUT_NAME = "AUDIOHUB-TEST-REPORT.json"\\n'
             '"pipewire_links_inspected"\\n'
             '"eq_usb_direct_links"')
        offline_diag = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
        offline_diag.write_text(offline_diag.read_text() + "\n".join((
            "def _read_runtime(path, user_id):",
            'os.open("/", flags)',
            "os.O_DIRECTORY | os.O_NOFOLLOW",
            "os.open(component, flags, dir_fd=dirfd)",
            "parent.st_uid != user_id",
            "stat.S_IMODE(parent.st_mode) & 0o077",
            "meta.st_nlink != 1",
            "stat.S_IMODE(meta.st_mode) & 0o077",
            "MAX_RUNTIME_BYTES + 1",
            "def _unique_runtime_json_object(pairs):",
            'raise ValueError("duplicate diagnostic runtime JSON member")',
            "object_pairs_hook=_unique_runtime_json_object",
            "def _reject_runtime_json_constant(_value):",
            "parse_constant=_reject_runtime_json_constant",
            "except (UnicodeError, ValueError, RecursionError):",
            "def _finite_runtime_json_float(number):",
            "math.isfinite(value)",
            "parse_float=_finite_runtime_json_float",
        )))
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
        audio_unit = root / audit.SERVICES["runtime"][0]
        audio_unit.write_text(audio_unit.read_text() + "KillMode=control-group\n")
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


    def test_symlinked_html_and_locale_files_block_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            html = root / "opt/audiohub/web/index.html"
            html.unlink()
            html.symlink_to("/etc/passwd")
            checks = audit.inspect(root)
            self.assertFalse(checks["web_static_files_nofollow_regular_bounded"])
            self.assertNotEqual(audit.run(root), 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            locale = root / "opt/audiohub/web/locales/en.json"
            locale.unlink()
            locale.symlink_to("/etc/passwd")
            self.assertFalse(audit.inspect(root)[
                "web_static_files_nofollow_regular_bounded"
            ])

    def test_symlinked_locale_directory_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            directory = root / "opt/audiohub/web/locales"
            backup = root / "backup-locales"
            directory.rename(backup)
            directory.symlink_to(backup, target_is_directory=True)
            self.assertFalse(audit.inspect(root)[
                "web_static_files_nofollow_regular_bounded"
            ])

    def test_oversize_web_asset_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            js = root / "opt/audiohub/web/app.js"
            js.write_bytes(b"x" * (512 * 1024 + 1))
            self.assertFalse(audit.inspect(root)[
                "web_static_files_nofollow_regular_bounded"
            ])

    def test_nonregular_web_asset_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            js = root / "opt/audiohub/web/styles.css"
            js.unlink()
            js.mkdir()
            self.assertFalse(audit.inspect(root)[
                "web_static_files_nofollow_regular_bounded"
            ])

    def test_missing_static_nofollow_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            web = root / "opt/audiohub/src/audiohub/webserver.py"
            web.write_text(web.read_text().replace(
                "os.O_NOFOLLOW", "os.O_RDONLY"
            ))
            checks = audit.inspect(root)
            self.assertFalse(checks["status_static_and_state_files_nofollow_bounded"])

    def test_normal_web_assets_and_bounded_reader_pass_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            checks = audit.inspect(root)
            self.assertTrue(checks["web_static_files_nofollow_regular_bounded"])
            self.assertTrue(checks["status_static_and_state_files_nofollow_bounded"])


    def test_missing_private_runtime_atomic_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            runtime = root / "opt/audiohub/src/audiohub/runtime.py"
            runtime.write_text(runtime.read_text().replace(
                "secrets.token_hex(12)", "predictable-name"
            ))
            checks = audit.inspect(root)
            self.assertFalse(checks["runtime_private_state_nofollow_atomic"])

    def test_predictable_runtime_temp_path_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            runtime = root / "opt/audiohub/src/audiohub/runtime.py"
            runtime.write_text(runtime.read_text() +
                               '\npath.with_suffix(".tmp")\n')
            self.assertFalse(audit.inspect(root)[
                "runtime_private_state_nofollow_atomic"
            ])

    def test_normal_private_runtime_atomic_guards_pass_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "runtime_private_state_nofollow_atomic"
            ])


    def test_missing_supervisor_shutdown_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            runtime = root / "opt/audiohub/src/audiohub/runtime.py"
            runtime.write_text(runtime.read_text().replace(
                "self._stop_all_managed_routes()", "pass"
            ))
            self.assertFalse(audit.inspect(root)[
                "unexpected_runtime_failure_stops_all_audio_routes"
            ])

    def test_wrong_systemd_kill_mode_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            unit = root / audit.SERVICES["runtime"][0]
            unit.write_text(unit.read_text().replace(
                "KillMode=control-group", "KillMode=process"
            ))
            self.assertFalse(audit.inspect(root)[
                "unexpected_runtime_failure_stops_all_audio_routes"
            ])

    def test_managed_route_failure_guard_present_in_normal_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "unexpected_runtime_failure_stops_all_audio_routes"
            ])


    def test_unguarded_bluez_trust_fails_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            agent = root / "opt/audiohub/src/audiohub/pairing.py"
            agent.write_text(agent.read_text().replace(
                "self.pending_authorizations.pop(path, None)", "pass"
            ))
            self.assertFalse(audit.inspect(root)[
                "bluetooth_trust_requires_agent_authorization"
            ])

    def test_unsourced_paired_signal_fails_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            agent = root / "opt/audiohub/src/audiohub/pairing.py"
            agent.write_text(agent.read_text().replace(
                'bus_name="org.bluez"', 'bus_name="anyone"'
            ))
            self.assertFalse(audit.inspect(root)[
                "bluetooth_trust_requires_agent_authorization"
            ])

    def test_missing_real_paired_property_check_fails_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            agent = root / "opt/audiohub/src/audiohub/pairing.py"
            agent.write_text(agent.read_text().replace(
                'device.Get("org.bluez.Device1", "Paired")', "True"
            ))
            self.assertFalse(audit.inspect(root)[
                "bluetooth_trust_requires_agent_authorization"
            ])

    def test_unpaired_event_token_purge_guard_in_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)["bluetooth_unpaired_event_revokes_pending_trust"])

    def test_false_paired_does_not_revoke_token_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/pairing.py"
            file.write_text(file.read_text().replace(
                'or ("Paired" in change and not change["Paired"])):',
                'or ("Paired" in change and False)):'
            ))
            self.assertFalse(audit.inspect(root)["bluetooth_unpaired_event_revokes_pending_trust"])

    def test_missing_paired_invalidation_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/pairing.py"
            file.write_text(file.read_text().replace(
                'if ((invalidated and "Paired" in invalidated)',
                'if ((invalidated and False)'
            ))
            self.assertFalse(audit.inspect(root)["bluetooth_unpaired_event_revokes_pending_trust"])

    def test_missing_device_specific_token_revocation_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/pairing.py"
            file.write_text(file.read_text().replace(
                "self.pending_authorizations.pop(path, None)",
                "self.pending_authorizations.get(path)"
            ))
            self.assertFalse(audit.inspect(root)["bluetooth_unpaired_event_revokes_pending_trust"])

    def test_bluez_cancel_revokes_pending_in_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)["bluetooth_cancel_revokes_pending_trust"])

    def test_noop_bluez_cancel_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/pairing.py"
            path.write_text(path.read_text().replace(
                "self.pending_authorizations.clear()", "pass"
            ))
            self.assertFalse(audit.inspect(root)["bluetooth_cancel_revokes_pending_trust"])

    def test_incomplete_bluez_cancel_revocation_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/pairing.py"
            path.write_text(path.read_text().replace(
                "self.pending_authorizations.clear()",
                "self.pending_authorizations.pop(device, None)"
            ))
            self.assertFalse(audit.inspect(root)["bluetooth_cancel_revokes_pending_trust"])

    def test_authorized_bluez_pairing_guard_present_in_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "bluetooth_trust_requires_agent_authorization"
            ])


    def test_unlimited_bluez_discoverability_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/pairing.py"
            path.write_text(path.read_text().replace(
                'DiscoverableTimeout", dbus.UInt32(BOOT_WINDOW)',
                'DiscoverableTimeout", dbus.UInt32(0)'
            ))
            self.assertFalse(audit.inspect(root)[
                "bluetooth_pairable_discoverable_timers_bounded"
            ])

    def test_unlimited_pairable_timeout_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/pairing.py"
            path.write_text(path.read_text().replace(
                'PairableTimeout", dbus.UInt32(BOOT_WINDOW)',
                'PairableTimeout", dbus.UInt32(0)'
            ))
            self.assertFalse(audit.inspect(root)[
                "bluetooth_pairable_discoverable_timers_bounded"
            ])

    def test_service_restart_reopens_full_guest_window_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/pairing.py"
            path.write_text(path.read_text().replace(
                "self.deadline = float(BOOT_WINDOW)",
                "self.deadline = time.monotonic() + BOOT_WINDOW"
            ))
            self.assertFalse(audit.inspect(root)[
                "bluetooth_pairable_discoverable_timers_bounded"
            ])

    def test_bounded_bluez_adapter_timeouts_pass_image_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "bluetooth_pairable_discoverable_timers_bounded"
            ])

    def test_missing_bounded_capture_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/process_capture.py"
            path.write_text(path.read_text().replace(
                "selectors.DefaultSelector()", "unbounded-communicate"
            ))
            self.assertFalse(audit.inspect(root)["pipewire_stdout_bounded_no_shell"])

    def test_runtime_direct_unbounded_capture_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/runtime.py"
            path.write_text(path.read_text().replace(
                "bounded_command_output(args, timeout=timeout)",
                "subprocess.run(args, capture_output=True)"
            ))
            self.assertFalse(audit.inspect(root)["pipewire_stdout_bounded_no_shell"])

    def test_missing_preflight_limit_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/hardware_preflight.py"
            path.write_text("subprocess.run(['pw-dump'], capture_output=True)")
            self.assertFalse(audit.inspect(root)["pipewire_stdout_bounded_no_shell"])

    def test_real_bound_and_graph_limits_are_present_in_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)["pipewire_stdout_bounded_no_shell"])

    def test_manual_observation_cannot_mark_hardware_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/manual_acceptance.py"
            source.write_text(source.read_text().replace(
                '"hardware_accepted": False', '"hardware_accepted": True'
            ))
            self.assertFalse(audit.inspect(root)[
                "manual_hardware_observation_not_auto_approval"
            ])

    def test_manual_observation_cannot_mark_release_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/manual_acceptance.py"
            source.write_text(source.read_text().replace(
                '"release_ready": False', '"release_ready": True'
            ))
            self.assertFalse(audit.inspect(root)[
                "manual_hardware_observation_not_auto_approval"
            ])

    def test_manual_observation_cannot_start_network_or_write_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/manual_acceptance.py"
            source.write_text(source.read_text() + "\\nimport socket\\n")
            self.assertFalse(audit.inspect(root)[
                "manual_hardware_observation_not_auto_approval"
            ])

    def test_verified_manual_observation_guard_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "manual_hardware_observation_not_auto_approval"
            ])


    def test_missing_duplicate_node_id_detection_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/discovery.py"
            source.write_text(source.read_text().replace(
                "if ident in seen:", "if False:"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_node_identity_ambiguity_fails_closed"
            ])

    def test_arbitrary_first_bluetooth_source_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/discovery.py"
            source.write_text(source.read_text().replace(
                "conflicted.add(name_mac)", "pass"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_node_identity_ambiguity_fails_closed"
            ])

    def test_arbitrary_last_virtual_sink_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            source = root / "opt/audiohub/src/audiohub/discovery.py"
            source.write_text(source.read_text().replace(
                "return {} if ambiguous else found", "return found"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_node_identity_ambiguity_fails_closed"
            ])

    def test_preflight_without_uniqueness_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/hardware_preflight.py"
            path.write_text(path.read_text().replace(
                "_conflicting_node_ids(nodes)", "True"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_node_identity_ambiguity_fails_closed"
            ])

    def test_link_inspection_without_uniqueness_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/audio_graph.py"
            path.write_text(path.read_text().replace(
                "_conflicting_node_ids(nodes)", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_node_identity_ambiguity_fails_closed"
            ])

    def test_shared_pipewire_json_guard_in_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "pipewire_nodes_and_links_strict_shared_json_snapshot"
            ])

    def test_missing_pipewire_duplicate_member_check_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/discovery.py"
            file.write_text(file.read_text().replace(
                "object_pairs_hook=_unique_pipewire_members", "object_pairs_hook=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_nodes_and_links_strict_shared_json_snapshot"
            ])

    def test_permissive_link_parser_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/audio_graph.py"
            file.write_text(file.read_text().replace(
                "graph = _parse_pipewire_graph(raw)", "graph = json.loads(raw)"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_nodes_and_links_strict_shared_json_snapshot"
            ])

    def test_missing_pipewire_graph_depth_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/discovery.py"
            file.write_text(file.read_text().replace(
                "return raw if _pipewire_graph_shape_bounded(raw) else None",
                "return raw"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_nodes_and_links_strict_shared_json_snapshot"
            ])

    def test_missing_pipewire_deep_json_failure_handling_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/discovery.py"
            file.write_text(file.read_text().replace(
                "except (UnicodeError, TypeError, ValueError, RecursionError):",
                "except (UnicodeError, TypeError, ValueError):"
            ))
            self.assertFalse(audit.inspect(root)[
                "pipewire_nodes_and_links_strict_shared_json_snapshot"
            ])

    def test_unique_pipewire_identity_guards_pass_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "pipewire_node_identity_ambiguity_fails_closed"
            ])


    def test_offline_diag_symlinked_runtime_directory_guard_missing_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "os.open(component, flags, dir_fd=dirfd)",
                "os.open(component, flags)"
            ))
            self.assertFalse(audit.inspect(root)[
                "offline_diag_runtime_directory_nofollow_private"
            ])

    def test_offline_diag_public_runtime_directory_guard_missing_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "stat.S_IMODE(parent.st_mode) & 0o077", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "offline_diag_runtime_directory_nofollow_private"
            ])

    def test_offline_diag_hardlinked_status_guard_missing_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "meta.st_nlink != 1", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "offline_diag_runtime_directory_nofollow_private"
            ])

    def test_private_offline_diagnostic_status_read_guard_passes_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "offline_diag_runtime_directory_nofollow_private"
            ])



    def test_root_offline_diagnostic_json_parser_guard_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "offline_diag_json_integrity_fail_closed"
            ])

    def test_missing_offline_duplicate_member_guard_fails_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "object_pairs_hook=_unique_runtime_json_object", "object_pairs_hook=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "offline_diag_json_integrity_fail_closed"
            ])

    def test_missing_offline_nonfinite_guard_fails_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "parse_constant=_reject_runtime_json_constant", "parse_constant=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "offline_diag_json_integrity_fail_closed"
            ])

    def test_missing_offline_nested_json_recursion_guard_fails_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "except (UnicodeError, ValueError, RecursionError):",
                "except (UnicodeError, ValueError):"
            ))
            self.assertFalse(audit.inspect(root)[
                "offline_diag_json_integrity_fail_closed"
            ])

    def test_unbounded_manual_laptop_pw_dump_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/network_laptop.py"
            path.write_text(path.read_text().replace(
                'bounded_command_output(("pw-dump",), timeout=5)',
                'subprocess.run(["pw-dump"], capture_output=True)'
            ))
            self.assertFalse(audit.inspect(root)[
                "manual_laptop_pipewire_capture_bounded"
            ])

    def test_manual_laptop_wpctl_unbounded_capture_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/network_laptop.py"
            path.write_text(path.read_text().replace(
                '("wpctl", "set-default", str(output["id"])), timeout=5,',
                '("wpctl", "set-default", str(output["id"])),'
            ))
            self.assertFalse(audit.inspect(root)[
                "manual_laptop_pipewire_capture_bounded"
            ])

    def test_manual_laptop_ignoring_capture_failure_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/network_laptop.py"
            path.write_text(path.read_text().replace(
                "if result is None or result.returncode != 0:",
                "if result.returncode != 0:"
            ))
            self.assertFalse(audit.inspect(root)[
                "manual_laptop_pipewire_capture_bounded"
            ])

    def test_manual_laptop_bounded_pipewire_guard_passes_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "manual_laptop_pipewire_capture_bounded"
            ])


    def test_unbounded_status_http_workers_block_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "self._client_slots.acquire(blocking=False)",
                "unbounded_worker_start(request)"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_http_clients_bounded_no_request_logs"
            ])

    def test_unlimited_http_client_timeout_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "conn.settimeout(CLIENT_READ_TIMEOUT_SECONDS)", "pass"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_http_clients_bounded_no_request_logs"
            ])

    def test_raw_request_access_logging_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "def log_message(self, format, *args):",
                "def access_log_path(self, format, *args):"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_http_clients_bounded_no_request_logs"
            ])

    def test_bounded_and_private_webserver_image_guard_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "status_http_clients_bounded_no_request_logs"
            ])


    def test_web_runtime_file_owner_guard_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "info.st_uid != private_owner", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_runtime_private_owner_and_hardlink_guard"
            ])

    def test_web_runtime_directory_private_mode_guard_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "stat.S_IMODE(parent.st_mode) & 0o077", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_runtime_private_owner_and_hardlink_guard"
            ])

    def test_web_runtime_status_hardlink_guard_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "info.st_nlink != 1", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_runtime_private_owner_and_hardlink_guard"
            ])

    def test_web_private_status_guard_passes_installed_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "status_runtime_private_owner_and_hardlink_guard"
            ])

    def test_malformed_status_inputs_have_installed_image_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "status_malformed_inputs_fail_closed"
            ])

    def test_json_decoder_body_marker_required_in_installed_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                'body.decode("utf-8")',
                'body.decode("latin-1")'
            ))
            self.assertFalse(audit.inspect(root)[
                "status_malformed_inputs_fail_closed"
            ])

    def test_missing_deep_json_failure_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "except (UnicodeError, ValueError, RecursionError):",
                "except (UnicodeError, ValueError):"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_malformed_inputs_fail_closed"
            ])

    def test_missing_url_parsing_failure_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "except ValueError:", "except LookupError:"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_malformed_inputs_fail_closed"
            ])

    def test_strict_status_json_guard_present_in_installed_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "status_json_unique_keys_and_finite_numbers_only"
            ])

    def test_missing_duplicate_json_member_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "object_pairs_hook=_unique_json_object",
                "object_pairs_hook=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_json_unique_keys_and_finite_numbers_only"
            ])

    def test_missing_nonfinite_json_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "parse_constant=_reject_json_constant",
                "parse_constant=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_json_unique_keys_and_finite_numbers_only"
            ])

    def test_total_client_lifetime_guard_present_in_installed_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "status_http_total_lifetime_and_peer_error_privacy"
            ])

    def test_missing_total_lifetime_watchdog_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "watchdog.start()", "pass"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_http_total_lifetime_and_peer_error_privacy"
            ])

    def test_missing_timeout_shutdown_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "request.shutdown(socket.SHUT_RDWR)", "pass"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_http_total_lifetime_and_peer_error_privacy"
            ])

    def test_unsanitized_server_error_handler_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "def handle_error(self, request, client_address):",
                "def handle_unprotected_error(self, request, client_address):"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_http_total_lifetime_and_peer_error_privacy"
            ])

    def test_json_exponent_integrity_guards_both_installed_readers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "status_and_offline_json_finite_exponent_guard"
            ])

    def test_missing_web_exponent_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/webserver.py"
            path.write_text(path.read_text().replace(
                "parse_float=_finite_status_json_float", "parse_float=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_and_offline_json_finite_exponent_guard"
            ])

    def test_missing_root_diagnostic_exponent_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            path.write_text(path.read_text().replace(
                "parse_float=_finite_runtime_json_float", "parse_float=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "status_and_offline_json_finite_exponent_guard"
            ])

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
                'sinks if (usb_ready and self.route_policy_valid) else {})',
                'sinks)'
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

    def test_installed_private_config_nofollow_all_parents_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "private_config_ancestor_symlink_fd_walk"
            ])

    def test_source_route_direct_path_open_blocks_native_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/source_routes.py"
            path.write_text(path.read_text().replace(
                'dirfd = os.open("/", flags)',
                "dirfd = os.open(path, flags)"
            ))
            self.assertFalse(audit.inspect(root)[
                "private_config_ancestor_symlink_fd_walk"
            ])

    def test_input_profile_direct_path_open_blocks_native_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/input_profiles.py"
            path.write_text(path.read_text().replace(
                'nextfd = os.open(component, flags, dir_fd=dirfd)',
                "nextfd = os.open(path, flags)"
            ))
            self.assertFalse(audit.inspect(root)[
                "private_config_ancestor_symlink_fd_walk"
            ])

    def test_unprotected_profile_directory_creation_blocks_native_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/input_profiles.py"
            path.write_text(path.read_text().replace(
                "dirfd = _safe_dir(directory, create=True)",
                "directory.mkdir(parents=True, exist_ok=True)\ndirfd = _safe_dir(directory)"
            ))
            self.assertFalse(audit.inspect(root)[
                "private_config_ancestor_symlink_fd_walk"
            ])

    def test_private_route_config_reader_guard_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)["source_route_config_strict_nonblocking_read"])

    def test_route_fifo_blocking_open_fails_image_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/source_routes.py"
            file.write_text(file.read_text().replace(
                "os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW",
                "os.O_RDONLY | os.O_NOFOLLOW"
            ))
            self.assertFalse(audit.inspect(root)["source_route_config_strict_nonblocking_read"])

    def test_route_duplicate_json_parser_missing_fails_image_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/source_routes.py"
            file.write_text(file.read_text().replace(
                "object_pairs_hook=_unique_route_members", "object_pairs_hook=None"
            ))
            self.assertFalse(audit.inspect(root)["source_route_config_strict_nonblocking_read"])

    def test_private_input_profile_guard_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)["input_profile_config_strict_nonblocking_read"])

    def test_profile_fifo_blocking_open_fails_image_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/input_profiles.py"
            file.write_text(file.read_text().replace(
                "os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW",
                "os.O_RDONLY | os.O_NOFOLLOW"
            ))
            self.assertFalse(audit.inspect(root)["input_profile_config_strict_nonblocking_read"])

    def test_profile_duplicate_json_parser_missing_fails_image_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/input_profiles.py"
            file.write_text(file.read_text().replace(
                "object_pairs_hook=_unique_profile_members", "object_pairs_hook=None"
            ))
            self.assertFalse(audit.inspect(root)["input_profile_config_strict_nonblocking_read"])

    def test_installed_runtime_strict_settings_json_guard_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "runtime_settings_assignments_json_fail_closed"
            ])

    def test_duplicate_runtime_settings_parser_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            f = root / "opt/audiohub/src/audiohub/runtime.py"
            f.write_text(f.read_text().replace(
                "object_pairs_hook=_unique_state_json_members",
                "object_pairs_hook=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "runtime_settings_assignments_json_fail_closed"
            ])

    def test_missing_runtime_depth_guard_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            f = root / "opt/audiohub/src/audiohub/runtime.py"
            f.write_text(f.read_text().replace(
                "not _private_state_shape_bounded(value)", "False"
            ))
            self.assertFalse(audit.inspect(root)[
                "runtime_settings_assignments_json_fail_closed"
            ])

    def test_runtime_nonfinite_state_parser_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            f = root / "opt/audiohub/src/audiohub/runtime.py"
            f.write_text(f.read_text().replace(
                "parse_float=_finite_state_json_float", "parse_float=None"
            ))
            self.assertFalse(audit.inspect(root)[
                "runtime_settings_assignments_json_fail_closed"
            ])

    def test_installed_mixer_master_first_guard_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            self.assertTrue(audit.inspect(root)[
                "mixer_master_gain_verified_before_managed_routes"
            ])

    def test_master_gain_order_regression_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/mixer.py"
            path.write_text(path.read_text().replace(
                "if output_id is not None:", "if False:"
            ))
            self.assertFalse(audit.inspect(root)[
                "mixer_master_gain_verified_before_managed_routes"
            ])

    def test_unchecked_wpctl_control_result_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/runtime.py"
            path.write_text(path.read_text().replace(
                "if applied is None or applied.returncode != 0:", "if False:"
            ))
            self.assertFalse(audit.inspect(root)[
                "mixer_master_gain_verified_before_managed_routes"
            ])

    def test_routing_before_mixer_programming_blocks_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            path = root / "opt/audiohub/src/audiohub/runtime.py"
            body = path.read_text()
            before = body.replace(
                "for args in volume_commands(",
                "self._route(sources if\nfor args in volume_commands("
            )
            path.write_text(before)
            self.assertFalse(audit.inspect(root)[
                "mixer_master_gain_verified_before_managed_routes"
            ])

    def test_missing_flexible_source_plan_blocks_alpha_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/src/audiohub/source_routes.py").unlink()
            checks = audit.inspect(root)
            self.assertFalse(checks["source_source_routes.py"])
            self.assertFalse(checks["source_routing_isolated_and_fail_closed"])

    def test_missing_dynamic_lan_target_blocks_alpha_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            receiver = root / "opt/audiohub/src/audiohub/network_laptop.py"
            receiver.write_text(receiver.read_text().replace(
                "if lan_target() != target:", "if False:"
            ))
            self.assertFalse(
                audit.inspect(root)["source_routing_isolated_and_fail_closed"]
            )

    def test_missing_source_isolation_blocks_alpha_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            runtime = root / "opt/audiohub/src/audiohub/runtime.py"
            runtime.write_text(runtime.read_text().replace(
                'channel != getattr(self, "route_plan", default_routes())["lan_slot"]',
                "True"
            ))
            self.assertFalse(
                audit.inspect(root)["source_routing_isolated_and_fail_closed"]
            )

    def test_missing_graph_source_blocks_image_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            (root / "opt/audiohub/src/audiohub/audio_graph.py").unlink()
            self.assertFalse(audit.inspect(root)["privacy_safe_pipewire_link_observation"])
            self.assertFalse(audit.inspect(root)["source_audio_graph.py"])

    def test_disabling_actual_link_inspection_blocks_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            graph = root / "opt/audiohub/src/audiohub/audio_graph.py"
            graph.write_text(graph.read_text().replace(
                '"output-node-id"', '"node.name"'
            ))
            self.assertFalse(audit.inspect(root)["privacy_safe_pipewire_link_observation"])

    def test_missing_sd_link_metrics_blocks_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            file = root / "opt/audiohub/src/audiohub/firstboot_diag.py"
            file.write_text(file.read_text().replace(
                '"eq_usb_direct_links"', '"hardware_passed"'
            ))
            self.assertFalse(audit.inspect(root)["privacy_safe_pipewire_link_observation"])

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
