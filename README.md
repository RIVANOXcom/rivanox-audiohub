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
> See the [source and OS third-party review](./docs/licensing/THIRD-PARTY-REVIEW-2026-11-05.md) and
> [separate PRIVATE Model C development procedure](./docs/licensing/MODEL-C-PRIVATE-DEVELOPMENT.md).
> The current published source remains **AGPL-3.0-only**, including
> existing commercial-use rights under that license. No prior AGPL grant
> is withdrawn; the draft does not yet grant or restrict additional rights.

**Maintainer continuity:** [PAPA AudioHub canonical resume, exact PR/CI evidence and license gates](./docs/PAPA_CANONICAL_RESUME_20261105.md). This is an engineering handoff, not an authorized release.

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

### Driverless isolated Pi4 speaker soundcheck (alpha)

A built-in, opt-in **5-second quiet 440 Hz** test tone now allows an
operator to test the encrypted Windows-to-Pi4 audio route before
installing/configuring any Windows Scream driver. In the portable
Windows GUI choose **Pi speaker test**; alternatively use
`py -3 START-WINDOWS-BRIDGE.py --test-tone`. The test has
a hard five-second duration, 200 ms fade, explicit `ISOLATED` confirmation,
a Stop control, and opens **no Windows Scream UDP listener**. The
private TLS key/cert, isolated lab Pi4 with working PipeWire/USB,
human supervision, low speaker volume, and operator approval remain
mandatory. Passing CI or seeing audio frame counts does not prove
audible Edifier sound or Windows Scream driver interoperability.
See [the first hardware test instructions](./docs/WINDOWS-PORTABLE-ALPHA.md).

The optional **Left / Right / Left then Right** selector now lets the
operator check actual stereo-channel mapping, not just whether any tone
arrives. The five-second L→R sequence includes a silent separation;
it remains a manually authorized private TLS test. The operator must
listen to both speakers and record the result. See
[Windows stereo channel test steps](./docs/WINDOWS-PORTABLE-ALPHA.md).

After a manual test the Windows GUI can now capture **separate physical
LEFT/RIGHT observations** and explicitly save a small private JSON
report. The owner records whether each speaker was heard correctly,
swapped, silent or distorted. Nothing is uploaded, no credentials or
device identifiers are exported, and the report **never** constitutes
automatic hardware verification or release approval. This removes the
need to copy sensitive terminal logs to report a physical fault.
See [operator observation instructions](./docs/WINDOWS-PORTABLE-ALPHA.md).

Before testing, the Windows GUI can now **offline-compare the Pi's
public X.509 PEM/DER certificate to a separately confirmed DER SHA256**
from the physically trusted Pi console. The certificate picker never
replaces the independently entered fingerprint, and a mismatch
blocks the connection before networking. The portable terminal
equivalents are \`--certificate-file\` and
\`--show-cert-fingerprint\`. This shortens error-prone onboarding but
does not create trusted owner identity, certificates, keys or
automatic provisioning. Read the
[offline certificate cross-check walkthrough](./docs/WINDOWS-PORTABLE-ALPHA.md).

### Authenticated Windows audio: isolated engineering preview only

A separate optional **TLS 1.3, pinned-cert, 32-byte shared-key challenge-response**
Windows bridge and Raspberry Pi receiver now provide a manual alternative to
the spoofable raw Scream UDP lab input. The Windows bridge listens for the
already installed Scream driver **only on 127.0.0.1**, then sends validated
stereo PCM inside TLS to the Pi; the Pi requires an explicit owner-created
key and certificate and never starts playback without authentication. It is
one-shot, time-limited and **OFF by default**, with no remote UI or service.
No Scream driver is shipped, and its Windows loopback unicast operation and
actual audio have not been hardware tested. There are no bundled credentials.
An independent, reproducible **Windows portable ALPHA ZIP** now provides a
single guided Python launcher with an optional local labeled `--gui`
window (IP, cert fingerprint, private key picker, offline Check, explicit
Start and Stop), an offline `--self-check`, a
no-network `--check-only` configuration review and an explicit `ISOLATED`
confirmation before any TCP/UDP socket is opened. Its temporary GitHub
Source Checks artifact includes source-code provenance and an exact SHA256;
there is no installer, third-party driver, secret or automatic service.
Read the [Windows first-start guide](./docs/WINDOWS-PORTABLE-ALPHA.md) and
[the isolated authenticated Windows bench runbook](./docs/SECURE-WINDOWS-LAN-LAB.md).
**No normal/home-network deployment or production release is approved.**

**Hardware note:** Two simultaneous A2DP senders have not been verified
on Pi 4. The Windows Scream receiver is plaintext/unauthenticated and is
never started automatically. For isolated manual bench work its UDP
listener now auto-closes after 10 minutes by default (explicit 1–30 minute
limit with `--session-minutes`); activity cannot extend the session.
This does not authenticate a sender. See the
[manual LAN session runbook](./docs/HARDWARE-OBSERVATION-RUNBOOK.md#time-limited-manual-windows-lan-bench-session-alpha-only). Renaming a channel does not authorize a
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

### Experimental Windows/Pi4 offline PSK-copy comparison

The isolated Windows operator alpha can now display a private local
32-hex HMAC-based check code for its existing 32-byte shared-key file
(\`--show-key-code ABSOLUTE_PATH\`). Compare only against the independently
computed code from the physically trusted Pi console; optionally enter
the Pi code in the GUI or use \`--expected-key-code CODE\` to refuse a
mismatch before network access. No secret bytes are displayed or sent,
no keys are created, transferred or rotated, and Windows NTFS ACLs
remain operator-controlled. This is **not** owner authentication,
hardware acceptance, or an official release. See
[Windows operator instructions](docs/WINDOWS-PORTABLE-ALPHA.md).

### Experimental offline staged PSK rotation preview

For the isolated Windows-to-Pi4 TLS test lab, the operator may now
preflight **both** existing and separately staged private 32-byte PSK
copies against independently trusted Pi comparison codes before
manual key rotation. Use the GUI **4 · Staged PSK preview (offline)**
or \`py -3 START-WINDOWS-BRIDGE.py --rotation-preflight\` with hidden
interactive code prompts. The preview rejects reused secrets, wrong
codes and aliased files; it never creates, installs, rotates or removes
credentials and it never connects to the Pi. A separately authorized
operator performs coordinated cutover, low-volume hardware smoke test
and rollback. The detailed guide is in
[Windows isolated lab setup](docs/WINDOWS-PORTABLE-ALPHA.md).

### Local-first Bluetooth pairing readiness (Pi4 ALPHA)

The Pi4 now offers an **operator-facing, read-only** first-use Bluetooth
status check. Run \`PYTHONPATH=/opt/audiohub/src python3 -m
audiohub.pairing_readiness\` at an already-authorized **local Pi console**
(no browser API, new pairing rights, Wi-Fi, controller writes, logs or
network connection). The status explains whether the first-boot ten-minute
window appears visible, closed, expired, full, untrusted, or unexpectedly
open, with clear next steps. No MAC address, device name, personal
information or key is printed; \`--json\` returns a bounded anonymous
snapshot. The existing first-boot FAT \`AUDIOHUB-TEST-REPORT.json\` now
includes \`bluetooth_pairing_state\` and \`bluetooth_paired_devices\` so
the **headless operator can examine it after a safe shutdown and SD-card
removal**. It never asserts ownership, sound or two-source Bluetooth
compatibility. The existing NoInputNoOutput test agent is not secure
phone-owner claiming; production ownership/phone Wi-Fi still requires a
separate, reviewed implementation. Follow the
[Pi4 pairing readiness guide](./docs/PI4-BLUETOOTH-FIRST-USE.md).

### View the headless Pi4 SD first-boot report without Python or Wi-Fi

AudioHub now includes a self-contained, five-language browser viewer
for the anonymous \`AUDIOHUB-TEST-REPORT.json\` produced by Pi4
first-boot diagnostics. Open \`AUDIOHUB-BOOT-REPORT-VIEWER.html\` from
the **portable Windows test ZIP**, or
[the source HTML viewer](web/boot-report-viewer.html), directly on
Windows/Mac/Linux after a controlled Pi shutdown and SD removal. A
small link in the existing AudioHub read-only web prototype opens
the same viewer. It never uploads the chosen file, changes Bluetooth,
or interprets SD data as ownership/hardware release approval.
See [headless operator instructions](docs/PI4-BLUETOOTH-FIRST-USE.md).

### Play local WAV music through AudioHub without pairing or a cloud service

An operator can now play **their own** bounded 16-bit PCM WAV files
as an actual, independently controlled source in the existing
\`audiohub.music\` mixer input. Preview up to eight files with
\`python3 -m audiohub.local_music /absolute/path/file.wav\`, then
explicitly select \`--play\` at the trusted Pi4 terminal; press
**Ctrl+C** to stop. Audio is streamed into a **fixed music virtual
sink**, never a default speaker fallback, with low initial stream
volume. No new daemon, credentials, account, file upload, route
changes or Bluetooth permissions are required. Works offline;
this is NOT Internet radio or phone-owner onboarding.
See [local WAV operator instructions](docs/LOCAL-MUSIC-PLAYBACK.md).

### Browse a local album without typing each WAV filename

At the trusted Pi4 console, use `python3 -m audiohub.local_music
--library /home/audiohub/PrivateMusic` to display numbered,
privacy-preserving WAV durations without playing anything. Add
`--tracks 2,1` for a safe queue preview and only then add `--play`
for explicit user-controlled, bounded playback in that order.
`--show-titles` optionally reveals sanitized filenames **on the local
terminal only**. Music remains on the Pi, no playlist is stored and
no unauthenticated browser/audio endpoint is opened. Full guide:
[Local music source and folder picker](docs/LOCAL-MUSIC-PLAYBACK.md).

### Control an ongoing local WAV queue without exposing a device API

From an already-authorized Pi4 terminal, append `--play --interactive`
to an explicitly selected `audiohub.local_music` queue. Enter `s`
for anonymous session status, `n` to skip one track, `q` to stop,
`h` for help or Ctrl+C to interrupt. A real TTY on both input/output
is required; no background service, HTTP controller or saved playlist
is created. Real sound is still unverified until an isolated Pi4
hardware listening test. See
[local music playback guide](docs/LOCAL-MUSIC-PLAYBACK.md).

### Navigate a local audio queue without a network remote

On an explicitly started Pi4 `--play --interactive` session, the
operator can also press `l` + Enter for an anonymous ordered queue
and planned WAV durations, `p` to play the preceding selected track,
`r` to replay the current track, or a valid number `1`–`8` to jump
directly within the selected queue. All commands are local to the
already-authorized physical terminal, keep the original session
limit, display no private filenames and leave Bluetooth, network,
PipeWire routing and EQ unchanged. See
[local WAV controls](docs/LOCAL-MUSIC-PLAYBACK.md).

### Pause and resume your local Pi4 WAV session

From a manually started `--play --interactive` terminal session,
`u` + Enter pauses the current **owned local music player**,
and another `u` + Enter resumes it. The `s` status command shows
whether it is paused. Existing next/previous/replay/jump, quit,
Ctrl+C and the total session deadline continue to work while paused.
The player is resumed before termination to avoid leaving a stopped
process behind. PipeWire services, Bluetooth sources, routing and
security permissions are unchanged. Buffered speaker audio can
continue briefly; **real Pi4/Edifier audibility is still unverified**.
See [local music operator instructions](docs/LOCAL-MUSIC-PLAYBACK.md).

### Guided offline local music playback (one Pi4 command)

At a trusted Pi4 operator terminal, start
`python3 -m audiohub.local_music --guided --library /home/audiohub/PrivateMusic`
with the installed source on `PYTHONPATH` as unprivileged audiohub
user. Select up to eight numbered WAVs, enter `ALL` for a small album,
or `SHUFFLE` to pick up to eight random tracks within the session time.
Press Enter to
cancel, enter `CHANGE` at the review step to reselect (up to twice),
or type **exactly `PLAY`** at the final prompt to start
interactive playback. No audio starts merely from scanning or choosing
tracks. Titles remain hidden unless `--show-titles` is explicit.
Then use `u` pause/resume, `q` stop and the existing local controls;
no remote service, stored playlist, new permission or device route is
introduced. Details and safe rollback:
[local music guide](docs/LOCAL-MUSIC-PLAYBACK.md).
