<div align="center">

# 🎚️ RIVANOX AudioHub

### One speaker system. Multiple audio sources. Your mix.

**A headless, multilingual, open-source audio mixer for Raspberry Pi 4.**

**Powered by [RIVANOX](https://rivanox.com)**

[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)](./docs/STATUS.md)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](./LICENSE)
[![Website](https://img.shields.io/badge/RIVANOX-Website-black)](https://rivanox.com)
[![Support on Ko-fi](https://img.shields.io/badge/Support-Ko--fi-ff5e5b)](https://ko-fi.com/RIVANOX)

</div>

## Make your existing speakers smarter

Stop choosing between music, a laptop video, and a tablet. AudioHub is being built to mix multiple simultaneous sources into one set of speakers, with **independent channel volume and EQ**. It is designed to run without a monitor or keyboard after the image has been flashed.

### Three independently named inputs — not fixed device categories

| Display slot | Current ALPHA-capable input transport | Separate controls |
| --- | --- | --- |
| **Input 1** (rename e.g. *Living room TV*) | First Bluetooth A2DP source | Volume, mute, three-band EQ |
| **Input 2** (rename e.g. *Console*) | Manual isolated LAN PCM input, **OFF by default** | Volume, mute, three-band EQ |
| **Input 3** (rename e.g. *Work PC*) | Second Bluetooth A2DP source, **hardware-unverified** | Volume, mute, three-band EQ |

You are **not** required to own a phone, laptop or tablet for the
respective slot. The internal PipeWire identifiers `music/laptop/tablet`
remain stable for compatibility; their **visible names are freely editable**.
The current web prototype saves chosen names **only in the current browser**,
not to the Pi. A separate private offline local-console storage model exists,
but authenticated phone-to-device synchronization still needs engineering.
**An isolated local-console routing policy now allows the two supported
Bluetooth source slots and the dormant, manually started LAN source to
be reassigned among the three internal EQ inputs.** It does not pair,
authenticate or enroll devices and is not accessible from the web UI.
See [offline source routing for the development bench](./docs/FLEXIBLE-SOURCE-ROUTING-LAB.md).

**Hardware note:** Two simultaneous A2DP senders have not been verified
on Pi 4. The Windows Scream receiver is plaintext/unauthenticated and is
never started automatically. Renaming a channel does not authorize a
device, select a Bluetooth peer or enable the network receiver.

**Output:** A compatible USB audio speaker, initially the Edifier R600USB, plus a master output volume control.

### The experience we are building

1. Download the latest **verified Raspberry Pi 4 SD card image**.
2. Write it to a microSD card using your preferred imaging tool.
3. Plug in your USB speakers and power the Pi.
4. Select `AudioHub` in your phone's Bluetooth device list and play audio.
5. Use a local web app to manage individual channel volumes, equalizers, radio, and connections.

No display, keyboard, SSH session, shell commands, or Linux administration should be necessary for normal use.

### Interface languages

🇬🇧 English · 🇩🇪 Deutsch · 🇪🇸 Español · 🇫🇷 Français · 🇮🇹 Italiano

**Project language:** English only. Translations are supplied as app resources; development discussions, documentation, code comments and issue templates are in English.

## Downloads and development status

> ⚠️ **Alpha development – no verified, ready-to-flash SD image has been published yet.** Source snapshots and preview builds are **not stable releases**. Do not assume they are suitable for an unattended device.

For **experimental hardware bench tests only**, the last
verified source-and-image artifact **before the flexible source-routing
changes** is [5 November Pi4 Alpha ZIP #13433476966](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064465468/artifacts/13433476966):
Actions run **42064465468**, source
`9e612290841ed586effc19ca37d2edab479d4524`,
**172 Python tests / 50 rootfs checks**, expiring 5 December 2026.
It is **not** a Release, requires GitHub sign-in, includes local naming
but does **not** contain the new free source assignments in draft PR #29.
Verify the **inner compressed image** against the bundled
`SHA256SUMS.txt`, use a spare SD and an isolated Pi without trusted
Ethernet/WLAN. A newer image from PR #29 can be called downloadable
only after its **own** successful native ARM64 build, rootfs security
audit, SHA256/XZ/manifest verification and actual artifact upload;
see [PR #29](https://github.com/RIVANOXcom/rivanox-audiohub/pull/29).
[Pi bench instructions](./docs/FIRST-PI-ALPHA-TEST.md).

Once hardware tests and security acceptance are complete, download images from:

**[Latest verified release](https://github.com/RIVANOXcom/rivanox-audiohub/releases/latest)**

The release will include `AudioHub-Pi4.img.xz`, `SHA256SUMS.txt`, and release notes. If the link currently returns 404, no verified image exists yet. A green CI status is not equivalent to a successful hardware test.

### Engineering priorities

- USB-audio discovery and recovery
- Simple Bluetooth pairing and reconnection
- Three isolated audio signal paths with per-source EQ and gain
- Local-network laptop audio
- Five-language mobile-first web app
- Offline/first-boot Wi-Fi provisioning
- Repeatable Raspberry Pi OS Lite image creation
- Reproducible dependencies, dependency attribution and verified releases
- Secure provisioning, diagnostic visibility and long-term reliability

See [status](./docs/STATUS.md), [architecture](./docs/ARCHITECTURE.md) and [release policy](./docs/RELEASE-POLICY.md) for what is and is not implemented.

**Continue development without losing decisions:** [current project handoff](./docs/PROJECT-HANDOFF.md), [prioritized engineering backlog, defects and optimizations](./docs/ENGINEERING-BACKLOG.md) and [GitHub main-branch protection setup for the owner](./docs/GITHUB-SECURITY-RULESET.md). These documents are under active draft development; `main` has not incorporated the stacked PR chain yet.

## Open source, commercial alternatives and third-party software

Original RIVANOX code is offered under **GNU AGPL-3.0-only**, subject to ownership and third-party rights. The [license](./LICENSE) governs the open-source option. Commercial alternative licensing of eligible RIVANOX-owned code may be negotiated separately; a commercial license does not automatically cover third-party dependencies or community contributions.

The AGPL does **not** require all users, including commercial users, to pay. It grants the freedoms described in its terms. Nothing in the repository represents a legal opinion or a blanket commercial sublicense for dependencies.

The RIVANOX name and branding are not automatically licensed for unrelated products. See the [trademark policy](./TRADEMARKS.md).

## Support independent software development

AudioHub is developed as an independent RIVANOX project. Your contributions can help fund hardware tests, accessibility, documentation and maintenance.

**☕ [Support RIVANOX on Ko-fi](https://ko-fi.com/RIVANOX)**

Contributions are voluntary, do not purchase a commercial software license, and do not guarantee priority support. For products and services, explore **[RIVANOX.com](https://rivanox.com)**.

## Contribute or report an issue

Read [CONTRIBUTING.md](./CONTRIBUTING.md), report functional bugs through [GitHub Issues](https://github.com/RIVANOXcom/rivanox-audiohub/issues), and submit security reports through the private process in [SECURITY.md](./SECURITY.md).

---

<div align="center">**AudioHub by RIVANOX — practical audio freedom, without the complexity.**</div>
