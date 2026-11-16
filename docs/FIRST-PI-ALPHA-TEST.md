# Raspberry Pi 4 first-boot alpha test — isolated operator bench only

**NOT A PRODUCT RELEASE.** These instructions describe a manually approved
operator-only test of an explicitly identified Pi 4 development image. A
successful source CI, image build or package audit does NOT demonstrate that
a real Pi booted, the Edifier speaker produced sound, a secure operator login
exists, or that redistribution/release has been approved.

## Choose one exact native build (avoid historical, expired previews)

This is the **version-independent operator procedure**. Do not rely on
previously pinned PR numbers, filenames, ZIP hashes or run IDs in an old
copy of a test guide. For this development series, consult the current
[Draft PR304 evidence](https://github.com/RIVANOXcom/rivanox-audiohub/pull/304)
for its immutable source commit, native ARM64 run and actual uploaded
test ZIP. Subsequent isolated source revisions need their **own** completed
native build and artifact; an older ZIP is never proof of a newer commit.

1. Open the chosen GitHub Actions **Build unverified Pi 4 image** run in
   [repository Actions](https://github.com/RIVANOXcom/rivanox-audiohub/actions).
   Require `completed / success` on the **exact intended source SHA**.
   Record the source commit, run ID, Pi image filename and artifact ID.
   Only select the `AUDIOHUB-ALPHA-UNVERIFIED-DO-NOT-DISTRIBUTE` artifact
   belonging to this run. This is an expiring authenticated test attachment,
   **not a GitHub Release**. Missing, expired or inaccessible: **STOP**.
2. From GitHub's artifact details/API for that exact artifact, independently
   record its reported **outer ZIP SHA256** and size. Save the ZIP on a
   trusted local PC; confirm the downloaded ZIP SHA256 matches the provider
   digest before extraction. On Windows use PowerShell:
   `Get-FileHash -Algorithm SHA256 .\downloaded-artifact.zip`.
   On Linux use `sha256sum downloaded-artifact.zip`; on macOS use
   `shasum -a 256 downloaded-artifact.zip`. A missing reported digest
   or mismatch means **STOP**. The GitHub-hosted digest itself is
   **not** evidence that this procedure was run by a human operator.
3. With Python 3, the exact matching repository source and a verified
   downloaded ZIP, an offline audit can be run without flashing hardware:
   `python3 scripts/release_bundle_audit.py --zip downloaded-artifact.zip
   --expected-source-sha SOURCE_COMMIT_SHA
   --expected-zip-sha256 PROVIDER_ZIP_SHA256`
   (enter as one shell command with the actual recorded values).
   The audit always reports `public_release_ready=false`; this is expected.
   Where Python/tools are unavailable, do the following manual checks
   rather than claiming the audit ran.
4. Extract the ZIP **only after outer digest verification**. The current
   five-file preview bundle must contain exactly one `*.img.xz`,
   `SHA256SUMS.txt`, `PREVIEW-MANIFEST.json`, `ROOTFS-PACKAGES.json`,
   and `AUDIOHUB-OFFLINE-REPORT-VIEWER.html`. Check
   `PREVIEW-MANIFEST.json` binds the intended `source_sha`, native run ID,
   image SHA256 and exact offline viewer size/SHA256. Compare the image
   against `SHA256SUMS.txt` (`sha256sum -c SHA256SUMS.txt` when available)
   and `xz --test <image-filename>.img.xz` when available. Confirm the
   viewer SHA256 from the **same ZIP**. Refuse inconsistent filenames,
   missing files, image digest mismatch, corrupt XZ or stale manifest.
   Older four-file previews have no bundled viewer and are not equivalent
   to the new operator test bundle.

## Three-step isolated bench test — operator authorization required

**Before any flashing, agree on a safe shutdown method.** The preview image
does not expose an approved/default local operator password and has SSH
disabled. The secure first-login/ownership flow is owned separately by
AH-005 / PAPA-5B2E6939 (Workbench #3427). Do not guess credentials, enable
autologin or SSH, enable a trusted LAN, bypass pairing authorization, or
assume that unplugging a running Pi safely unmounts the SD filesystem.
If a separately approved safe way to power down the isolated test device
does not exist, **do not begin the physical flash/boot test**; coordinate
the bounded operator access/shutdown procedure with that mission.

1. **Prepare without losing data.** Confirm explicit operator permission
   for the exact source SHA/image hash, a disposable microSD (at least
   16 GB; 32 GB recommended), intended Raspberry Pi 4, suitable power
   and Edifier R600USB over USB. Preserve the original SD untouched and
   independently preserve all owned WAV/EQ as well as unsupported
   MP3/FLAC/other files; do not interpret a partial WAV backup as a full
   SD migration. Manually flash **only the spare card** using Raspberry Pi
   Imager 'Use custom'. Flashing erases the selected storage.
2. **Observe the actual device on an isolated bench.** With no Ethernet,
   home Wi-Fi credentials, SSH, shared passwords or trusted network,
   boot the Pi/Edifier at low initial volume. Note visible boot indications
   and whether the test Bluetooth sender pairs or real sound is heard;
   silence is not evidence of success. The one-time FAT boot diagnostic
   samples for about ten minutes; it does not certify sound, secure
   ownership, complete routing or continuously stable USB. Audio testing
   requiring a local privileged console must await AH-005 authorized
   access. The optional unauthenticated Windows LAN sender requires a
   **separate** isolated-LAN authorization and is disabled by default.
3. **Safely power down, then inspect locally.** Use only the approved
   shutdown procedure. After the Pi is completely off, read
   `AUDIOHUB-TEST-REPORT.json` from the *spare SD boot partition* on a
   trusted PC. Open the same ZIP's offline
   `AUDIOHUB-OFFLINE-REPORT-VIEWER.html` file and manually select the
   report in the local picker. Compare last reported direct USB route
   with **sampled USB-presence history** (late detection, disappearance,
   intermittent observation). Instead of manually transcribing 40
   hexadecimal digits, the same bundled offline HTML viewer can now
   open the small `PREVIEW-MANIFEST.json` from the SAME independently
   SHA256-verified ZIP and populate the expected source SHA locally.
   It validates the expected test-only schema and never sends the
   manifest, but it does NOT independently verify package integrity or
   authenticate the SD report. Manual SHA entry remains an alternative. A USB route reported in JSON is NOT
   a human stereo or actual-audibility test. The report is unsigned and
   mutable; never upload its raw contents or share identifiers.
   The **unmodified original SD** is the rollback option after shutdown.

Capture the selected image SHA, ZIP SHA, source SHA, native run ID,
actual Pi/Edifier observations, powerdown method, and result as
PASS/FAIL/NOT TESTED, redacting private details. Do not claim S3 on CI
or a synthetic browser report. Reboot/reconnection, two simultaneous
Bluetooth sources, a third LAN source, independent EQ, USB hotplug and
24-hour endurance are *separate physical tests* requiring explicit
permission. See [three-source test protocol](THREE-SOURCE-LAB-ACCEPTANCE.md).
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

Neither this operator-only test image nor this procedure proves an approved
installable **production** release. No public release, automated deployment,
merge, or GO without complete hardware, ownership, licensing and operator
signoff.
Tracking: PAPA `PJ2611-0001:R001`, AH-001 #3267, AH-002 #3268,
AH-006 #3272, AH-009 #3275.

## Optional earlier-vs-later boot comparison (not a request to restart)

After **authorized safe shutdown**, an operator may privately copy the
FAT AUDIOHUB-TEST-REPORT.json to their trusted PC. The Pi overwrites the
report on its next boot, so save any earlier copy *before* a separately
authorized later run. Do not reboot merely to generate a comparison.

The same offline HTML viewer accepts an earlier saved report in a second
file picker alongside the current report and exact verified-ZIP manifest.
It strictly sanitizes both reports, shows only anonymous USB direct-link
and sampled USB-presence before/after findings, and refuses comparisons
when the public source SHA differs, is missing or conflicts with the
expected package SHA. No network, persistence, credentials or Pi writes.
Both reports are unsigned/mutable observations, never proof of continuous
or audible Edifier sound or automatic S3 acceptance.
