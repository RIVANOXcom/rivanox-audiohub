# First Raspberry Pi 4 alpha SD-image test — experimental ONLY

**Not a product release.** The first Pi OS image was created by a real
GitHub Actions ARM64 image-build job, but no real Pi4/Edifier audio boot test
or secure owner onboarding has been accepted. This document is for an
authorized, local **isolated development bench** only. Do not deploy this
image on a home or office network, expose network ports or enter real
Wi-Fi/owner credentials.

## Where the image actually is (not GitHub Releases)

The initial image from **4 November 2026** is an expiring *Actions artifact*:

1. Sign in to GitHub with a user who can access this repository.
2. Open [Actions run 41792407565](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41792407565).
3. On the run's **Summary** page, locate **Artifacts** (typically near
   the bottom) and select
   `AUDIOHUB-ALPHA-UNVERIFIED-DO-NOT-DISTRIBUTE`.
4. [Direct artifact link](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41792407565/artifacts/13303394505).
5. GitHub supplies a ZIP archive (~604 MB). Extract the ZIP to see
   `image_2026-11-04-AudioHub-Pi4-UNVERIFIED.img.xz` and
   `SHA256SUMS.txt`.

**Expiry:** GitHub reported this old artifact as present, not expired,
and scheduled to expire on **11 November 2026**. After expiry, a new
preview build is needed. Neither the repo **Releases** tab nor the
green **Source checks** in the recent Actions list contains this image.

The initial experimental build provenance is source commit
`93e637276d5fc772a4b06f7848aacdeddfddaf17`,
run `41792407565`; its CI rootfs preflight passed 32 build-only checks.
A checksum and an XZ integrity test succeeded **in that build**,
but a Pi 4 has not been booted as part of CI.

Future experimental builds using the proposed download improvements
will show an artifact link in the **Actions run job summary**, plus
`SHA256SUMS.txt` and `PREVIEW-MANIFEST.json`. Proposed retention:
30 days, if repo policy allows. They do **not** appear under Releases.

### Download fails / no artifact visible?

- **404 / sign-in page:** Sign in to GitHub and verify access to
  `RIVANOXcom/rivanox-audiohub`, then open the exact run link above.
  The link is not an anonymously hosted static file.
- **No Artifacts section or expired artifact:** Check the run's Summary,
  not Source checks or Releases. If the artifact has expired, an
  authorized CI operator must create a fresh isolated preview build.
- **ZIP opens but no image appears:** Verify the downloaded archive is
  complete and unzip it before selecting the image.
- **Permission or browser download blocked:** Use a logged-in browser
  with adequate local storage and without a restrictive download
  extension. Do not search for the ZIP under GitHub Releases.
- **Want a stable public image?** That requires explicit review,
  Pi hardware proof and a *separate* official release decision.
  Do not mark an experimental artifact as production ready.

## Prepare one isolated first-boot check

Hardware: Raspberry Pi 4, official/reliable compatible power supply, a
**spare** microSD (at least 16 GB, use 32 GB if available), known USB
speaker (intended Edifier R600USB), Bluetooth phone, a second computer
to download/flash the image.

1. Unzip the GitHub artifact. Preserve the supplied checksum file.
   Verify the compressed image's SHA-256 against `SHA256SUMS.txt`
   *before flashing*. On Linux/macOS with `sha256sum` installed,
   run `sha256sum -c SHA256SUMS.txt` from the extracted folder.
   On Windows, `Get-FileHash <image.img.xz> -Algorithm SHA256`
   gives a value to compare manually to the checksum file.
2. Open Raspberry Pi Imager, choose **Use custom**, select the
   `.img.xz` file and write it to the **spare** SD card. If the installed
   Imager version refuses XZ, decompress the image with 7-Zip or `xz`
   and select the resulting `.img`. This **erases the target card**.
   Do not configure a shared Wi-Fi password, SSH or real private
   credentials as part of this unverified setup.
3. On an **isolated** bench with **no Ethernet** and **no WLAN
   provisioning**, connect the intended USB speakers, insert the
   flashed card and power the Pi 4.
4. During the initial pairing period (source currently models a
   ten-minute window), search on the phone for an AudioHub Bluetooth
   device; observe whether it appears and whether pairing works.
   If it connects, start **low-volume** test audio and check the USB
   speaker. Device discovery, pairing and sound are all
   **UNVERIFIED** until observed in the lab.
5. Record whether the Pi boots, any LED or HDMI indicators, Bluetooth
   discoverability, pairing, USB output and behavior after one
   deliberate power cycle. Stop immediately on unexpected behavior.
   Do not invite unrelated phones to pair.
6. If sound fails, record the precise failing stage and useful
   screenshots (redact MAC addresses and other identifying data).
   Do not assume that the status page can be reached from a phone.
   This image does **not** include a working secure phone Wi-Fi setup,
   a verified admin login, or a guaranteed remote diagnostics route.

### Minimal test record

| Check | Result to record |
| --- | --- |
| Flash tool / image SHA-256 verified | tool/version and yes/no |
| Pi4 model and power | model/revision, power type |
| USB Edifier R600USB | connected/recognized/unknown |
| First boot | visible boot indicators and elapsed observations |
| Phone Bluetooth visibility | detected/not detected |
| Pairing | success/failure/error |
| Low-volume USB audio | audible/silent/errors |
| Reboot and reconnect | yes/no/unknown |

## Why we are not releasing this image

The image belongs to an **older source branch** than the separate
security and networking PRs #15–#19. Source checks succeeding in newer
branches **do not retroactively update this image**. In particular,
the initial image may use an unauthenticated status HTTP listener,
initial Bluetooth pairing is not a hardware-bound owner proof,
phone-only Wi-Fi onboarding is absent, and a working simultaneous
three-channel mix remains untested.

Rootfs packaging tests, an Actions artifact and an XZ digest check are
not a substituted physical boot/audio acceptance. Official release
policy, security and third-party legal requirements still apply.

Tracking: PAPA `PJ2611-0001:R001`, AH-006 #3272,
AH-009 #3275, AH-001 #3267. **No installation/deployment/release GO.**
