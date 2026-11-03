# RIVANOX AudioHub — Project baseline v1.0

**Canonical Workbench project key:** `PJ2611-0001:R001`  
**Project name:** RIVANOX AudioHub  
**Engineering source:** https://github.com/RIVANOXcom/rivanox-audiohub  
**Public development status:** Alpha, pre-release (not hardware verified)  
**Baseline recorded:** 2026-11-03  
**Document language:** English only

## Product vision

Deliver a compact, energy-efficient, reliable audio appliance that connects ordinary USB audio speakers to multiple independent audio sources. A person with no Linux experience must be able to flash one prebuilt SD-card image, insert it into a Raspberry Pi 4, connect USB speakers and power, and use Bluetooth music without a monitor, keyboard, SSH, terminal or mandatory account registration.

The initial target is the **Raspberry Pi 4** and **Edifier R600USB**. The device must behave for the phone like a simple consumer Bluetooth receiver. A local, mobile-friendly control interface adds channel mixing, EQ, connection status, radio and device management without being required for routine playback.

## Explicit user requirements and priorities

1. **P0 — Flash and play.** An official, preconfigured `AudioHub-Pi4.img.xz` downloadable from GitHub Releases; no required end-user OS installation or Linux commands.
2. **P0 — Phone music.** Bluetooth A2DP audio from Android and common music apps. One-time pairing must be simple; trusted devices should reconnect when the source device supports it.
3. **P0 — Independent inputs.** Three simultaneous channels: phone, laptop, tablet; each has separate volume, mute and EQ. The laptop may use LAN/WLAN or a supported wired adapter. Dual concurrent Bluetooth input is a *test objective*, not an accepted fact.
4. **P0 — USB speaker.** Digital USB output to Edifier R600USB and safe behavior when the selected audio hardware is disconnected.
5. **P0 — Secure appliance.** No public default password or insecure always-on administration. The first owner can commission and recover the device with a phone.
6. **P0 — Verifiable quality.** Hardware-first acceptance before publishing a stable image. CI is necessary, but is not a substitute for boot and audio tests.
7. **P1 — Mobile UI.** Full application localization into en, de, es, fr and it; browser auto-detection with a user override. Complete translated status and controls.
8. **P1 — Reliability.** Automatic service startup/recovery, low idle power, avoidance of excessive microSD writes, connection and error status.
9. **P1 — Open source and sustainability.** Eligible original code under AGPL-3.0-only; separately negotiated commercial alternative licensing where RIVANOX owns the necessary rights; voluntary Ko-fi funding and RIVANOX.com awareness. Third-party rights and EU/DE obligations are not waived.

## Three-channel signal design

```text
Bluetooth phone (A2DP)  ---> channel 1 source ---> EQ 1 ---> gain 1 ---+
Windows laptop (network) ---> channel 2 source ---> EQ 2 ---> gain 2 ---+--> safe master mix
Tablet (BT/network)     ---> channel 3 source ---> EQ 3 ---> gain 3 ---+    --> USB audio --> R600USB
```

The mixer must not pause the phone when the laptop becomes active. The user must be able to set each channel independently. A limiter or defined headroom prevents clipping as multiple channels sum. If a second Bluetooth input cannot be made reliable on the Pi 4, document tested hardware or network alternatives rather than overstating support.

## System boundaries

- **Audio runtime:** Raspberry Pi OS Lite ARM64, PipeWire/WirePlumber and BlueZ, with an unprivileged routing supervisor.
- **Web UI:** local-first browser/PWA control plane; audio playback must remain active when closed.
- **Network:** optional for Bluetooth music; required for network laptop audio, radio and some management features.
- **Storage:** bootable SD-card image; volatile status in tmpfs; persistent settings only when changed.
- **Distribution:** public GitHub repository and verified GitHub Releases.
- **Governance:** PAPA Workbench is the persistent project authority. GitHub records source, issues, workflow runs and release artifacts; no bidirectional sync is assumed until ticket 121 is implemented and verified.

## Acceptance and non-goals

**Acceptance:** the complete procedure and hardware proof in [RELEASE-ACCEPTANCE.md](RELEASE-ACCEPTANCE.md) must pass before a stable release is labeled ready to flash.

**Not promised yet:** native Bluetooth multi-receiver interoperability, DRM-protected mobile system audio capture, Spotify account control without official compatibility, cloud remote management, zero latency, universal USB speaker support, or fully completed production legal clearance.

**Current truth:** a native ARM64 GitHub Actions build produced a compressed `.img.xz` file on 2026-11-03, but the post-build checksum step failed because of root-owned output permissions. A dedicated preview workflow fixes artifact staging and is pending verification. No validated SD-card image has been released.
