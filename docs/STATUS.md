# Development status

**Status:** Alpha / pre-release. No verified ready-to-flash Pi 4 image has been published. Native ARM64 test-only SD images have been built and uploaded to GitHub Actions (latest prior-to-renaming run 42057278883; 159 tests, 48 rootfs checks). **No real Pi4/Edifier playback, ownership security or product-ready Release has been verified.**

## Goals

- USB speaker playback using Edifier R600USB where recognized as a USB-audio device
- Phone Bluetooth A2DP input with simple initial pairing and reconnection
- Laptop network audio input
- Third tablet audio input, including a two-Bluetooth-source test and supported alternatives
- Independent gain, mute and three-band EQ per input, plus master volume
- Local-first web UI localized in en/de/es/fr/it
- Self-configuring headless first boot and recoverable network provisioning
- GitHub-hosted reproducible image builds and verified release assets

## Status definitions

**Designed** means the architecture has been drafted. **Implemented** means code exists. **CI validated** means automated code-level tests have passed. **Hardware verified** means logs and a repeatable Pi 4 procedure demonstrate it works. **Released** means an image and checksum are available from GitHub Releases.

None of the planned audio feature paths has been marked hardware verified in this repository.

## Release blockers

1. First-boot authentication must not rely on a shared published secret.
2. A bootable image must be built from pinned inputs and pass offline/first-boot checks.
3. Bluetooth A2DP with a real phone must be tested.
4. Simultaneous audio paths, per-source EQ, USB speaker output and recovery must be tested.
5. Legal notices, attribution and applicable EU requirements must be assessed for the distributed artifact.

No release should claim Bluetooth parallelism, zero-setup provisioning or hardware compatibility without evidence.
