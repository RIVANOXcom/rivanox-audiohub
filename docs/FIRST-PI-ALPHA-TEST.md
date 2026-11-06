# Raspberry Pi 4 first-boot alpha test — isolated development only

**NOT A PRODUCT RELEASE.** This procedure is for an explicitly authorized
operator using a physically isolated development bench, a disposable
microSD and NO home/workplace network or real credentials. CI validates
source and image packaging, **not** Pi boot, Edifier sound, secure device
ownership or safe installation. Nothing in this guide grants release GO.

## Verified image snapshot — 6 November 2026

This deliberately pinned, independently verified ARM64 Pi4 preview is
**Draft PR75**, for an expressly authorized isolated operator experiment
only. Newer development previews exist; they are not automatically
substitutes for this specific reference image. Verify ALL commit, test,
artifact and checksum data again before any human decision to test.

| Proof | Exact value |
| --- | --- |
| Development PR | [PR75](https://github.com/RIVANOXcom/rivanox-audiohub/pull/75), Draft and unmerged |
| Source commit | `2b02bb4968467cd1033b47ddeaccaba092b96db0` |
| Source checks | [GitHub Actions #42305591855](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42305591855), **709/709 PASS** |
| Native ARM64 | [GitHub Actions #42305548510](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42305548510), **92/92** real installed-rootfs gates PASS |
| Test-only artifact | [#13546207449](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42305548510/artifacts/13546207449) — `AUDIOHUB-ALPHA-UNVERIFIED-DO-NOT-DISTRIBUTE` |
| ZIP SHA-256 (GitHub upload) | `b6bc5175fdee8f7c89aa0e041ec5521e7881ec2f1bd1d658156237434e1b9ad5` |
| Compressed Pi image SHA-256 (CI manifest) | `7b1adf94685ffe2cdbe1e86e83e11839da0fcd814d78bca0818e362f24167c95` |
| Artifact expiry (server reported) | 6 December 2026, 22:41 UTC |
| Classification | `UNVERIFIED_ALPHA_TEST_ONLY`; `public_release_ready=false` |

CI also reported `sha256sum -c` success, `xz --test` success, manifest provenance
verification and `bundle_integrity=passed`. These are **CI readbacks**,
not independent checks of any ZIP downloaded to the operator's computer.
The repository Releases tab does **not** contain this artifact.

### Retrieve and verify the exact test ZIP — operator only

1. Sign in to GitHub with access to this repo. Open the exact
   [ARM64 job #42305548510](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42305548510)
   and download **artifact #13546207449** under **Artifacts**. Do not
   take an old or similarly named ZIP from another build. If it expired
   or the account cannot access it, record **NOT AVAILABLE** and stop.
2. Compare the locally downloaded **ZIP** SHA-256 with
   `b6bc5175fdee8f7c89aa0e041ec5521e7881ec2f1bd1d658156237434e1b9ad5`.
   Windows PowerShell: `Get-FileHash -Algorithm SHA256 .\downloaded-artifact.zip`.
   Linux/macOS with the required tools: `sha256sum downloaded-artifact.zip`.
   Stop on any mismatch.
3. Extract the ZIP locally. Confirm it contains precisely one compressed
   `*.img.xz` image and the expected `SHA256SUMS.txt`,
   `PREVIEW-MANIFEST.json` and `ROOTFS-PACKAGES.json`.
   Check the manifest source commit matches the exact PR75 SHA above,
   and its native image-build run ID is #42305548510.
4. Check the image digest against the **manifest, SHA256SUMS.txt and**
   `7b1adf94685ffe2cdbe1e86e83e11839da0fcd814d78bca0818e362f24167c95`.
   Linux: run `sha256sum -c SHA256SUMS.txt` in the extracted directory.
   Windows: `Get-FileHash -Algorithm SHA256 .\image_2026-11-06-AudioHub-Pi4-UNVERIFIED.img.xz`.
   If available, run `xz --test image_2026-11-06-AudioHub-Pi4-UNVERIFIED.img.xz`.
   Any mismatch or corrupt XZ means **STOP**.
5. Only after these checks and a specific operator decision for an
   **isolated experiment**, use Raspberry Pi Imager **Use custom** with
   the `.img.xz` image and a **spare** card of at least 16 GB,
   preferably 32 GB. Flashing **erases the selected storage**.
   This document is not approval to flash, deploy or install anything.
   Do not substitute production cards or connect trusted systems.

### Isolated physical first-boot protocol

- Use the intended **Raspberry Pi 4**, suitable power, Edifier R600USB
  over USB, and a test-only Bluetooth sender at **low initial volume**.
  Disable Ethernet and do **not** provision WLAN, SSH, real passwords,
  administrative credentials, shared networks, firewalls or services.
- Power the Pi with the disposable image and observe boot indicators.
  The tentative initial Bluetooth discovery/pairing window is about
  ten minutes in the source; this has **not** been proven on a real Pi.
  Record whether a Bluetooth device is actually discovered and pairs.
- Record whether music is genuinely **audible** on the USB Edifier, not
  merely present in PipeWire graph metadata. If no audio is heard,
  do not infer a working path from process or status output.
- Observe reboot and reconnection separately. A FAT partition
  `AUDIOHUB-TEST-REPORT.json` may exist; it is unsigned and mutable
  and is **not physical acceptance**. Never disclose MACs, IPs, SSIDs,
  device IDs or private credentials in uploaded evidence.
- The optional Windows Scream LAN receiver remains **unauthenticated,
  disabled by default and IP-spoofable**. The three-source experiment
  in [THREE-SOURCE-LAB-ACCEPTANCE.md](THREE-SOURCE-LAB-ACCEPTANCE.md)
  requires a *separately authorized isolated test LAN*, manual
  `--unsafe-lan-test` and a permitted Windows sender. Do not expose
  it to a trusted/home/public network or enable it automatically.
- Two independent Bluetooth streams, three-source mix and EQ isolation,
  clipped waveform measurement, USB hotplug and true 24-hour endurance
  have **NOT** been verified, irrespective of CI status. Do not claim a
  physical result without a real operator test and evidence.

## Blank bench evidence form (not yet executed)

Every result starts as **NOT TESTED**. An operator must explicitly observe
and record pass/fail/unknown using the exact source image identifiers above.
Raw private device data should remain under operator control.

| Required measurement | Recorded result |
| --- | --- |
| Operator reference/date and physically isolated setup | NOT TESTED |
| Pi 4 revision and power supply type | NOT TESTED |
| Downloaded ZIP SHA-256 independently checked | NOT TESTED |
| Image SHA-256, manifest HEAD/run and XZ independently checked | NOT TESTED |
| Disposable SD verified before destructive flash | NOT TESTED |
| Pi boots without keyboard, Ethernet or WLAN | NOT TESTED |
| Edifier R600USB recognized and audio genuinely audible | NOT TESTED |
| Bluetooth discoverable and paired with test sender | NOT TESTED |
| USB unplug/replug and restart recovery | NOT TESTED |
| Second independent Bluetooth stream accepted concurrently | NOT TESTED |
| Manually opted-in Windows laptop input on isolated test LAN | NOT TESTED |
| Three simultaneous channels and independent mute/EQ verified | NOT TESTED |
| Peak/clipping measurements with three sources | NOT TESTED |
| 24-hour uninterrupted endurance and power-loss behavior | NOT TESTED |
| Authenticated phone owner-claim and Wi-Fi onboarding | NOT IMPLEMENTED |
| Source/third-party rights and CEO legal/release approval | NOT APPROVED |

If an actual test fails, document stage, exact source/run/image, and
redacted results. Lack of a report is missing evidence, not automatic
proof of success or failure. No simulated observations may be treated
as signed physical acceptance.

## Mandatory release blockers

- **689** packages were installed in the native CI image, **680**
  copyright files present, **nine unresolved** notice paths, and
  **83 source-rights** files pending human review.
- The effective source license remains **AGPL-3.0-only**.
  Proposed Model C is NOT effective; commercial redistribution
  and third-party obligations are NOT signed off.
- Physical Pi4/Edifier audible simultaneous audio, two-A2DP capability,
  authenticated phone ownership/Wi-Fi onboarding, 24-hour endurance,
  Windows sender security and operator/CEO release authorization remain
  unverified.

Neither this test-only image nor this guide is installable release
evidence. No public release, no automated deployment, no merge or GO.
Tracking: PAPA `PJ2611-0001:R001`, AH-001 #3267, AH-002 #3268,
AH-006 #3272, AH-009 #3275.
