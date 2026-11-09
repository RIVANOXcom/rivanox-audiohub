# Pi4 Bluetooth first-use readiness – operator ALPHA

This is **a local-only, read-only diagnostic and guided user experience**,
NOT secure owner claiming, Bluetooth device enrolment, phone Wi-Fi setup,
or hardware approval. No stable release. Raspberry Pi 4 + Edifier R600USB
compatibility and simultaneous dual Bluetooth audio remain unverified.
The existing Bluetooth agent uses BlueZ \`NoInputNoOutput\` and a limited
600-second boot window for a maximum of two paired devices. **It does not
cryptographically identify the owner**: a nearby device may attempt to
pair during the initial window. Use an operator-controlled isolated bench.

## First-use without an exposed device management website

1. Flash a separately obtained, hash-verified **UNVERIFIED** Pi4 image to
   a disposable SD card **only after operator approval**. Never replace
   an installed system's card/configuration automatically. Do not
   interpret a successful CI image build as tested hardware.
2. During the first 10 minutes after cold boot, **only in the physically
   isolated and supervised test space**, use the Bluetooth menu on the
   intended phone/tablet and look for **AudioHub**. If it is visible,
   select it; the existing agent accepts at most two devices in the
   initial experimental window. Do not interpret pairing success as
   secure owner claiming or verified stereo output. If other nearby
   phones could connect, do not use this experimental window.
3. On an already-authorized Pi **local console**, independently check:

       PYTHONPATH=/opt/audiohub/src python3 -m audiohub.pairing_readiness

   To obtain only anonymous machine-readable counters and fixed states:

       PYTHONPATH=/opt/audiohub/src python3 -m audiohub.pairing_readiness --json

   This performs one **local system D-Bus read** of BlueZ
   \`GetManagedObjects\`. It does NOT call \`Set\`, \`Pair\`, \`Trust\`, open
   a network socket, install profiles or change permissions.
   It reports the adapter powered/discoverable/pairable flags, at most
   three **bounded aggregate** device counters and a status:
   \`initial_window_observed\`, \`known_devices\`, \`device_limit\`,
   \`paired_untrusted\`, \`window_closed\`, \`unexpected_open\`,
   \`controller_off\`, \`inconsistent\`, \`ambiguous_adapter\` or
   \`unavailable\`. BlueZ state can change immediately after reading;
   it is not a binding authorization, attestation or owner proof.
4. **Headless SD-card alternative:** The existing first-boot diagnostic
   writes \`AUDIOHUB-TEST-REPORT.json\` to the FAT boot partition,
   subject to normal mounted-partition safety checks. After a controlled
   Pi shutdown, remove the SD and read this JSON on a trusted computer.
   In addition to existing USB and runtime aggregate status, the top-level
   \`bluetooth_pairing_state\` and \`bluetooth_paired_devices\` now convey
   the last coarse read-only Bluetooth state. It never contains
   identifiers, MACs, passkeys or SSIDs; it cannot be trusted as
   tamper-resistant hardware evidence. Do not edit and reinsert the SD
   expecting to authorize or reprovision Bluetooth or Wi-Fi.
5. \`known_devices\` means a paired/trusted record exists and it may be
   possible to reconnect from the *existing device*. Verify actual
   connection and audio with the operator and speakers. It is **not**
   an authenticated owner claim or proof that two A2DP senders can play
   concurrently. \`window_closed\` means the first-boot window is
   unavailable; there is **no** approved post-claim pairing frontend.
   Do not reboot or force a global discoverable window to work around
   the limit. \`unexpected_open\` is a security warning to stop new
   pairing attempts and inspect the local BlueZ agent.
6. If no USB sound is heard, do **not** infer that Bluetooth is broken
   from the pairing counters alone. The separate physical Edifier
   LEFT/RIGHT soundcheck and other hardware validations still apply.
   No pairing status grants a release GO.

## Rollback and privacy

The command makes no changes and requires no rollback. To stop viewing
a report simply close the local console or remove the SD after a proper
power-off. Installed BlueZ and system services remain untouched. There
is no remote write API, phone onboarding, credentials, automatic restart,
automatic discovery extension or changing of pairing/permission modes.
If the agent is unexpectedly open, a separately authorized owner must
secure the Pi offline; do not issue remote repair commands based solely
on this diagnostic.

The image builder continues to pin Pi OS inputs and install sources
into \`/opt/audiohub/src\`. A newer image containing this feature is
necessary to use the new Pi command and SD report; older image
artifacts and the Windows test ZIP do not contain this Pi module.
Use the exact GitHub CI artifact SHA and manifest, not an undocumented
flashable release claim.

## No-Python, no-network SD report viewer (Windows, Mac or Linux browser)

A self-contained five-language HTML viewer is available as
\`AUDIOHUB-BOOT-REPORT-VIEWER.html\` inside the verified experimental
Windows operator ZIP, and as \`web/boot-report-viewer.html\` in the
canonical GitHub source. Open the HTML file locally in an up-to-date
browser **without running a local server or installing Python**. The Pi
does not need a network connection. The normal AudioHub read-only web
prototype also links to the same viewer; the file is still selected
locally on the computer or phone and never uploaded to the Pi.

After the operator **safely powers off the Pi**, remove its SD card and
access the FAT boot partition on the computer. Select only
\`AUDIOHUB-TEST-REPORT.json\`, no larger than 4096 bytes. The viewer
recognizes the original offline diagnostic schema, only the fixed,
bounded Bluetooth readiness states and the final snapshot's aggregate
USB/controller status. It displays a localized safe next step for
closed, open, untrusted or inconsistent Bluetooth status, and supports
an explicit Clear action. The file is parsed in your browser memory;
no fetch, upload, logging, persistent storage or network calls are
performed by this standalone page. The raw JSON never becomes HTML,
and private strings are never shown in the output. Even a valid report
is **untrusted removable-media data**; it does not authenticate an
owner, grant pairing access, prove a functioning Edifier speaker, or
approve a release. New Pi4 builds can emit the Bluetooth readiness
fields; old schema-compatible reports show only their existing
aggregate audio health and say that Bluetooth pairing is unavailable.

Rollback: close the HTML page, or use Clear result. No configuration,
Bluetooth device, Pi service, file or SD content is ever modified.
