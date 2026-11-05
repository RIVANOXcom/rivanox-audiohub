# Tested localhost status boundary in the next alpha Pi image

**Build-time packaging guard, NOT a hardware security certification.**

The temporary native ARM64 image from 2026-11-05, run 42024744603,
already supports flashing but is based on an earlier alpha source ref.
Its default read-only HTTP status server binds to all IPv4 interfaces.
Until secure ownership and encrypted onboarding exist, that image must
be tested off trusted Ethernet/Wi-Fi and should not host a phone setup UI.

This stacked branch carries reviewed draft PR #15's status binding policy
into the actual image source used by the pi-gen installer:

- `src/audiohub/status_bind.py` defaults to **127.0.0.1:8765**.
- An explicit `AUDIOHUB_STATUS_BIND_IP` is required to be a literal
  RFC1918 address, and only if `AUDIOHUB_UNSAFE_STATUS_LAN=YES` is set
  manually by an engineer on an isolated test LAN. There is no auto-enable.
- The web service stays **read-only**. No owner claim, Wi-Fi credentials,
  pairing management or control API is exposed.
- The rootfs pre-export audit verifies `status_bind.py` is installed,
  the web server calls `select_bind_address()`, and the installed
  systemd unit does not opt into unsafe LAN mode. A missing guard or
  a wildcard listener blocks image creation.
- Nine inherited source regression tests plus three new rootfs-image
  contract tests prevent this safety boundary from silently regressing.

The previous experimental image download remains available for the
original isolated Bluetooth/Edifier smoke test. The new image version,
once built in Actions and accompanied by a verified checksum and
provenance manifest, must be separately linked and selected for
additional hardware testing. No current SD card is modified by CI.

**Deliberate usability consequence:** A phone cannot load the status
page from the home Wi-Fi. A real owner-verified, authenticated,
CSRF-protected phone setup flow remains mandatory. The Bluetooth agent
still has the security limitations documented in AH-005. Keep the Pi
on an isolated hardware bench during testing.

Tracking: PAPA PJ2611-0001:R001, AH-001 #3267,
AH-006 #3272, AH-005 #3271. G2/G3/G4/G7/G10 remain unverified.
No merge, installation, official GitHub Release or product GO.
