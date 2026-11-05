<div align="center">

# 🎚️ RIVANOX AudioHub

### One speaker system. Multiple audio sources. Your mix.

**A headless, multilingual, open-source audio mixer for Raspberry Pi 4.**

**Powered by [RIVANOX](https://rivanox.com)**

**❤️ [Support AudioHub development on Ko-fi](https://ko-fi.com/RIVANOX)** · **[Commercial licensing information](./docs/COMMERCIAL-LICENSING.md)**

[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)](./docs/STATUS.md)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](./LICENSE)
[![Website](https://img.shields.io/badge/RIVANOX-Website-black)](https://rivanox.com)
[![Support on Ko-fi](https://img.shields.io/badge/Support-Ko--fi-ff5e5b)](https://ko-fi.com/RIVANOX)

</div>

> **Licensing transition — planned Model C, NOT EFFECTIVE.**
> RIVANOX has selected a future **source-available** model: personal,
> non-commercial use free of charge; new commercial/organizational use
> subject to a separate written license. The legal text is under review
> in [LICENSE-C-DRAFT.md](./LICENSE-C-DRAFT.md), with the
> [rights audit](./docs/licensing/RIGHTS-AUDIT-2026-11-05.md).
> The current published source remains **AGPL-3.0-only**, including
> existing commercial-use rights under that license. No prior AGPL grant
> is withdrawn; the draft does not yet grant or restrict additional rights.

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

The **latest CI-validated experimental Pi4 image** is from
[Draft PR #30](https://github.com/RIVANOXcom/rivanox-audiohub/pull/30),
commit `8ab26da637604723e4c29f114cc93a478e0d02f0`:

**[Download temporary Pi4 Alpha Test ZIP (Actions artifact #13443339137)](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086909475/artifacts/13443339137)**

- [Source CI 42086920486](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086920486): **226 Python tests passed**.
- [Native ARM64 image CI 42086909475](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086909475): **SUCCESS**, **55/55 real rootfs checks**, image SHA256 / XZ integrity and preview provenance verified.
- ZIP size 606,222,225 bytes. **Expires 5 December 2026**.
  GitHub sign-in may be required for Actions artifacts, even though the
  source repository is public. Extract the ZIP for the `.img.xz`,
  `SHA256SUMS.txt` and `PREVIEW-MANIFEST.json`.
- **Not a GitHub Release and not hardware certified.** Flash only to a
  spare microSD and use an isolated test bench. No secure phone-first
  ownership or Wi-Fi provisioning yet. The manually gated Windows UDP
  input is **untrusted**, disabled by default. Do not connect it to a
  trusted LAN.
- [How to test the Pi safely](./docs/FIRST-PI-ALPHA-TEST.md) ·
  [Offline integrity preflight](./docs/RELEASE-DISTRIBUTION.md) ·
  [Observed PipeWire links and diagnostics](./docs/PIPEWIRE-LINK-OBSERVABILITY.md).

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

Original RIVANOX code is offered under **GNU AGPL-3.0-only**, subject to ownership and third-party rights. **Commercial use under AGPL is allowed without a fee or revenue share**; see the full terms for redistribution and network-access obligations. The [license](./LICENSE) governs the open-source option. Commercial alternative licensing of eligible RIVANOX-owned code may be negotiated separately; a commercial license does not automatically cover third-party dependencies or community contributions.

The AGPL does **not** require all users, including commercial users, to pay. It grants the freedoms described in its terms. Nothing in the repository represents a legal opinion or a blanket commercial sublicense for dependencies.

The RIVANOX name and branding are not automatically licensed for unrelated products. See the [trademark policy](./TRADEMARKS.md).

## Help keep AudioHub free, safe and maintained

Development includes real Raspberry Pi and speaker compatibility testing,
security updates, accessibility, documentation and dependable releases.
Community contributions can help fund that work.

**❤️ [Support AudioHub on Ko-fi — voluntary donation](https://ko-fi.com/RIVANOX)**

Donations are entirely optional: **they never unlock AGPL rights,
downloads, core functionality or support entitlements**. No tracking or
payment processing is built into AudioHub.

Businesses can also explore **[commercial licensing](./docs/COMMERCIAL-LICENSING.md)**
for an optional, separately negotiated license to eligible RIVANOX-owned
source, or professional integration and support services. Commercial use
**under the existing AGPL remains permitted without paying royalties** if
the license conditions are followed. RIVANOX cannot promise proprietary
rights in upstream Raspberry Pi OS or third-party code.

Official public GitHub Releases are planned only after hardware,
security, legal and owner-approval gates; see the
[reviewed release workflow](./docs/RELEASE-DISTRIBUTION.md).
Learn more at **[RIVANOX.com](https://rivanox.com)**.

## Contribute or report an issue

Read [CONTRIBUTING.md](./CONTRIBUTING.md), report functional bugs through [GitHub Issues](https://github.com/RIVANOXcom/rivanox-audiohub/issues), and submit security reports through the private process in [SECURITY.md](./SECURITY.md).

---

<div align="center">**AudioHub by RIVANOX — practical audio freedom, without the complexity.**</div>
