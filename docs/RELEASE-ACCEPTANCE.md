# Hardware and release acceptance plan

**Target:** Raspberry Pi 4, Edifier R600USB, flash-only SD setup, USB speaker, smartphone, laptop, tablet.  
**Current status:** NOT ACCEPTED. This is a test plan, not a test report.

| Gate | Required verification | Evidence |
| --- | --- | --- |
| G1 — Provenance | Build source commit and pinned package versions; SHA256 and XZ integrity; no unlicensed copied code or embedded static credential. | CI run, manifest, SHA256SUMS.txt, license audit. |
| G2 — First boot | Fresh microSD, only speaker USB and Pi power; no monitor/keyboard/SSH required. | Video or technician protocol, boot logs, image hash. |
| G3 — Bluetooth phone | Standard discoverable device name, simple initial A2DP pairing, Spotify/YouTube audio, safe reconnection after power cycle. | Pairing matrix with Android versions and device models. |
| G4 — USB output | R600USB enumerated, selected output actually carries sound, no diversion to HDMI, unplug/replug recovers. | ALSA/PipeWire logs and audible test. |
| G5 — Audio separation | Phone, laptop and tablet play independently and simultaneously; separate mute, volume and EQ; mix clipping controlled. | 3-input test recordings, channel matrix, signal measurements. |
| G6 — Dual Bluetooth feasibility | Verify two independent A2DP senders only if supported; otherwise document tested alternatives and equipment. | Repeated reproducible tests; no ungrounded claims. |
| G7 — Wi-Fi/owner security | Phone-only initial setup, verified ownership, authenticated controls, safe recovery when LAN absent. No universal default secret. | Threat model and authorization tests. |
| G8 — Offline and reliability | Bluetooth music without Internet; network recovery; background playback when UI closed; 24h test; unexpected power loss. | Logs and failure injection checklist. |
| G9 — Accessibility/localization | App all en/de/es/fr/it; error strings, controls, persistence, screen reader labels and browser fallback. | Localization parity tests and UI acceptance. |
| G10 — Distribution | Latest verified release downloads as img.xz; checksum verified; licensing notices, support and limitations accurate. | Release URL, owner approval, independent install check. |

A **stable** release requires all mandatory gates and explicit release authorization. Source CI and a compressed image file alone do not satisfy G2–G10.

## Notes for the first pilot

Use an isolated test SD card and keep a recovery copy. The current experimental images are unverified and may not finish first-boot configuration. Do not instruct nontechnical users to flash an alpha image as if production-ready.

Only test with equipment the user already has until there is a demonstrated need for a wired line input or additional Bluetooth hardware.
