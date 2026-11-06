# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed pre-export inspection of a built AudioHub root filesystem.

This checks packaging consistency, not actual Raspberry Pi boot, audio quality,
or legal compliance. Invoked by the pi-gen custom stage before compression.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

LANGUAGES = ("en", "de", "es", "fr", "it")
CHANNELS = ("music", "laptop", "tablet")
SERVICES = {
    "bluetooth": (
        "etc/systemd/system/audiohub-bluetooth.service",
        "etc/systemd/system/multi-user.target.wants/audiohub-bluetooth.service",
        "python3 -m audiohub.pairing",
    ),
    "runtime": (
        "etc/systemd/user/audiohub-runtime.service",
        "etc/systemd/user/default.target.wants/audiohub-runtime.service",
        "python3 -m audiohub.runtime",
    ),
    "status": (
        "etc/systemd/user/audiohub-status-web.service",
        "etc/systemd/user/default.target.wants/audiohub-status-web.service",
        "python3 -m audiohub.webserver",
    ),
}
REQUIRED_BINARIES = ("python3", "pw-dump", "pw-loopback", "pw-cat", "wpctl", "bluetoothctl")


def inspect(root: Path) -> dict[str, bool]:
    """Return named checks with no secrets or identifying information."""
    if not root.is_dir():
        return {"rootfs_exists": False}
    checks: dict[str, bool] = {}
    source = root / "opt/audiohub/src/audiohub"
    for name in ("__init__.py", "runtime.py", "pairing.py", "mixer.py", "webserver.py", "status_bind.py", "firstboot_diag.py", "network_laptop.py", "network_buffer.py", "input_profiles.py", "source_routes.py", "audio_graph.py", "hardware_preflight.py", "process_capture.py", "manual_acceptance.py"):
        checks["source_" + name] = (source / name).is_file()
    # Polling PipeWire must not allocate arbitrarily large stdout or
    # include raw metadata in logs and auxiliary reports.
    try:
        capture_source = (source / "process_capture.py").read_text()
        runtime_source = (source / "runtime.py").read_text()
        preflight_source = (source / "hardware_preflight.py").read_text()
        discovery_source = (source / "discovery.py").read_text()
        checks["pipewire_stdout_bounded_no_shell"] = all(
            marker in capture_source for marker in (
                "MAX_COMMAND_STDOUT_BYTES = 4 * 1024 * 1024",
                "selectors.DefaultSelector()",
                "max_bytes + 1 - len(output)",
                "start_new_session=True",
                "shell=False",
                "os.killpg(",
                "stderr=subprocess.DEVNULL",
            )
        ) and all(
            marker in runtime_source for marker in (
                "from .process_capture import bounded_command_output",
                "bounded_command_output(args, timeout=timeout)",
            )
        ) and (
            'bounded_command_output(("pw-dump",), timeout=5)'
            in preflight_source
        ) and all(
            marker in discovery_source for marker in (
                "MAX_PIPEWIRE_GRAPH_BYTES = 4 * 1024 * 1024",
                "MAX_PIPEWIRE_GRAPH_OBJECTS = 8192",
            )
        )
    except OSError:
        checks["pipewire_stdout_bounded_no_shell"] = False
    # The offline diagnostic runs as root. It must never follow symlinked
    # ancestors into an untrusted user-controlled runtime JSON directory.
    try:
        offline_source = (source / "firstboot_diag.py").read_text()
        checks["offline_diag_runtime_directory_nofollow_private"] = all(
            token in offline_source for token in (
                "def _read_runtime(path, user_id):",
                'os.open("/", flags)',
                "os.O_DIRECTORY | os.O_NOFOLLOW",
                "os.open(component, flags, dir_fd=dirfd)",
                "parent.st_uid != user_id",
                "stat.S_IMODE(parent.st_mode) & 0o077",
                "meta.st_nlink != 1",
                "stat.S_IMODE(meta.st_mode) & 0o077",
                "MAX_RUNTIME_BYTES + 1",
            )
        )
    except OSError:
        checks["offline_diag_runtime_directory_nofollow_private"] = False
    # PipeWire Node IDs and virtual sink identities must be unique before
    # wpctl set-default or pw-loopback can use them. Duplicate records or
    # conflicting BT profiles cannot choose an arbitrary first/last node.
    try:
        discovery = (source / "discovery.py").read_text()
        preflight = (source / "hardware_preflight.py").read_text()
        graph = (source / "audio_graph.py").read_text()
        checks["pipewire_node_identity_ambiguity_fails_closed"] = all(
            marker in discovery for marker in (
                "def _conflicting_node_ids(nodes):",
                "if ident in seen:",
                "if _conflicting_node_ids(nodes):",
                "conflicted.add(name_mac)",
                'return [source for source in result if source["address"] not in conflicted]',
                "ambiguous.add(name)",
                "return {} if ambiguous else found",
            )
        ) and "_conflicting_node_ids(nodes)" in preflight and (
            "_conflicting_node_ids(nodes)" in graph
        )
    except OSError:
        checks["pipewire_node_identity_ambiguity_fails_closed"] = False
    # No operator-only "hardware check" may quietly grant legal, owner or
    # stable-image approval from detected topology or typed responses.
    try:
        manual = (source / "manual_acceptance.py").read_text()
        checks["manual_hardware_observation_not_auto_approval"] = all(
            token in manual for token in (
                'from .hardware_preflight import probe',
                '"hardware_accepted": False',
                '"ownership_authenticated": False',
                '"legal_redistribution_approved": False',
                '"model_c_license_effective": False',
                '"release_ready": False',
                '"persisted": False',
                '"operator_observations": observations',
                'MAX_INPUT_ATTEMPTS = 3',
            )
        ) and 'import socket' not in manual and 'write_text(' not in manual
    except OSError:
        checks["manual_hardware_observation_not_auto_approval"] = False
    # Runtime's private state must never follow attacker-controlled links,
    # write through a fixed .tmp name, or accept unbounded JSON.
    try:
        runtime_security = (source / "runtime.py").read_text()
        checks["runtime_private_state_nofollow_atomic"] = all(
            marker in runtime_security for marker in (
                "MAX_RUNTIME_JSON_BYTES = 32 * 1024",
                "def _private_parent_fd(path, *, create=False):",
                "os.O_NOFOLLOW", "os.O_NONBLOCK",
                "os.O_EXCL", "secrets.token_hex(12)",
                "stat.S_ISREG", "os.replace(name, path.name",
                "os.fsync(dirfd)",
            )
        ) and 'path.with_suffix(".tmp")' not in runtime_security
    except OSError:
        checks["runtime_private_state_nofollow_atomic"] = False
    # An unexpected supervisor exception must stop all managed audio routes;
    # systemd must kill the entire service cgroup if cleanup itself fails.
    try:
        runtime_source = (source / "runtime.py").read_text()
        runtime_unit = (root / SERVICES["runtime"][0]).read_text()
        checks["unexpected_runtime_failure_stops_all_audio_routes"] = all(
            mark in runtime_source for mark in (
                "def _stop_all_managed_routes(self):",
                "def poll_safely(self):",
                "self._stop_all_managed_routes()",
                "self.poll_safely()",
            )
        ) and all(mark in runtime_unit for mark in (
            "KillMode=control-group", "Restart=always"
        ))
    except OSError:
        checks["unexpected_runtime_failure_stops_all_audio_routes"] = False
    # Build-time guard: the alpha status UI is unauthenticated, so the
    # installed image must never bind to all interfaces by default.
    try:
        bind_module = (source / "status_bind.py").read_text()
        webserver = (source / "webserver.py").read_text()
        status_unit = (root / SERVICES["status"][0]).read_text()
        checks["status_loopback_default"] = (
            'LOOPBACK = "127.0.0.1"' in bind_module
            and 'values.get("AUDIOHUB_STATUS_BIND_IP", LOOPBACK)' in bind_module
            and 'values.get("AUDIOHUB_UNSAFE_STATUS_LAN") != "YES"' in bind_module
        )
        checks["status_web_uses_guarded_bind"] = (
            "from .status_bind import select_bind_address" in webserver
            and "BoundedStatusHTTPServer((select_bind_address(), 8765)" in webserver
            and "0.0.0.0" not in webserver
        )
        checks["status_static_and_state_files_nofollow_bounded"] = all(
            marker in webserver for marker in (
                "STATIC_MAX_BYTES = 512 * 1024",
                "STATUS_MAX_BYTES = 32 * 1024",
                "os.O_NOFOLLOW", "os.O_NONBLOCK",
                "stat.S_ISREG", "read_public_status()",
            )
        )
        # The status JSON is audiohub-user-owned runtime state, unlike
        # root-owned publicly readable HTML/JS. Only the private status
        # reader must enforce UID, private directory mode, and nlink=1.
        checks["status_runtime_private_owner_and_hardlink_guard"] = all(
            mark in webserver for mark in (
                "def _bounded_regular_bytes(path, limit, *, private_owner=None):",
                "parent.st_uid != private_owner",
                "stat.S_IMODE(parent.st_mode) & 0o077",
                "info.st_uid != private_owner",
                "info.st_nlink != 1",
                "stat.S_IMODE(info.st_mode) & 0o077",
                "private_owner=os.geteuid()",
            )
        ) and "_bounded_regular_bytes(WEBROOT / filename, STATIC_MAX_BYTES)" in webserver
        checks["status_http_clients_bounded_no_request_logs"] = all(
            mark in webserver for mark in (
                "MAX_STATUS_CLIENTS = 8",
                "CLIENT_READ_TIMEOUT_SECONDS = 5",
                "class BoundedStatusHTTPServer(ThreadingHTTPServer):",
                "threading.BoundedSemaphore(MAX_STATUS_CLIENTS)",
                "self._client_slots.acquire(blocking=False)",
                "self.shutdown_request(request)",
                "def process_request_thread(self, request, client_address):",
                "self._client_slots.release()",
                "conn.settimeout(CLIENT_READ_TIMEOUT_SECONDS)",
                "def log_message(self, format, *args):",
            )
        ) and "server = BoundedStatusHTTPServer(" in webserver
        # A malformed status JSON document or HTTP absolute request URI
        # must fail closed, rather than throw out of the alpha status handler.
        checks["status_malformed_inputs_fail_closed"] = all(
            mark in webserver for mark in (
                'json.loads(body.decode("utf-8"))',
                "except (UnicodeError, ValueError, RecursionError):",
                "path = urlsplit(self.path).path",
                "except ValueError:",
            )
        )
        # Private owner-authored JSON may still contain duplicate keys or
        # Python-only NaN/Infinity constants. Refuse the complete snapshot.
        checks["status_json_unique_keys_and_finite_numbers_only"] = all(
            mark in webserver for mark in (
                "def _unique_json_object(pairs):",
                "if key in result:",
                "raise ValueError(\"duplicate status JSON member\")",
                "object_pairs_hook=_unique_json_object",
                "def _reject_json_constant(_value):",
                "parse_constant=_reject_json_constant",
            )
        )
        checks["status_service_no_unsafe_lan_opt_in"] = (
            "AUDIOHUB_UNSAFE_STATUS_LAN" not in status_unit
            and "AUDIOHUB_STATUS_BIND_IP" not in status_unit
        )
    except OSError:
        checks["status_loopback_default"] = False
        checks["status_web_uses_guarded_bind"] = False
        checks["status_service_no_unsafe_lan_opt_in"] = False
        checks["status_static_and_state_files_nofollow_bounded"] = False
        checks["status_http_clients_bounded_no_request_logs"] = False
        checks["status_runtime_private_owner_and_hardlink_guard"] = False
        checks["status_malformed_inputs_fail_closed"] = False
        checks["status_json_unique_keys_and_finite_numbers_only"] = False
    # BlueZ's PropertiesChanged signal is not a license to mark arbitrary
    # neighbors as Trusted. Ensure the installed agent requires a short-lived
    # explicit authorization callback, verifies real BlueZ paired state and
    # rejects unauthenticated services outside that authorization.
    try:
        pairing_source = (source / "pairing.py").read_text()
        checks["bluetooth_trust_requires_agent_authorization"] = all(
            marker in pairing_source for marker in (
                "AUTHORIZATION_TTL = 45",
                "def authorized_pairing_signal(",
                "def authorize_pending(self, device):",
                "self.pending_authorizations.pop(path, None)",
                'bus_name="org.bluez"',
                'device.Get("org.bluez.Device1", "Paired")',
                "if not self.allowed() or not (",
                'raise Rejected("Untrusted device")',
            )
        ) and "self.authorize_pending(device)" in pairing_source
    except OSError:
        checks["bluetooth_trust_requires_agent_authorization"] = False
    # PairableTimeout=0 / DiscoverableTimeout=0 mean unlimited in BlueZ.
    # The first-boot listener may not reopen a fresh window on restart.
    try:
        pairing_source = (source / "pairing.py").read_text()
        checks["bluetooth_pairable_discoverable_timers_bounded"] = all(
            token in pairing_source for token in (
                "self.deadline = float(BOOT_WINDOW)",
                'self.adapter.Set("org.bluez.Adapter1", "PairableTimeout", dbus.UInt32(BOOT_WINDOW))',
                'self.adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(BOOT_WINDOW))',
                'self.adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(False))',
                'self.adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(False))',
            )
        ) and 'DiscoverableTimeout", dbus.UInt32(0)' not in pairing_source
    except OSError:
        checks["bluetooth_pairable_discoverable_timers_bounded"] = False
    # Offline-only debug output is written by a strictly sandboxed root
    # service; never include network enrollment secrets in the image or report.
    diag_unit_path = root / "etc/systemd/system/audiohub-firstboot-diag.service"
    diag_enable_path = root / (
        "etc/systemd/system/multi-user.target.wants/audiohub-firstboot-diag.service"
    )
    try:
        diag_unit = diag_unit_path.read_text()
        checks["offline_diag_unit_sandboxed"] = all(
            option in diag_unit for option in (
                "python3 -m audiohub.firstboot_diag",
                "PrivateNetwork=yes",
                "NoNewPrivileges=yes",
                "ProtectSystem=strict",
                "ReadWritePaths=/boot/firmware",
                "ConditionPathIsMountPoint=/boot/firmware",
            )
        ) and "ExecStart=/bin/sh" not in diag_unit
        if diag_enable_path.is_symlink():
            target = os.readlink(diag_enable_path)
            resolved = (root / target.lstrip("/")) if os.path.isabs(target) else (
                diag_enable_path.parent / target
            )
            checks["offline_diag_enabled"] = resolved.is_file()
        else:
            checks["offline_diag_enabled"] = False
        diag_source = (source / "firstboot_diag.py").read_text()
        checks["offline_diag_no_network_clients"] = (
            "socket.socket" not in diag_source
            and "subprocess.run" not in diag_source
            and "dbus.SystemBus" not in diag_source
            and 'OUTPUT_NAME = "AUDIOHUB-TEST-REPORT.json"' in diag_source
        )
    except OSError:
        checks["offline_diag_unit_sandboxed"] = False
        checks["offline_diag_enabled"] = False
        checks["offline_diag_no_network_clients"] = False
    # A2DP must be routed into the two managed EQ sinks, not bypassed
    # through WirePlumber's default phone-as-playback behavior.
    try:
        bluez_config = (
            root / "etc/wireplumber/wireplumber.conf.d/90-audiohub.conf"
        ).read_text()
        runtime_source = (source / "runtime.py").read_text()
        checks["bluetooth_input_role_configured"] = all(
            needle in bluez_config for needle in (
                "bluez5.roles = [ a2dp_sink ]",
                'node.name = "~bluez_input.*"',
                "bluez5.media-source-role = input",
                "monitor.bluez.rules = [",
            )
        )
        checks["managed_eq_routing_and_usb_gate"] = all(
            needle in runtime_source for needle in (
                "channel not in CHANNELS",
                '"--capture", source',
                '"--playback", "audiohub." + channel',
                'usb_ready = bool(selected and selected.returncode == 0)',
                'self._route(sources if self.route_policy_valid else [],',
                'sinks if (usb_ready and self.route_policy_valid) else {})',
            )
        )
    except OSError:
        checks["bluetooth_input_role_configured"] = False
        checks["managed_eq_routing_and_usb_gate"] = False
    # Image must ship the already reviewed AH-003 conservative
    # 3-channel gain budget; source runtime settings cannot silently
    # restore an unbounded master volume.
    try:
        mixer_source = (source / "mixer.py").read_text()
        runtime_source = (source / "runtime.py").read_text()
        checks["conservative_mix_gain_installed"] = all(
            needle in mixer_source for needle in (
                "def mix_gain_budget(settings):",
                "def effective_master_gain(settings):",
                "return min(1.0, 1.0 / worst_case)",
                "str(effective_master_gain(settings))",
            )
        ) and all(
            needle in runtime_source for needle in (
                "effective_master_gain(self.settings)",
                '"effective_master_percent"',
            )
        )
    except OSError:
        checks["conservative_mix_gain_installed"] = False
    # An unauthenticated legacy LAN PCM receiver may be shipped as source
    # ONLY for deliberate bench testing. It must never bind a socket or
    # register a service during image boot. This deliberately does not
    # authorize the Windows sender for a consumer release.
    try:
        laptop_source = (source / "network_laptop.py").read_text()
        buffer_source = (source / "network_buffer.py").read_text()
        checks["laptop_manual_receiver_packaged"] = all(
            token in laptop_source for token in (
                'TARGET = "audiohub.laptop"',
                '"--target=" + target',
                "validate_options(sender_ip, bind_ip, port, unsafe_lan_test)",
                "target = lan_target()",
                "if lan_target() != target:",
                'parser.add_argument("--unsafe-lan-test", action="store_true"',
                '"10.0.0.0/8"',
            )
        ) and all(
            token in buffer_source for token in (
                "MAX_BUFFER_PACKETS = 16",
                "MAX_PCM_PACKET_BYTES = 1152",
                "self._packets.popleft()",
            )
        )
    except OSError:
        checks["laptop_manual_receiver_packaged"] = False
    # This optional unauthenticated LAN receiver must never reintroduce
    # unbounded pw-dump/wpctl stderr or stdout after the live runtime and
    # hardware preflight were moved to the safe bounded process reader.
    try:
        laptop_source = (source / "network_laptop.py").read_text()
        capture_source = (source / "process_capture.py").read_text()
        checks["manual_laptop_pipewire_capture_bounded"] = all(
            token in laptop_source for token in (
                "from .process_capture import bounded_command_output",
                'bounded_command_output(("pw-dump",), timeout=5)',
                '("wpctl", "set-default", str(output["id"])), timeout=5,',
                "if result is None or result.returncode != 0:",
                "if selected is None or selected.returncode != 0:",
            )
        ) and not any(token in laptop_source for token in (
            "capture_output=True", "subprocess.run(", "shell=True",
        )) and all(
            token in capture_source for token in (
                "MAX_COMMAND_STDOUT_BYTES = 4 * 1024 * 1024",
                "selectors.DefaultSelector()",
                "stderr=subprocess.DEVNULL",
                "start_new_session=True",
            )
        )
    except OSError:
        checks["manual_laptop_pipewire_capture_bounded"] = False
    systemd_paths = (
        root / "etc/systemd/system", root / "etc/systemd/user",
    )
    try:
        service_files = [
            file for folder in systemd_paths if folder.is_dir()
            for file in folder.rglob("*.service") if file.is_file()
        ]
        checks["laptop_receiver_not_autostarted"] = (
            bool(service_files)
            and not any(
                "audiohub-laptop" in file.name
                or "audiohub-network" in file.name
                or "audiohub.network_laptop" in file.read_text(errors="replace")
                or "--unsafe-lan-test" in file.read_text(errors="replace")
                for file in service_files
            )
        )
    except OSError:
        checks["laptop_receiver_not_autostarted"] = False
    # User-defined display names must remain an offline user-only model until
    # authenticated owner provisioning exists. A public status/POST API would
    # leak local preferences or allow remote network-triggered mutations.
    try:
        profiles = (source / "input_profiles.py").read_text()
        js = (root / "opt/audiohub/web/app.js").read_text()
        webserver = (source / "webserver.py").read_text()
        checks["editable_names_offline_no_public_api"] = all(
            required in profiles for required in (
                'SLOTS = ("music", "laptop", "tablet")',
                "MAX_NAME_CHARS = 32",
                "O_NOFOLLOW",
                "fcntl.flock",
            )
        ) and all(
            required in js for required in (
                "audiohub.preview.input-labels.v1",
                "localStorage.setItem",
                "nameInput.addEventListener",
            )
        ) and 'def do_POST(self):' in webserver and (
            "Read-only preview" in webserver
        ) and "input_profiles" not in webserver
    except OSError:
        checks["editable_names_offline_no_public_api"] = False
    # Physical input rebinding cannot originate from public status or
    # unauthenticated LAN packets. A private local policy must reserve the
    # manual LAN slot and keep Bluetooth streams off that same EQ input.
    try:
        routes = (source / "source_routes.py").read_text()
        supervisor = (source / "runtime.py").read_text()
        receiver = (source / "network_laptop.py").read_text()
        checks["source_routing_isolated_and_fail_closed"] = all(
            token in routes for token in (
                'FILENAME = "source-routes.json"',
                'MAX_FILE_BYTES = 4096',
                'os.O_NOFOLLOW',
                'fcntl.flock',
                'if slot in used:',
                'def lan_target(directory=None):',
            )
        ) and all(
            token in supervisor for token in (
                "load_routes(CONFIG)",
                'plan["mode"] == "manual"',
                'channel != getattr(self, "route_plan", default_routes())["lan_slot"]',
                'self.route_policy_valid = False',
            )
        ) and all(
            token in receiver for token in (
                'target = lan_target()',
                'check_audio_target(target)',
                'player_command(target)',
                'if lan_target() != target:',
            )
        )
    except OSError:
        checks["source_routing_isolated_and_fail_closed"] = False
    # A green rootfs audit must not regress to name-only audio topology
    # assertions. The runtime must extract actual, bounded PipeWire Link
    # node IDs and report only aggregate counts on the offline SD card.
    try:
        graph_source = (source / "audio_graph.py").read_text()
        preflight_source = (source / "hardware_preflight.py").read_text()
        runtime_source = (source / "runtime.py").read_text()
        offline_source = (source / "firstboot_diag.py").read_text()
        checks["privacy_safe_pipewire_link_observation"] = all(
            token in graph_source for token in (
                "def summarize_links(raw):",
                '"PipeWire:Interface:Link"',
                '"output-node-id"',
                '"input-node-id"',
                '"release_ready": False',
            )
        ) and "summarize_links" in preflight_source and all(
            token in runtime_source for token in (
                "summarize_links(result.stdout",
                '"eq_output_usb_direct_links"',
                '"pipewire_links_inspected"',
            )
        ) and all(
            token in offline_source for token in (
                '"pipewire_links_inspected"',
                '"eq_usb_direct_links"',
            )
        )
    except OSError:
        checks["privacy_safe_pipewire_link_observation"] = False
    # Verify packaged web assets are actual local files. Symlinked webroots,
    # locale directories, files, FIFOs or huge resources are release blockers
    # even when the read-only Python server would fail closed at runtime.
    static_root = root / "opt/audiohub/web"
    web_dirs = ("opt", "opt/audiohub", "opt/audiohub/web",
                "opt/audiohub/web/locales")
    static_names = ("index.html", "app.js", "styles.css") + tuple(
        "locales/" + lang + ".json" for lang in LANGUAGES
    )
    safe_directories = all(
        (root / name).is_dir() and not (root / name).is_symlink()
        for name in web_dirs
    )
    safe_files = safe_directories
    for name in static_names:
        path = static_root / name
        try:
            metadata = path.lstat()
            file_safe = (stat.S_ISREG(metadata.st_mode)
                         and 0 < metadata.st_size <= 512 * 1024)
        except OSError:
            file_safe = False
        safe_files = safe_files and file_safe
    checks["web_static_files_nofollow_regular_bounded"] = safe_files
    for name in ("index.html", "app.js", "styles.css"):
        checks["web_" + name] = (root / "opt/audiohub/web" / name).is_file()
    base_keys = None
    for language in LANGUAGES:
        try:
            data = json.loads((root / "opt/audiohub/web/locales" / (language + ".json")).read_text())
            keys = set(data) if isinstance(data, dict) else set()
            valid = len(keys) >= 25 and all(
                isinstance(value, str) and value.strip() for value in data.values()
            )
            if language == "en":
                base_keys = keys
            checks["locale_" + language] = valid and keys == base_keys
        except (OSError, ValueError, TypeError, AttributeError):
            checks["locale_" + language] = False
    try:
        passwd = (root / "etc/passwd").read_text()
        checks["audiohub_user"] = any(
            line.startswith("audiohub:") and ":/home/audiohub:" in line
            for line in passwd.splitlines()
        )
    except OSError:
        checks["audiohub_user"] = False
    for name, (unit_path, enabled_path, command) in SERVICES.items():
        unit = root / unit_path
        enabled = root / enabled_path
        try:
            data = unit.read_text()
            checks[name + "_service"] = (
                command in data and "Restart=always" in data and "NoNewPrivileges=yes" in data
            )
        except OSError:
            checks[name + "_service"] = False
        # Absolute symlinks refer to the target image root, not the CI host.
        if enabled.is_symlink():
            link = os.readlink(enabled)
            target = (root / link.lstrip("/")) if os.path.isabs(link) else (enabled.parent / link)
            checks[name + "_enabled"] = target.is_file()
        else:
            checks[name + "_enabled"] = False
    checks["user_linger_enabled"] = (root / "var/lib/systemd/linger/audiohub").is_file()
    checks["ssh_not_autostarted"] = not any(
        (root / path).exists() or (root / path).is_symlink()
        for path in (
            "etc/systemd/system/multi-user.target.wants/ssh.service",
            "etc/systemd/system/multi-user.target.wants/sshd.service",
        )
    )
    for binary in REQUIRED_BINARIES:
        path = root / "usr/bin" / binary
        checks["binary_" + binary] = path.exists()
    eq = root / "home/audiohub/.config/pipewire/pipewire.conf.d/90-audiohub-eq.conf"
    try:
        config = eq.read_text()
        checks["independent_eq_virtual_sinks"] = all(
            'node.name = "audiohub.' + channel + '"' in config
            for channel in CHANNELS
        ) and config.count("libpipewire-module-filter-chain") == len(CHANNELS)
        checks["eq_not_world_writable"] = not bool(eq.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH))
    except OSError:
        checks["independent_eq_virtual_sinks"] = False
        checks["eq_not_world_writable"] = False
    try:
        bluetooth_unit = (root / SERVICES["bluetooth"][0]).read_text()
        checks["bluetooth_no_admin_api"] = "audiohub.webserver" not in bluetooth_unit
    except OSError:
        checks["bluetooth_no_admin_api"] = False
    for path in ("opt/audiohub/src/audiohub", "opt/audiohub/web"):
        try:
            checks["safe_permissions_" + path.replace("/", "_")] = not bool(
                (root / path).stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            )
        except OSError:
            checks["safe_permissions_" + path.replace("/", "_")] = False
    return checks


def run(root: Path) -> int:
    results = inspect(root)
    failures = sorted(name for name, passed in results.items() if not passed)
    report = {
        "schema": "rivanox-audiohub-rootfs-preflight/1",
        "scope": "build-time packaging only; NOT a hardware boot or security sign-off",
        "passed": not failures,
        "checks": results,
        "failed_checks": failures,
    }
    if root.is_dir():
        path = root / "usr/share/doc/audiohub/rootfs-preflight.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "failed_checks": failures, "count": len(results)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isabs(sys.argv[1]):
        print("Expected absolute root filesystem directory", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(Path(sys.argv[1])))
