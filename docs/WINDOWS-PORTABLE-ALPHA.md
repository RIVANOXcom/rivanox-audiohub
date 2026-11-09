# AudioHub Windows TLS Bridge — Portable ALPHA (operator bench only)

**NOT a released app. NOT approved for home, workplace, or public networks.**

This folder contains the Windows side of AudioHub's manually operated,
authenticated TCP audio bridge. It runs using Python's standard library.
There is no installer, Windows driver, certificate, password or shared key
included. Nothing starts automatically.

## Four steps for a manually authorized isolated test

1. **Prerequisites.** Windows 10/11, separately installed Python 3.11 or
   newer with TLS 1.3, and an independently installed Windows Scream virtual
   audio driver. Configure its **unicast 48 kHz/16-bit/stereo UDP** output
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
3. **Check without connecting.** In a terminal in this extracted folder:
   
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
