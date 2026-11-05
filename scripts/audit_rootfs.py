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
REQUIRED_BINARIES = ("python3", "pw-dump", "pw-loopback", "wpctl", "bluetoothctl")


def inspect(root: Path) -> dict[str, bool]:
    """Return named checks with no secrets or identifying information."""
    if not root.is_dir():
        return {"rootfs_exists": False}
    checks: dict[str, bool] = {}
    source = root / "opt/audiohub/src/audiohub"
    for name in ("__init__.py", "runtime.py", "pairing.py", "mixer.py", "webserver.py", "status_bind.py", "firstboot_diag.py"):
        checks["source_" + name] = (source / name).is_file()
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
            and "ThreadingHTTPServer((select_bind_address(), 8765)" in webserver
            and "0.0.0.0" not in webserver
        )
        checks["status_service_no_unsafe_lan_opt_in"] = (
            "AUDIOHUB_UNSAFE_STATUS_LAN" not in status_unit
            and "AUDIOHUB_STATUS_BIND_IP" not in status_unit
        )
    except OSError:
        checks["status_loopback_default"] = False
        checks["status_web_uses_guarded_bind"] = False
        checks["status_service_no_unsafe_lan_opt_in"] = False
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
