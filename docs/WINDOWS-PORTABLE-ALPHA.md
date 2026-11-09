# AudioHub Windows TLS Bridge — Portable ALPHA (operator bench only)

**NOT a released app. NOT approved for home, workplace, or public networks.**

This folder contains the Windows side of AudioHub's manually operated,
authenticated TCP audio bridge. It runs using Python's standard library.
There is no installer, Windows driver, certificate, password or shared key
included. Nothing starts automatically.

## Offline certificate cross-check (recommended before any audio test)

The Windows GUI now has a **Choose public cert…** file picker. A copied
Pi PUBLIC server certificate alone **does not establish trust**. Its SHA256
must be compared against the value separately observed at the Pi's
**physically trusted console** or over another owner-verified offline
channel. Never accept a fingerprint supplied only with an untrusted
download, chat message, LAN discovery or certificate file.

1. With the Pi4 physically under your control, confirm the isolated
   test identity. On the trusted Pi console, print the certificate's
   **DER SHA256**, not the text-file/PEM SHA256:

       set -o pipefail
       openssl x509 -in /path/to/your/pi-server-public.crt -outform DER | sha256sum

   Compare all **64 lowercase hexadecimal characters** through an
   independently trusted offline channel. No server private key should
   ever leave the Pi.
2. Copy **only the public certificate** in PEM or DER format to a
   private operator-approved folder on the Windows test PC. Keep the
   individually provisioned 32-byte per-bench shared key separately
   protected, and verify Windows key-file NTFS ACLs manually.
3. In \`py -3 START-WINDOWS-BRIDGE.py --gui\`, type the independently
   verified Pi SHA256 into the existing fingerprint field; it is
   intentionally **not filled automatically**. Select the public
   certificate with **Choose public cert…**. Choose
   **Check locally (offline)**. The GUI compares the local certificate's
   exact DER SHA256 to the independently entered fingerprint, without
   opening TCP/UDP. A mismatch, missing/linked/invalid cert or an
   unrelated private key file blocks the connection. The comparison
   is repeated before every manually authorized Start.
4. Terminal-only users can check the same certificate by running:

       py -3 START-WINDOWS-BRIDGE.py --certificate-file "C:\path\pi-public.crt" --check-only

   After entering the Pi address, fingerprint and private key path,
   this performs the same fail-closed offline check. Only after
   separate isolated-lab approval, run the command without
   \`--check-only\`, confirm \`ISOLATED\` and run the existing
   5-second speaker test or the normal Windows Scream bridge.
   To *inspect* a public certificate without keys or sockets, use
   \`py -3 START-WINDOWS-BRIDGE.py --show-cert-fingerprint "C:\path\pi-public.crt"\`.
   **An inspection of a Windows-local certificate is not an independent
   trust check.** Only a hash confirmed at the trusted Pi console
   establishes the expected identity.

The local verification parses exactly one X.509 public certificate
using Python's installed OpenSSL, accepts PEM or DER, refuses linked,
oversized, non-X.509 or private-key files, and compares the DER SHA256
in constant time. It creates no certificates, keys, accounts, trust
store changes, network privileges or services. It does **not**
automatically validate the certificate's origin, hostname, expiry,
issuer trust chain, owner identity or rotation/revocation state.
The existing pinned TLS 1.3 handshake still checks the certificate
against the independently entered value; its Pi-side HMAC key proof
remains mandatory. On a real consumer product, owner enrollment and
certificate/key rotation will need additional approved work.


## Optional offline matching of the two 32-byte lab key copies

A certificate SHA256 pin verifies the Pi TLS certificate, but cannot tell
whether the separate Windows and Pi shared-secret **files match**. The
Windows portable alpha now offers an optional, *read-only* key-copy check
before any manually authorized session, without printing or transferring
the 32 secret bytes. It does **not** create, repair, replace, synchronize
or rotate credentials. Keep both existing files private and independently
protect their file permissions. The resulting 32-hex character code is a
domain-separated 128-bit HMAC truncation. It is only a private equality
check of full-entropy 32-byte random PSKs: NOT a password, proof of the
Pi's identity, a new login, or a substitute for authenticated TLS/HMAC.
Do not publicly post the code: it can help guess a weak underlying key.

**1. On the physically trusted, isolated Pi console**, read the EXISTING
32-byte secret file only after selecting its correct private path. The
current Pi4 alpha predates the Windows key-code module, so use this
self-contained Python 3 snippet on the Pi instead of assuming that
a new Pi image or module has been installed:

~~~sh
python3 - <<'PY'
import hashlib
import hmac
import os
import stat
from pathlib import Path
p = Path(input("Absolute path of existing Pi 32-byte private PSK: ").strip())
if not p.is_absolute() or any(x.is_symlink() for x in (p, *p.parents)):
    raise SystemExit("Unsafe or linked path")
fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
try:
    meta = os.fstat(fd)
    if (not stat.S_ISREG(meta.st_mode) or meta.st_size != 32
            or meta.st_mode & 0o077 or meta.st_uid != os.geteuid()):
        raise SystemExit("Pi key needs 32 bytes and private owner-only mode")
    raw = os.read(fd, 33)
finally:
    os.close(fd)
if len(raw) != 32:
    raise SystemExit("Wrong key size")
print("PRIVATE Pi key comparison code:",
      hmac.new(raw, b"RIVANOX-AUDIOHUB-OFFLINE-PSK-CHECK-v1",
               hashlib.sha256).hexdigest()[:32])
PY
~~~

Only the *comparison code*, never the raw key, may be manually compared
between the trusted Pi console and the Windows GUI. Keep this code within
the isolated owner's test procedure. If the Pi/Windows copies disagree,
STOP: re-provision the copies manually through an approved private path;
never attempt to fix the mismatch by changing a key automatically.

**2. On Windows**, inside the extracted and checksum-verified portable
test folder, with the existing private PSK stored under user-controlled
NTFS ACLs, show its local code *only when needed*:

~~~text
py -3 START-WINDOWS-BRIDGE.py --show-key-code "C:\private\audiohub-lab-psk.bin"
~~~

No ports open. The program prints a 32-hex local comparison code, not the
secret or file path. In the graphical app, selecting **Show local code
(offline)** performs the same read-only operation; it never fills in or
replaces the independently obtained Pi code.

**3. Compare privately**, and optionally type the Pi code into the
**Pi PSK comparison code** field in the GUI. **Check locally (offline)**
rejects a mismatch; **Start isolated session** checks again. The actual
bridge also verifies the *same loaded key bytes* before it opens the TCP
socket. Terminal-only operators can add
~~~text
--expected-key-code <the-private-32-hex-code-from-trusted-Pi>
~~~
to \`--check-only\` or a separately approved live invocation; this
option never carries the 32 secret bytes. A shell history may retain the
code. Do not mix it up with the separate 64-hex *certificate* SHA256 pin.

A matching optional code only indicates matching key copies. It does not
attest Pi ownership, key randomness, TLS configuration, Windows NTFS
ACLs, a deployed Pi receiver, audible sound or secure key rotation.
If no expected code was entered, previous manual behavior remains intact,
and the real network HMAC challenge is still mandatory. No credentials
are added to the Windows ZIP or to GitHub. Rotating keys and obtaining
operator-approved credentials on real hardware remain separate work.


## Guided staged key rotation preview (manual authorization still required)

The operator can now **preflight two private key copies** offline before a
manual changeover. This is useful when replacing a temporary test key: it
finds accidental reuse, old/new file aliases and mismatches *before* an
authorized cutover. The tool never creates, copies, backs up, activates,
rotates, revokes or deletes credentials, changes a Pi service, or opens any
port. **No operator permission to rotate is inferred from a passing check.**
The Pi4 image in this test pair predates this Windows-only feature.

1. On a physically trusted, isolated Pi console, the **operator** first
   establishes an authorized secure staging/recovery procedure: stop or
   account for any concurrent sessions, preserve the existing working key
   in protected operator-controlled storage, and separately stage a fresh
   cryptographically random **32-byte** secret on both Pi and Windows
   using private channels and owner-only file permissions. Do not use the
   AudioHub GitHub issue, ticket, email, screenshots, shell history or a
   public share for the raw secret. This preview does none of those tasks.
2. Compute the **current** and **new staged** *private* 32-hex comparison
   codes independently on the physically trusted Pi for the corresponding
   two existing private files. The standalone Python snippet in the
   section "Optional offline matching of the two 32-byte lab key copies"
   above works on the older Pi alpha: run it separately for the old and
   staged files. Codes are not key bytes, but MUST still be kept private.
3. On Windows, in the extracted package, open the GUI using
   \`py -3 START-WINDOWS-BRIDGE.py --gui\`. Choose the active (old)
   private key file in the original field, then click **4 · Staged PSK
   preview (offline)**. Select the **existing staged** Windows file,
   enter BOTH independently obtained Pi codes into the masked fields,
   confirm you obtained them from the trusted Pi console, and press
   **Compare old and staged copies (offline)**. A passing result only
   means the two local key copies matched the supplied independent
   private codes at the time of the check, and the codes were different.
   No Pi is contacted. The dialog never switches the active key.
4. For a keyboard-only Windows console, the same no-network preflight is
   available as \`py -3 START-WINDOWS-BRIDGE.py --rotation-preflight\`.
   It prompts for old and staged paths, then asks for both Pi codes using
   non-echoing private prompts rather than command-line arguments.
   Neither preview saves a JSON report, stores codes, or changes OS ACLs.
5. **Only with separate operator authorization**, manually stop both
   running sessions, switch the corresponding protected key configuration
   on the Pi and Windows as a deliberate coordinated step, and recheck
   the independent certificate SHA256 pin plus the newly active key
   code. Start the existing isolated low-volume LEFT then RIGHT speaker
   soundcheck after checking both Pi and Windows are on the *same*
   intended new key. The preview alone does NOT validate TLS or audio.
6. **Rollback** if the new session cannot authenticate or no sound is
   heard: stop both manual sessions, restore the protected previous
   key configuration on both devices through the operator's authorized
   manual procedure, and rerun the offline old-code verification before
   an approved low-volume soundcheck. Do not automatically overwrite,
   delete or retire the old secret. Final revocation, cleanup, log/data
   retention and access-control review remain owner responsibilities.

Any invalid key file, linked path, hard-linked duplicate, wrong 32-byte
size, POSIX unsafe mode, incorrect trusted Pi code or reused old secret
makes the preview **fail closed**. Windows NTFS ACLs are not independently
certified, and the tool cannot establish whether the Pi code really
came from a trusted Pi. Recheck immediately before the manual cutover;
there is no transactional Pi/Windows key switch. A passing preview is
always \`OFFLINE_STAGING_CHECK_ONLY\`, **not** credential deployment,
Pi ownership, physical hardware acceptance, or public release GO.

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
