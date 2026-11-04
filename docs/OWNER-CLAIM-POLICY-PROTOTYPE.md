# Owner claim policy prototype — design boundary (AH-005 / AH-001)

**Status: SOURCE-ONLY POLICY MODEL, NOT AN OWNER ENROLLMENT SERVICE.**
The code in `src/audiohub/owner_claim_policy.py` is intentionally not
referenced by a systemd service, web route, Bluetooth agent or image installer.
It is not callable by a phone, does not provision Wi-Fi, and does **not**
grant network administration privileges.

## What is modeled

- Default-deny when the trusted persistent factory-unowned status is unknown.
  No automatic claim window opens on a reboot.
- Only a caller that has already verified a **trusted local physical event**
  may call `arm_physical(trusted_physical_event=True)`. A Python boolean
  is **not itself evidence** of such an event. The actual hardware event
  source has **not** been implemented or verified.
- After a permitted event, a fresh CSPRNG-generated 256-bit one-time
  proof may be communicated **out of band** by a future trusted physical
  adapter. It must not be sent in HTTP responses, broadcast via Bluetooth,
  included in logs, displayed in unauthenticated status, or shipped in an
  image. This project has not chosen a feasible headless out-of-band
  delivery mechanism.
- The proof has a 120-second time-to-live and a maximum of five failed
  attempts. Only the SHA-256 digest is retained in process memory;
  comparisons of equal-size digests use `hmac.compare_digest`.
  Repeated claim calls and further windows after success are rejected.
- Successful volatile verification produces a separate 256-bit
  short-lived session capability, expiring after 600 seconds. It may be
  revoked. This capability is **not** a persistent owner credential or
  a secure phone session. The model never records secrets to the SD card
  and never marks `durable_owner_verified`, `network_onboarding_enabled`,
  or `release_ready` true.
- An invalid/missing entropy source fails closed. The policy uses a lock
  to serialize concurrent attempts.

## Mandatory integration before any phone-visible onboarding

1. Specify a feasible *accessible* physical presence action for the actual
   Pi4 enclosure (button/verified NFC/unique out-of-band label, etc.).
   An LED flash pattern or a generic Bluetooth Just Works bond is not
   automatically an authenticated physical owner proof.
2. Provide a **trusted hardware-only adapter** that cannot be invoked by
   unauthenticated HTTP, Bluetooth or LAN traffic. Integrate robust
   debouncing and anti-replay at that boundary.
3. Design a per-device *secure out-of-band proof delivery mechanism* for
   a user with **only a phone**, no screen, keyboard, Linux commands or
   factory-shared password. This design must be reviewed for physically
   nearby attackers, phone accessibility and recovery.
4. Implement a permission-protected, **atomic durable ownership store**
   with factory-state verification, surviving reboot, read failure = deny,
   no stale token/session replay and a tested physical factory reset.
   A new in-memory `OwnerClaimPolicy` instance after reboot does not know
   a previous claim took place. Never set `trusted_factory_unowned=True`
   merely because there is no writable owner file.
5. Authenticate every control-plane state mutation, provide CSRF/origin
   defenses and key/session rotation; gate LAN listeners using **verified
   durable ownership**, not a local boolean or a one-off claim success.
   Encrypt and protect Wi-Fi credentials; never expose them in public
   status or build assets. Test denial, request floods and power loss.
6. Verify actual Pi4 first-boot and recovery with R600USB and a phone,
   including unclaimed/claimed/failed Wi-Fi paths. Complete G2/G3/G7
   physical and security acceptance before any release.

The existing read-only alpha status UI remains bound to loopback by
default (PR #15) and is **not** automatically changed by this branch.
In particular, no initial pairing timeout or cryptographic claim policy
proves that an arbitrary first Bluetooth phone is the appliance owner.

## Tests and decision

The pure unit tests cover explicit local-event precondition, one-time
secrets, expiry, five-attempt limit, malformed inputs, replay, session
revocation, public redaction, unavailable entropy and nonintegration
with automatic services. Tests are mocked/source-only. There has been
no real physical button, smartphone session, authenticated Wi-Fi,
installer or Raspberry Pi audio test.

**Owner decision still required before live enrollment:** an acceptable
physical/OOB workflow and recovery UX, device-specific durable storage
trust model and authenticated phone transport. Two implementation routes
can be evaluated: (A) trusted physical switch plus short-lived
out-of-band QR/NFC or secured label, or (B) factory-provisioned unique
device secret/QR with possession proof and secure reset policy. Both
need security and usability validation; neither is selected or enabled.

Project: `PJ2611-0001:R001`; AH-005 #3271 and AH-001 #3267.
No production approval or release is implied.
