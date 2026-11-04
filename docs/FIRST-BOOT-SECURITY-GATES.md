# First-boot security gate — pending (AH-001)

**Current outcome: BLOCKED FOR CONSUMER RELEASE.** This source-level record
is not a Raspberry Pi boot report, authorization, or an installable SD image.

## What the alpha source actually provides

- `build-image.sh` builds a clearly labelled **unverified** image only
  with `AUDIOHUB_BUILD_ACCEPT_PREVIEW=YES`, `ENABLE_SSH=0`,
  and a generated non-shared local user password.
- The image stage installs Bluetooth system and PipeWire/status user
  services, user lingering and initial EQ configuration. These
  packaging steps are covered separately by the pending rootfs-audit
  draft PR #6; this change does **not** duplicate that inspection.
- The experimental Bluetooth agent has a time-bounded
  `NoInputNoOutput` initial pairing window. Neither a small
  pairing window nor a bond proves that the first connecting phone
  belongs to the appliance owner.
- Until there is an owner-authenticated status/control service,
  the unprivileged **read-only** local status HTTP preview binds to
  `127.0.0.1:8765` by default. The installer does not opt into
  remote LAN exposure; any deliberate isolated test must explicitly
  select a specific RFC1918 interface IP and the
  `AUDIOHUB_UNSAFE_STATUS_LAN=YES` flag. This protects the current
  alpha prototype but **does not fulfill** the phone-viewable
  headless onboarding requirement.
- There is currently **no** secure device-owner claim workflow,
  phone-only Wi-Fi provisioning, authenticated settings endpoint,
  or proven phone-accessible recovery route. These are missing
  product features, not a recoverable CI error.

## Required prerequisites before automatic LAN status/control

1. Verify device-local owner intent without a reusable shared secret,
   e.g. an independently reviewed out-of-band claim factor, and
   reject nearby unsolicited Bluetooth/LAN claiming attempts.
2. Use per-device credentials, bounded enrollment attempts and
   cryptographically verified owner sessions; never derive privilege
   from source IP, Bluetooth pairing state or unverified hostnames.
3. Provide and verify authenticated phone Wi-Fi setup, offline
   fallback, CSRF/origin protections and physical recovery.
4. Make the control/status server enable its LAN interface **only**
   after the accepted ownership state is established. Ensure that
   data returned before claiming is minimal and redacted.
5. Run independent fresh-SD Pi4/Edifier hardware tests: power-on
   without keyboard, monitor or SSH; phone discovery, USB sound,
   power-cycle recovery, failed Wi-Fi paths, and first-owner
   spoofing/denial trials. Record image hash, source SHA and
   reproducible redacted evidence for release gates G2, G3 and G7.

## Explicit test interpretation

Code tests can demonstrate that a non-owner cannot request a
non-loopback listener *without the opt-in environment* and that
malformed runtime status does not crash the HTTP endpoint. They
cannot prove the device starts, owner identity, successful
Bluetooth audio, browser/phone access, Wi-Fi configuration or
long-term safety. All real-device gates remain **not tested**.

The LAN test opt-in is a temporary developer exception only:
never bake it into a shipped service, image, boot script or default
environment, and never forward port 8765 to the Internet.
A stable release, merge, hardware installation or device
permission change requires explicit independent authorization.

Tracking: PAPA `PJ2611-0001:R001`, AH-001 requirement #3267,
AH-005 #3271, release gates G2/G3/G7 and
`docs/SECURITY-THREAT-MODEL.md`.
