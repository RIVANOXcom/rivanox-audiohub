# AudioHub delivery roadmap

Workstream owner: PAPA project `PJ2611-0001:R001`. The source-of-truth for product requirements is Workbench; GitHub is the development, issue and build evidence provider.

## M0 — Source and image-build foundation

- [x] Public source repository and RIVANOX/Ko-fi project presence.
- [x] AGPL license text, separate commercial-license policy and upstream attribution plan.
- [x] Three-channel software configuration and unit tests.
- [x] Five-language browser UI prototype with translation tests.
- [x] Pinned `pi-gen` ARM64 development-image build.
- [x] First `.img.xz` produced in native ARM64 CI (run 41730586400).
- [x] Unverified image checksum, XZ integrity test and temporary GitHub Actions artifact upload proven ([run 41732307538](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41732307538)); this is **not** a public stable Release.
- [x] Five-language read-only health UI and image integration added in source, CI-tested (hardware not yet verified).
- [ ] Image contents audited against release security policy.

## M1 — Minimum useful Bluetooth-to-USB appliance

- [ ] Production-safe per-device ownership/first-boot claim without keyboard, screen or published secret.
- [ ] Bluetooth A2DP capture attached to actual USB speaker output.
- [ ] Auto-reconnect, reliable audio after restarts and USB replug.
- [ ] Phone pairing no harder than a commodity Bluetooth receiver.
- [ ] First physical Pi 4 acceptance evidence.

## M2 — Independent laptop and tablet input

- [ ] Verified LAN/WLAN laptop audio receiver; optional wired adapter pathway.
- [ ] Tablet independently attached; test dual Bluetooth capability or alternative.
- [ ] Three simultaneous channels with isolated gain, mute, EQ and clipping protection.
- [ ] Channel health status and watchdog.

## M3 — Full device management and stable release

- [ ] Authenticated local controller and five-language live device UI.
- [ ] Phone-based Wi-Fi onboarding and loss-of-network recovery.
- [ ] Internet radio/favorites without interfering with direct Bluetooth playback.
- [ ] 24h endurance, power-cycling and fault-injection tests.
- [ ] EU/DE/commercial and third-party dependency compliance audit.
- [ ] Verified owner-approved GitHub Release: `AudioHub-Pi4.img.xz` + `SHA256SUMS.txt`.

## Explicit release decision

There is **no stable SD-card image** until mandatory hardware, security and compliance gates pass. GitHub Actions preview artifacts are unverified, are retained only briefly and are not a replacement for an owner-approved GitHub Release.
