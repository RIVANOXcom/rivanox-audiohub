# AudioHub Windows TLS Bridge — Portable ALPHA (operator bench only)

**NOT a released app. NOT approved for home, workplace, or public networks.**

This folder contains the Windows side of AudioHub's manually operated,
authenticated TCP audio bridge. It runs using Python's standard library.
There is no installer, Windows driver, certificate, password or shared key
included. Nothing starts automatically.

## Four steps for a manually authorized isolated test

1. **Prerequisites.** Windows 10/11, separately installed Python 3.11 or
   newer with TLS 1.3. **Only for Windows program-audio streaming**, a
   separately installed Windows Scream virtual audio driver is also needed.
   Configure its **unicast 48 kHz/16-bit/stereo UDP** output
   exclusively to **127.0.0.1:4010**. The driver's ability to do this has
   **not been verified on a real Windows machine**. Its default multicast
   mode is not compatible. Do not use raw Scream on a home/work LAN.
2. **Private credentials.** On a separately isolated Pi4 test bench prepare
   a unique temporary 32-byte shared-key file and a Pi TLS 1.3 certificate.
   Privately copy only the shared key bytes to the Windows computer and
   restrict the file using NTFS ACLs. Obtain the Pi *public* certificate's
   **DER SHA-256 hex fingerprint** over a trusted offline channel. Never
   copy the Pi TLS private key to Windows. Do not use the example addresses
   or placeholder hashes without replacing them.
3. **Optional graphical test controls.** In a terminal inside this extracted
   folder, launch the local graphical setup:

       py -3 START-WINDOWS-BRIDGE.py --gui

   The GUI contains labeled Pi IP, exact TLS certificate SHA256, hidden
   private-key path with file picker, session duration and an explicit
   `ISOLATED` confirmation. Choose **Check locally (offline)** before
   **Start isolated session**. Check runs without any socket; Start
   rechecks everything and opens exactly one authenticated test session.
   **Stop** requests that TCP/UDP and playback forwarding close; the
   window does not reconnect automatically. If the desktop Tk interface
   is not installed, use the terminal workflow below. Neither workflow
   creates credentials, modifies ACLs or installs a Scream driver.

3a. **Terminal checks without connecting.** In a terminal in this extracted folder:
   
       py -3 START-WINDOWS-BRIDGE.py --self-check
       py -3 START-WINDOWS-BRIDGE.py --check-only

   The first command checks local Python/TLS capability only. The second
   prompts for the isolated Pi's IPv4 address, the independently verified
   public cert fingerprint, the absolute path to the protected 32-byte
   shared-key file, and a 1–30 minute duration. It checks their syntax
   and file shape **without opening a TCP/UDP port**. The Windows file's
   NTFS ACLs and Scream driver configuration are **not** verified.
4. **Manual session (only with operator authorization).** Manually start
   the corresponding Pi server from the repository runbook on a physically
   isolated lab network. Then run:

       py -3 START-WINDOWS-BRIDGE.py

   Re-enter the parameters. The session starts ONLY after you type the
   exact confirmation `ISOLATED`. It binds Windows Scream input to loopback
   only, opens a single pinned TLS 1.3 connection to the Pi and expires
   automatically after the configured duration. No settings are stored.
   The final PCM count is not evidence that sound was audible.

If Python is not registered as `py`, use `python` with a separately
installed compatible version. Do not disable Windows execution or security
policies to run this package.

## First hardware step: quiet speaker tone WITHOUT a Scream driver

Before configuring the Windows Scream driver, an operator can verify the
**authenticated Windows-to-Pi PCM audio path** using a self-generated
440 Hz / 5-second test tone at approximately -29.5 dBFS with 200 ms fades.
This requires no Windows Scream driver, program audio capture, third-party
runtime package, or external audio file. It still requires the isolated
Pi4 with the separately configured local private PipeWire/USB sound sink,
fresh shared key, pinned certificate, explicit Pi server start, and approved
network access. Start at minimum speaker/master gain to avoid surprises.

**GUI:** use `py -3 START-WINDOWS-BRIDGE.py --gui`, select
**Pi speaker test: quiet 5-second tone (no Scream driver)**, fill the
private Pi IP, verified certificate fingerprint and key path. Choose
**Check locally (offline)**, type `ISOLATED`, then **Start isolated session**.
The same **Stop** button can interrupt the short tone. No Windows UDP port
is opened in soundcheck mode. The Pi still authenticates the TLS connection
before any audio is emitted. There is no automatic retry.

**Terminal (no Tk required):** use
`py -3 START-WINDOWS-BRIDGE.py --test-tone --check-only` to check the
local parameters without network access, then — with the Pi receiver
already manually running on the isolated bench —
`py -3 START-WINDOWS-BRIDGE.py --test-tone` and confirm `ISOLATED`.
The 5-second tone stops independently of a 1–30 minute maximum session.
A successful frame count means only that data was submitted; the operator
must personally confirm actual sound from Edifier R600USB and separately
verify both sound channels, volume, USB recovery and reconnection. A tone
does **NOT** prove Windows Scream driver compatibility or Bluetooth mixing.

The tone is generated on the Windows bridge, not from the Pi local
soundcheck utility; it therefore exercises the encrypted network protocol,
pinned Pi certificate, manual sender authentication and Pi playback route.

## Identify left/right Edifier channels (stereo mapping)

The driverless low-volume tone can now identify an accidental
left/right swap, a silent channel or unintended mono routing. On the
isolated lab GUI, select **Pi speaker test**, then choose
**Left speaker only**, **Right speaker only**, or
**Left then right (5 seconds)**. The last option plays about 2 seconds
on LEFT, a half-second silent gap, about 2 seconds on RIGHT, and then
silence. Each audible section starts and ends with a fade. The full
sequence stays within 5 seconds at a fixed low level. The previous
**Both speakers** behavior remains the default.

In a Windows terminal, with the existing private key/cert and manual
Pi TLS listener already set up, first check inputs offline:

`py -3 START-WINDOWS-BRIDGE.py --test-tone --test-channel sequence --check-only`

After separate operator approval and at LOW speaker volume, issue
`py -3 START-WINDOWS-BRIDGE.py --test-tone --test-channel sequence`
and type `ISOLATED`. To check a channel independently choose
`--test-channel left` or `--test-channel right`.
`--test-channel` is refused unless `--test-tone` is explicitly enabled.
The soundcheck NEVER opens the Windows Scream UDP listener.

**Observe and record physically:** did LEFT play from the expected
speaker, did RIGHT play from the expected speaker, was either silent,
and was the sequence distorted or swapped? The software cannot hear the
speakers and a green GitHub CI or frame count cannot verify these
observations. Stop immediately if the speaker volume is uncomfortable.
No automatic repair to speaker routing, Windows settings or Pi
configuration is performed. Each repeat needs another manual session.

## Record the actual physical stereo observation (optional, offline)

After the operator-approved **Pi speaker test** in the GUI finishes or
fails, a third action becomes available: **Record physical speaker
observations (local JSON)**. This is the next step after listening to the
Edifier R600USB on the isolated Pi4 bench, not an automated hardware
certificate.

The window asks separately what you **personally heard** from LEFT
and RIGHT: expected side, opposite side, no sound, distortion, cannot
determine, or not checked. Mark the personal-listening checkbox
only if you truly listened to the physical speakers. This matters:
a successful TLS connection or a PCM frame counter does *not*
prove audible sound. If the connection failed before audio began,
save both sides as **Not checked** without claiming you listened.

Choose **Save private JSON locally** and an explicit new filename.
No observation file is written automatically. A preexisting destination
is never overwritten. The small report includes only the selected
test mode, whether the session completed, was stopped or failed,
the client PCM frame count, UTC time, manually selected observations
and the source SHA from the local alpha manifest *when available*.
It deliberately contains **no Pi address, Windows username, private
key, key path, certificate fingerprint, serial, audio waveform,
free-text field or network endpoint**. Source SHA in a local JSON
is not a signature or proof of hardware authenticity.

Every exported record is classified
`UNVERIFIED_HUMAN_OBSERVATION`, with `hardware_verified=false`,
`release_ready=false` and `review_required=true`, even when
both speakers were heard. This is an operator-authored observation,
not an automatic approval or a new production GO. The report is
never sent to GitHub, Workbench, RIVANOX, the Pi or a third party.
The owner may **separately** submit the file through an approved
private review channel. Protect the local JSON with normal
Windows account permissions and delete it later only under the
owner's own retention procedure. No additional OS changes occur.

For the first test, select **Left then right (5 seconds)**, listen,
then record whether the two sounds came from the expected speaker
positions. If distorted or silent, stop and leave the result
explicitly unapproved; inspect physical USB/audio routing offline.
A successful report export does not verify concurrent Bluetooth,
Scream driver compatibility or 24-hour stability.

## Smoke test, cancellation, rollback

Confirm actual low-volume USB sound from an Edifier R600USB on a separate
Pi4 test bench. Test a WRONG certificate fingerprint and a WRONG shared key
individually to verify no audio starts. Verify time-limited socket closure
and playback stop on USB removal. Capture only redacted manual observations.
**Ctrl+C** ends a manual session. Restore the previous Windows audio
output, stop the separate Pi process and remove operator-approved
temporary test firewall rules to roll back. Credential revocation and
cleanup are separate owner-controlled tasks. The app never auto-installs,
auto-pairs, writes registry entries, changes network settings, deploys
or erases secrets.

## Verify origin and completeness

Read SOURCE-MANIFEST.json in this directory. Its `source_sha` must match
the exact corresponding GitHub draft commit. The ZIP SHA256 is printed by
the official GitHub source-build job in SHA256SUMS-WINDOWS.txt. Compare the
locally downloaded inner ZIP with this checksum before running. GitHub's
outer Actions artifact ZIP has its own independent digest and expiry.
This package contains only a hand-picked set of source modules, the
corresponding source manifests, AGPL-3.0-only LICENSE and third-party notices,
and local operator instructions. It is not signed Windows code and does
not imply legal, Windows driver, USB hardware or production approval.

Further Pi, certificate, trust-boundary, 2 Bluetooth + LAN and recovery
instructions: README-ISOLATED-LAB.md in this bundle.
