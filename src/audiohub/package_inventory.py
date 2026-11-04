# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only source package inventory for the unverified AudioHub Pi4 image.

An install-stage package list is not a rootfs SBOM or a legal license audit:
transitive dependencies, exact versions and copyright texts are still unknown.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
PIN_PATTERN = re.compile(r"(?m)^PIN=\"([0-9a-f]{40})\"$")
PACKAGE_LIST = Path("image/stage-audiohub/00-packages/00-packages-nr")

# A source-level reference only, NOT verified package ownership or license.
NOTICE_GROUP = {
    "bluez": "BlueZ",
    "pipewire": "PipeWire",
    "pipewire-bin": "PipeWire",
    "pipewire-pulse": "PipeWire",
    "wireplumber": "WirePlumber",
    "libspa-0.2-bluetooth": "PipeWire",
    "alsa-utils": "Raspberry Pi OS / Debian",
    "pulseaudio-utils": "Raspberry Pi OS / Debian",
    "python3": "Raspberry Pi OS / Debian",
    "python3-dbus": "Raspberry Pi OS / Debian",
    "python3-gi": "Raspberry Pi OS / Debian",
    "network-manager": "Raspberry Pi OS / Debian",
    "avahi-daemon": "Raspberry Pi OS / Debian",
    "rfkill": "Raspberry Pi OS / Debian",
    "jq": "Raspberry Pi OS / Debian",
}


def package_names(contents):
    """Parse one Debian source package name per line without shell expansion."""
    names = []
    seen = set()
    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not PACKAGE_PATTERN.fullmatch(line):
            raise ValueError("Invalid image-stage package entry")
        if line in seen:
            raise ValueError("Duplicate image-stage package")
        seen.add(line)
        names.append(line)
    if not names:
        raise ValueError("Empty package list")
    return sorted(names)


def inspect_source(packages_text, notices_text, build_text):
    """Return a deterministic honest inventory, NEVER binary license approval."""
    names = package_names(packages_text)
    pins = PIN_PATTERN.findall(build_text)
    pin = pins[0] if len(pins) == 1 else None
    inventory = []
    uncovered = []
    for name in names:
        notice = NOTICE_GROUP.get(name)
        present = bool(notice and ("| " + notice + " |") in notices_text)
        if not present:
            uncovered.append(name)
        inventory.append({
            "package": name,
            "source_notice_group": notice,
            "group_listed_in_notices": present,
            "resolved_version": None,
            "copyright_file_audited": False,
            "license_verified": False,
        })
    return {
        "schema_version": 1,
        "assessment": "source_declarations_only_not_sbom",
        "package_count": len(inventory),
        "pi_gen_source_pin": pin,
        "missing_notice_reference": uncovered,
        "packages": inventory,
        "missing_release_evidence": [
            "actual_image_rootfs_package_versions",
            "complete_transitive_dependencies",
            "installed_debian_copyright_files",
            "third_party_license_obligations_and_source_offers",
            "reviewer_signoff_for_exact_release_artifact",
        ],
        "source_inventory_consistent": bool(pin and not uncovered),
        "license_audit_accepted": False,
        "release_ready": False,
    }


def probe_repo(root):
    """Inspect repository source files only; no execution or network requests."""
    root = Path(root)
    return inspect_source(
        (root / PACKAGE_LIST).read_text(encoding="utf-8"),
        (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
        (root / "build-image.sh").read_text(encoding="utf-8"),
    )


def main():
    root = Path(__file__).resolve().parents[2]
    try:
        report = probe_repo(root)
    except (OSError, UnicodeError, ValueError):
        report = {
            "schema_version": 1,
            "assessment": "source_inventory_invalid",
            "source_inventory_consistent": False,
            "license_audit_accepted": False,
            "release_ready": False,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["source_inventory_consistent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
