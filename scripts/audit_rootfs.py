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


MAX_EQ_AUDIT_BYTES = 64 * 1024
EQ_CONFIG_PATH = "home/audiohub/.config/pipewire/pipewire.conf.d/90-audiohub-eq.conf"


def _read_private_eq_config(root: Path):
    """Read only a bounded regular EQ file inside the actual image rootfs.

    A pre-export audit must not follow a file or directory symlink into the
    builder's host filesystem or block on a FIFO. Hardlinks are also rejected.
    Return (decoded text, mode) or None; never expose raw content on failure.
    """
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = None
    eqfd = None
    try:
        fd = os.open(root, directory_flags)
        parts = Path(EQ_CONFIG_PATH).parts
        for component in parts[:-1]:
            nextfd = os.open(component, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = nextfd
        eqfd = os.open(parts[-1], file_flags, dir_fd=fd)
        info = os.fstat(eqfd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= MAX_EQ_AUDIT_BYTES):
            return None
        raw = os.read(eqfd, MAX_EQ_AUDIT_BYTES + 1)
        if len(raw) != info.st_size:
            return None
        return raw.decode("utf-8"), info.st_mode
    except (OSError, UnicodeError):
        return None
    finally:
        if eqfd is not None:
            os.close(eqfd)
        if fd is not None:
            os.close(fd)


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
    # The root-owned offline SD diagnostic must not translate malformed or
    # ambiguous audiohub-owned JSON into an apparent healthy hardware report.
    try:
        offline_source = (source / "firstboot_diag.py").read_text()
        checks["offline_diag_json_integrity_fail_closed"] = all(
            mark in offline_source for mark in (
                "def _unique_runtime_json_object(pairs):",
                'raise ValueError("duplicate diagnostic runtime JSON member")',
                "object_pairs_hook=_unique_runtime_json_object",
                "def _reject_runtime_json_constant(_value):",
                "parse_constant=_reject_runtime_json_constant",
                "except (UnicodeError, ValueError, RecursionError):",
            )
        )
    except OSError:
        checks["offline_diag_json_integrity_fail_closed"] = False
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
    # Contradictory BlueZ identity metadata must not silently select one
    # sender MAC and admit a different physical source for audio capture.
    try:
        discovery_source = (source / "discovery.py").read_text()
        start = discovery_source.index("def bluetooth_sources(nodes):")
        end = discovery_source.index("def virtual_sinks(nodes):", start)
        bt_source = discovery_source[start:end]
        checks["bluetooth_dual_address_metadata_agrees"] = all(
            mark in bt_source for mark in (
                'for field in ("api.bluez5.address", "device.address"):',
                "if field not in value:",
                "stated = value[field]",
                "type(stated) is not str",
                "_MAC.fullmatch(stated) is None",
                "stated.upper() != name_mac",
                "if address_conflict:",
            )
        ) and 'value.get("api.bluez5.address") or' not in bt_source
    except (OSError, ValueError):
        checks["bluetooth_dual_address_metadata_agrees"] = False
    # A malformed BlueZ profile is still a duplicate identity candidate:
    # check same-MAC collision BEFORE returning early on metadata mismatch.
    try:
        discovery_source = (source / "discovery.py").read_text()
        start = discovery_source.index("def bluetooth_sources(nodes):")
        end = discovery_source.index("def virtual_sinks(nodes):", start)
        bt = discovery_source[start:end]
        duplicate = bt.index("if name_mac in seen:")
        seen_mark = bt.index("seen.add(name_mac)", duplicate)
        metadata = bt.index('for field in ("api.bluez5.address", "device.address"):')
        checks["bluetooth_duplicate_mac_checked_before_metadata"] = (
            duplicate < seen_mark < metadata
            and "conflicted.add(name_mac)" in bt
            and 'return [source for source in result if source["address"] not in conflicted]' in bt
        )
    except (OSError, ValueError):
        checks["bluetooth_duplicate_mac_checked_before_metadata"] = False
    # Real PipeWire metadata is untrusted: one JSON object with duplicate
    # Node IDs or Link endpoints must not become a last-wins valid graph,
    # and a deeply nested but size-bounded pw-dump must not crash services.
    try:
        discovery_source = (source / "discovery.py").read_text()
        graph_source = (source / "audio_graph.py").read_text()
        checks["pipewire_nodes_and_links_strict_shared_json_snapshot"] = all(
            marker in discovery_source for marker in (
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
            )
        ) and all(
            marker in graph_source for marker in (
                "_parse_pipewire_graph,",
                "graph = _parse_pipewire_graph(raw)",
            )
        )
    except OSError:
        checks["pipewire_nodes_and_links_strict_shared_json_snapshot"] = False
    # Hardware preflight reports count of sources eligible for routing,
    # not arbitrary bluez_input-named PipeWire objects with invalid identity.
    try:
        preflight = (source / "hardware_preflight.py").read_text()
        checks["hardware_preflight_only_counts_valid_bt_sources"] = (
            "from .discovery import _conflicting_node_ids, bluetooth_sources, pipewire_nodes" in preflight
            and "bluetooth = len(bluetooth_sources(nodes))" in preflight
            and 'name.startswith("bluez_input.")' not in preflight
            and '"bluetooth_source_count": bluetooth' in preflight
            and '"release_ready": False' in preflight
        )
    except OSError:
        checks["hardware_preflight_only_counts_valid_bt_sources"] = False
    # Read-only topology must agree with the real production USB/EQ target
    # selection, or a misleading "ready for manual test" could be shown.
    try:
        preflight = (source / "hardware_preflight.py").read_text()
        checks["hardware_preflight_uses_routable_usb_eq_targets"] = all(
            marker in preflight for marker in (
                "from .discovery import choose_usb_output, virtual_sinks",
                "routable = virtual_sinks(nodes)",
                'logical = {name: "audiohub." + name in routable for name in CHANNELS}',
                "selected_usb = choose_usb_output(nodes)",
                "selected_usb.get(\"id\") == edifier_ids[0]",
                "0 < value <= 2**31 - 1",
                '"release_ready": False',
            )
        ) and "logical_counts" not in preflight and "usb = edifier == 1" not in preflight
    except OSError:
        checks["hardware_preflight_uses_routable_usb_eq_targets"] = False
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
    # A naked ready flag is insufficient to prompt an operator about
    # audible Pi4 hardware; demand coherent non-approving PipeWire results.
    try:
        manual = (source / "manual_acceptance.py").read_text()
        checks["manual_operator_preflight_consistency"] = all(
            marker in manual for marker in (
                "def _consistent_read_only_preflight(report):",
                "type(report.get(\"schema_version\")) is not int",
                'report.get("assessment") == "topology_only_not_hardware_acceptance"',
                'checks.get("pipewire_inspection_succeeded") is True',
                'checks.get("edifier_usb_sink_unique") is True',
                'set(sinks) == {"music", "laptop", "tablet"}',
                'gates.get(gate) == "unverified"',
                'ready = _consistent_read_only_preflight(preflight)',
                '"hardware_accepted": False',
                '"release_ready": False',
            )
        )
    except OSError:
        checks["manual_operator_preflight_consistency"] = False
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
    # User-owned settings and BT mapping files are parsed by the real
    # supervisor, not just read-only status paths. No contradictory keys,
    # nonfinite numbers or deep but size-bounded JSON may influence routing.
    try:
        private_runtime = (source / "runtime.py").read_text()
        checks["runtime_settings_assignments_json_fail_closed"] = all(
            token in private_runtime for token in (
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
            )
        )
    except OSError:
        checks["runtime_settings_assignments_json_fail_closed"] = False
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
        # A per-recv socket timeout can be kept alive forever by a slow
        # sender; cap total request lifetime and suppress peer-bearing tracebacks.
        checks["status_http_total_lifetime_and_peer_error_privacy"] = all(
            mark in webserver for mark in (
                "CLIENT_MAX_LIFETIME_SECONDS = 15",
                "threading.Timer(",
                "watchdog.start()",
                "watchdog.cancel()",
                "request.shutdown(socket.SHUT_RDWR)",
                "def handle_error(self, request, client_address):",
            )
        )
        # A malformed status JSON document or HTTP absolute request URI
        # must fail closed, rather than throw out of the alpha status handler.
        checks["status_malformed_inputs_fail_closed"] = all(
            mark in webserver for mark in (
                "decoded = json.loads(",
                'body.decode("utf-8")',
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
        # Python json.loads accepts 1e999 as float('inf') even when
        # NaN/Infinity tokens are rejected via parse_constant. Both the
        # web status and root-owned boot diagnostic must reject overflow.
        offline_diag_source = (source / "firstboot_diag.py").read_text()
        checks["status_and_offline_json_finite_exponent_guard"] = all(
            token in webserver for token in (
                "def _finite_status_json_float(number):",
                "math.isfinite(value)",
                "parse_float=_finite_status_json_float",
            )
        ) and all(
            token in offline_diag_source for token in (
                "def _finite_runtime_json_float(number):",
                "math.isfinite(value)",
                "parse_float=_finite_runtime_json_float",
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
        checks["status_and_offline_json_finite_exponent_guard"] = False
        checks["status_http_total_lifetime_and_peer_error_privacy"] = False
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
    # BlueZ Device1.Trusted may survive unpairing. Reject unpaired trusted
    # devices instead of treating stale trust as unconditional A2DP authority.
    try:
        agent = (source / "pairing.py").read_text()
        start = agent.index("def AuthorizeService(self, device, uuid):")
        end = agent.index("def RequestConfirmation(self, device, passkey):", start)
        service = agent[start:end]
        trusted = service.index('if p.Get("org.bluez.Device1", "Trusted"):')
        paired = service.index('if not p.Get("org.bluez.Device1", "Paired"):', trusted)
        denied = service.index('raise Rejected("Unpaired trusted device")', paired)
        allowed = service.index("return", denied)
        checks["bluetooth_trusted_service_requires_paired"] = trusted < paired < denied < allowed
    except (OSError, ValueError):
        checks["bluetooth_trusted_service_requires_paired"] = False
    # BlueZ Device1.Paired=False or property invalidation may arrive
    # without Agent1.Cancel; revoke the specific pending trust token.
    try:
        pairing_source = (source / "pairing.py").read_text()
        changed_body = pairing_source.split(
            "def changed(self, interface, change, invalidated, path=None):", 1
        )[1].split("@dbus.service.method", 1)[0]
        checks["bluetooth_unpaired_event_revokes_pending_trust"] = all(
            marker in changed_body for marker in (
                'if ((invalidated and "Paired" in invalidated)',
                'or ("Paired" in change and not change["Paired"])):',
                "self.pending_authorizations.pop(path, None)",
                'if not change.get("Paired"):',
            )
        )
    except (OSError, IndexError):
        checks["bluetooth_unpaired_event_revokes_pending_trust"] = False
    # BlueZ Agent1.Cancel has no device argument. A canceled pairing must
    # revoke all pending one-use trust tokens, not just close the UI.
    try:
        pairing_source = (source / "pairing.py").read_text()
        cancel_body = pairing_source.split("def Cancel(self):", 1)[1].split(
            "def main():", 1
        )[0]
        checks["bluetooth_cancel_revokes_pending_trust"] = (
            cancel_body.strip().startswith("# BlueZ canceled")
            and cancel_body.strip().endswith("self.pending_authorizations.clear()")
            and "pass" not in cancel_body
        )
    except (OSError, IndexError):
        checks["bluetooth_cancel_revokes_pending_trust"] = False
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
    # Master gain attenuation and source muting must be applied to the
    # actual USB/PipeWire nodes before new managed sources are admitted.
    # A failed or missing wpctl result must tear down running routes.
    try:
        mixer_source = (source / "mixer.py").read_text()
        runtime_source = (source / "runtime.py").read_text()
        mixer_at = mixer_source.index("def volume_commands(settings, sink_ids, output_id=None):")
        master_at = mixer_source.index("if output_id is not None:", mixer_at)
        channel_at = mixer_source.index("for channel in CHANNELS:", mixer_at)
        poll_at = runtime_source.index("    def poll(self):")
        control_at = runtime_source.index("for args in volume_commands(", poll_at)
        route_at = runtime_source.index("self._route(sources if", poll_at)
        checks["mixer_master_gain_verified_before_managed_routes"] = (
            master_at < channel_at
            and control_at < route_at
            and "applied = run(*args)" in runtime_source
            and "if applied is None or applied.returncode != 0:" in runtime_source
            and 'raise RuntimeError("AudioHub mixer control failed")' in runtime_source
            and "self._stop_all_managed_routes()" in runtime_source
        )
    except (OSError, ValueError):
        checks["mixer_master_gain_verified_before_managed_routes"] = False
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
    # User-owned mixer JSON can contain a large integer within the bounded
    # JSON file: it must raise ValueError, never math.isfinite(int) OverflowError.
    try:
        mixer = (source / "mixer.py").read_text()
        checks["mixer_huge_integer_controls_fail_closed"] = all(
            token in mixer for token in (
                "def _integer(value, lower, upper):",
                "if type(value) is int:",
                "if lower <= value <= upper:",
                "if type(value) is not float:",
                "not math.isfinite(value)",
                "value.is_integer()",
                "return int(value)",
                'raise ValueError("value out of range")',
            )
        ) and "math.isfinite(value) or int(value) != value" not in mixer
    except OSError:
        checks["mixer_huge_integer_controls_fail_closed"] = False
    # Source/router IDs come from PipeWire metadata; volume controls must
    # never coerce booleans/floats/strings or reuse one ID for two targets.
    try:
        mixer = (source / "mixer.py").read_text()
        checks["mixer_wpctl_target_ids_strict_unique"] = all(
            marker in mixer for marker in (
                "def _validated_wpctl_targets(sink_ids, output_id):",
                "MAX_PIPEWIRE_NODE_ID = 2**31 - 1",
                "type(sink_ids) is not dict",
                "type(output_id) is not int",
                "type(node_id) is not int",
                "node_id in used",
                "sink_ids = _validated_wpctl_targets(sink_ids, output_id)",
                "node_id = str(sink_ids[channel])",
                "str(output_id), str(effective_master_gain(settings))",
            )
        ) and "str(int(sink_ids[channel]))" not in mixer
    except OSError:
        checks["mixer_wpctl_target_ids_strict_unique"] = False
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
    # The manual unauthenticated LAN player must tear down a blocked
    # pw-cat even when zero PCM writes have ever completed successfully.
    try:
        laptop_source = (source / "network_laptop.py").read_text()
        start = laptop_source.index("os.set_blocking(player.stdin.fileno(), False)")
        deadline = laptop_source.index("last_written_at = now", start)
        next_check = laptop_source.index("next_health_check = now + HEALTH_CHECK_SECONDS", start)
        checks["manual_lan_first_pcm_write_stall_bounded"] = (
            "IDLE_SECONDS = 5.0" in laptop_source
            and "if last_written_at is not None and now - last_written_at >= IDLE_SECONDS:" in laptop_source
            and start < deadline < next_check
            and "last_written_at = None" in laptop_source
            and "backlog.clear()" in laptop_source
            and "except BlockingIOError:" in laptop_source
        )
    except (OSError, ValueError):
        checks["manual_lan_first_pcm_write_stall_bounded"] = False
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
    # Preview input labels must use a real ECMAScript Unicode category
    # escape (one slash), not a literal backslash/p/C character class.
    # Mirror the local Python model: reject control/format/bidi/markup.
    try:
        preview = (root / "opt/audiohub/web/app.js").read_text()
        checks["web_preview_input_name_unicode_controls_safe"] = (
            r"/[\p{C}<>]/u.test(name)" in preview
            and r"/[\\p{C}<>]/u.test(name)" not in preview
            and "Array.from(name).length > 32" in preview
            and "title.textContent = tr(key)" in preview
        )
    except OSError:
        checks["web_preview_input_name_unicode_controls_safe"] = False
    # Stale async locale completions must never overwrite a newer user
    # language selection or trigger an obsolete English fallback.
    try:
        preview = (root / "opt/audiohub/web/app.js").read_text()
        checks["web_preview_latest_language_request_wins"] = all(
            token in preview for token in (
                "let languageRequestId = 0;",
                "const requestId = ++languageRequestId;",
                "if (requestId !== languageRequestId) return;",
            )
        ) and preview.count("if (requestId !== languageRequestId) return;") >= 2
    except OSError:
        checks["web_preview_latest_language_request_wins"] = False
    # Even if both requested and English locale fetches fail, the preview
    # must use the same metadata commit path as a successful English request.
    try:
        preview = (root / "opt/audiohub/web/app.js").read_text()
        checks["web_preview_english_fallback_metadata_consistent"] = all(
            token in preview for token in (
                'if (language !== "en") return setLanguage("en");',
                'data = { tagline: "All your audio. One place." };',
                "if (requestId !== languageRequestId) return;",
                "document.documentElement.lang = language;",
                'byId("language").value = language;',
                'localStorage.setItem("audiohub.locale", language)',
            )
        ) and 'words = { tagline: "All your audio. One place." };' not in preview
    except OSError:
        checks["web_preview_english_fallback_metadata_consistent"] = False
    # Slow or failed read-only status polling may not replace newer health
    # results, even when JSON decoding itself completes out of order.
    try:
        preview = (root / "opt/audiohub/web/app.js").read_text()
        start = preview.index("  async function readDeviceStatus() {")
        end = preview.index("  function translate()", start)
        reader = preview[start:end]
        checks["web_preview_latest_status_poll_wins"] = (
            "let statusRequestId = 0;" in preview
            and "const requestId = ++statusRequestId;" in reader
            and reader.count("if (requestId !== statusRequestId) return;") == 2
            and 'fetch("./api/status", {cache: "no-store"})' in reader
            and "deviceHealth = json && typeof json === \"object\" ? json : null;" in reader
            and "deviceHealth = null;" in reader
            and "renderHardwareStatus();" in reader
        )
    except (OSError, ValueError):
        checks["web_preview_latest_status_poll_wins"] = False
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
    # Offline configuration is user-owned and mutable, but must not hang
    # a runtime worker on a FIFO or accept last-wins duplicate JSON members.
    try:
        routes_source = (source / "source_routes.py").read_text()
        profile_source = (source / "input_profiles.py").read_text()
        checks["source_route_config_strict_nonblocking_read"] = all(
            marker in routes_source for marker in (
                "os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW",
                "if len(raw) != st.st_size:",
                "object_pairs_hook=_unique_route_members",
                "parse_constant=_reject_route_constant",
                "except (UnicodeError, ValueError, RecursionError):",
            )
        )
        checks["input_profile_config_strict_nonblocking_read"] = all(
            marker in profile_source for marker in (
                "os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW",
                "if len(data) != meta.st_size:",
                "object_pairs_hook=_unique_profile_members",
                "parse_constant=_reject_profile_constant",
                "except (UnicodeError, ValueError, RecursionError):",
            )
        )
    except OSError:
        checks["source_route_config_strict_nonblocking_read"] = False
        checks["input_profile_config_strict_nonblocking_read"] = False
    # O_NOFOLLOW only secures the final component of a single os.open(path).
    # Private route and label access must use a descriptor walk from "/" so
    # an ancestor alias cannot redirect local read or atomic profile writes.
    try:
        routes_source = (source / "source_routes.py").read_text()
        profile_source = (source / "input_profiles.py").read_text()
        required = (
            'dirfd = os.open("/", flags)',
            'for component in path.parts[1:]:',
            'nextfd = os.open(component, flags, dir_fd=dirfd)',
            'if ".." in path.parts:',
            'os.mkdir(component, mode=0o700, dir_fd=dirfd)',
            'if dirfd is not None:',
        )
        checks["private_config_ancestor_symlink_fd_walk"] = (
            all(marker in routes_source for marker in required)
            and all(marker in profile_source for marker in required)
            and "dirfd = _safe_dir(directory, create=True)" in profile_source
            and "directory.mkdir(parents=True" not in profile_source
            and "path.mkdir(parents=True" not in routes_source
        )
    except OSError:
        checks["private_config_ancestor_symlink_fd_walk"] = False
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
    # Runtime EQ setup must never follow user-controlled symlinks or
    # overwrite a hardlinked/unprivileged audio configuration in place.
    try:
        eq_setup_source = (source / "eq_setup.py").read_text()
        checks["eq_setup_private_atomic_nofollow"] = all(
            marker in eq_setup_source for marker in (
                "MAX_EQ_CONFIG_BYTES = 64 * 1024",
                "def _safe_eq_parent_fd(target):",
                "os.O_DIRECTORY | os.O_NOFOLLOW",
                "os.mkdir(component, mode=0o700, dir_fd=fd)",
                "stat.S_IMODE(st.st_mode) & 0o077",
                "os.stat(target.name, dir_fd=dirfd, follow_symlinks=False)",
                "not stat.S_ISREG(prior.st_mode)",
                "prior.st_nlink != 1",
                "os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW",
                "secrets.token_hex(12)",
                "os.fsync(out)",
                "os.replace(temp, target.name, src_dir_fd=dirfd, dst_dir_fd=dirfd)",
                "os.fsync(dirfd)",
            )
        ) and "target.write_text(" not in eq_setup_source
    except OSError:
        checks["eq_setup_private_atomic_nofollow"] = False
    # Parallel local setup may race directory creation; cleanup errors
    # must never leak descriptors or conceal the original EQ write failure.
    try:
        eq_setup_source = (source / "eq_setup.py").read_text()
        checks["eq_setup_concurrent_create_cleanup_safe"] = all(
            marker in eq_setup_source for marker in (
                "except FileExistsError:",
                "nextfd = os.open(component, flags, dir_fd=fd)",
                "except OSError:",
                "os.unlink(temp, dir_fd=dirfd)",
                "finally:\n            os.close(dirfd)",
            )
        )
    except OSError:
        checks["eq_setup_concurrent_create_cleanup_safe"] = False
    # The image checker itself must be safe against symlinks and special
    # files in an untrusted staging tree (even when the runtime writer is safe).
    eq_snapshot = _read_private_eq_config(root)
    checks["eq_rootfs_nofollow_regular_singlelink_bounded"] = eq_snapshot is not None
    if eq_snapshot is None:
        checks["independent_eq_virtual_sinks"] = False
        checks["eq_not_world_writable"] = False
    else:
        config, mode = eq_snapshot
        checks["independent_eq_virtual_sinks"] = all(
            'node.name = "audiohub.' + channel + '"' in config
            for channel in CHANNELS
        ) and config.count("libpipewire-module-filter-chain") == len(CHANNELS)
        checks["eq_not_world_writable"] = not bool(mode & (stat.S_IWGRP | stat.S_IWOTH))
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
