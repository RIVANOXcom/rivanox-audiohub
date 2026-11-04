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
    for name in ("__init__.py", "runtime.py", "pairing.py", "mixer.py", "webserver.py"):
        checks["source_" + name] = (source / name).is_file()
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
        checks[name + "_enabled"] = enabled.is_symlink() and enabled.resolve().is_file()
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
