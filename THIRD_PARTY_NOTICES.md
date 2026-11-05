# Third-party software and compliance

This repository publishes RIVANOX-authored orchestration and UI code under AGPL-3.0-only. A produced Raspberry Pi OS image additionally contains multiple independently licensed third-party components. **The RIVANOX license does not change their terms.**

| Component | Purpose | Source / license verification |
| --- | --- | --- |
| Raspberry Pi OS / Debian | Operating system | https://www.raspberrypi.com/software/ ; Debian package copyright files |
| Raspberry Pi pi-gen | Image builder | https://github.com/RPi-Distro/pi-gen |
| PipeWire | Audio routing and filter-chain | https://pipewire.pages.freedesktop.org/pipewire/ |
| WirePlumber | Session policy | https://pipewire.pages.freedesktop.org/wireplumber/ |
| BlueZ | Bluetooth stack | https://www.bluez.org/ |
| Scream | Optional network-audio receiver | https://github.com/duncanthrax/scream — MS-PL for the referenced upstream project |
| Flask and Python libraries | Local web control | Installed package metadata and associated licenses |

Before publishing binaries, archive exact dependency versions, redistributable source and applicable license/notice files. Retain upstream attribution; do not claim copyright over those components. Do not bundle streaming-service trademarks or copyrighted media. Spotify and similar services are independent; compatibility statements must not imply endorsement.

The exact composition and legal obligations of a future image must be audited on the artifact actually shipped, not inferred from this provisional list.

## Generated package inventory for future image reviews

The inventory-enabled experimental image branch produces a deterministic
`ROOTFS-PACKAGES.json` from the **built** dpkg database. It records installed
package name, version and architecture, plus SHA-256 of an available Debian
package copyright notice (or an explicit missing marker). Its schema expressly
reports `legal_review_approved=false`, and the preview bundle validator rejects
extra/secret-bearing fields or false legal claims. This is evidence for manual
review, **not** a complete SBOM, patent clearance, third-party license grant,
or authorization to redistribute an image. Missing notices require follow-up.

## Forward-looking Model C review — NOT EFFECTIVE

The owner's planned personal-free/commercial-license model applies **only**
to future separately identified original material where RIVANOX has adequate
rights. This document is not an assignment of Debian, Raspberry Pi OS,
pi-gen, PipeWire, WirePlumber, BlueZ, upstream Scream, firmware, kernel,
or other third-party copyrights. Even an approved future proprietary
RIVANOX license cannot remove applicable upstream GPL/AGPL obligations,
attribution, copyright notices or rights of legitimate prior AGPL users.
See [current rights audit](docs/licensing/RIGHTS-AUDIT-2026-11-05.md) and
[Model C proposed terms](LICENSE-C-DRAFT.md). Full binary/legal audit
and source-of-dependencies checklist remain open.
