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

### Planned audio channels

| Input | Intended connection | Independent controls |
| --- | --- | --- |
| Phone | Bluetooth A2DP | Volume, mute, EQ |
| Laptop | Local-network audio, optional wired adapter | Volume, mute, EQ |
| Tablet | Bluetooth where hardware allows, or a supported network source | Volume, mute, EQ |

**Hardware note:** Simultaneous Bluetooth A2DP input from two different devices is not yet validated. This must not be represented as a guaranteed feature. Tested alternatives may require an extra Bluetooth adapter or a dedicated network-streaming method.

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

For **experimental hardware bench tests only**, an older, short-lived [4 November 2026 Actions image artifact](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41792407565/artifacts/13303394505) exists (expires 11 November 2026). It is **not** in Releases, is based on older unverified source code, requires GitHub sign-in, and must not be connected to a trusted LAN. See [first Pi 4 experimental test and download help](./docs/FIRST-PI-ALPHA-TEST.md). New preview-image build summaries will link their temporary artifacts and checksum/provenance manifest; they are still not hardware-certified releases.

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
