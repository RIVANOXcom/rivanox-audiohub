# Owner key proof-of-possession prototype — AH-005

**Status: offline test-only cryptographic verifier, not a phone login or
proof of physical ownership.** This work is stacked on the owner record
prototype in draft PR #17, itself based on the one-time physical event
policy in PR #16 and localhost status lock in PR #15.

## Implemented in source only

The `OwnerRecordStore` now supports
`matches_public_key(candidate)`: reopens the preexisting UID-owned 0700
directory and strict 0600 owner record, compares a SHA-256 fingerprint
using constant-time digest comparison, and returns only a boolean. It
does **not** mark the owner as verified or change any service permissions.

`OwnerPossessionChallenge` enforces a single outstanding challenge:
it requires the candidate 32-byte Ed25519 public key to match the
protected owner record, uses 32 fresh random nonce bytes, and builds the
exact message:

```text
ASCII "RIVANOX-AUDIOHUB-OWNER-POSSESSION-V1" || 0x00
|| SHA256(raw_ed25519_public_key)  [32 bytes]
|| fresh_random_nonce              [32 bytes]
```

A future trusted phone client must sign those exact bytes with its
corresponding **private key**; the device checks the 64-byte Ed25519
signature using the maintained `cryptography` library (not custom
cryptography). The message expires after 60 seconds. A fifth failed
verification closes it, successful verification consumes it, and
replay of an old signature does not authenticate a new challenge.
A repeating entropy source between consecutive challenges is rejected.
All checks re-read the owner record before accepting a proof.

Successful `verify()` returns only a boolean and intentionally does
**not** create a privileged web session, grant Wi-Fi access or open
an HTTP listener. `public_status()` always returns
`owner_authenticated:false`, `network_onboarding_enabled:false` and
`release_ready:false`. The prototype never handles private keys and
never enables a network service.

## Verification

`tests/test_owner_challenge.py` generates real Ed25519 private keys
only in the ephemeral test process and exercises actual signing and
verification, wrong public keys, wrong domain, tampering, replays,
timeouts, denial after five failures, concurrent challenges, record
mutation, missing crypto backend and malformed input. No real owner
secret is committed or logged.

The source-check workflow installs **test-only**
`cryptography==46.0.4` in an isolated Python virtual environment.
It is **not installed into a Pi OS image**. A future production
package must pin, audit and license this dependency (including its
transitive native libraries) before it is used on hardware.

## Required next steps and explicit blockers

1. Select and validate a genuine *physical* first-owner presence
   mechanism, headless out-of-band proof transmission and secure
   factory-unowned root of trust. A caller passing
   `trusted_physical_approval=True` is **not** trusted hardware.
2. Validate the public key's origin, its durability and phone private
   key custody, and link the persistent record atomically to real
   physical enrollment. File permissions alone do not protect an
   SD card from privileged/offline attackers or rollback.
3. Design a **separately reviewed authenticated session service**
   with per-request authorization, CSRF/origin checks, anti-bruteforce
   limits across restarts, TLS/channel protection, session revocation
   and smartphone-friendly account recovery.
4. Only once authenticated device ownership has been proven may
   local-network status or phone Wi-Fi provisioning be permitted by
   explicit policy. This PR provides **no** Wi-Fi credentials path,
   Bluetooth setup control, login page, network listener or
   authenticated session.
5. Physical tests on Pi4 plus Edifier R600USB, Android/other phones,
   reboot/power loss, corrupted and copied SD, proximity attacker,
   failed Wi-Fi and 24-hour run remain **unperformed**.

No image installation, approval, service changes or release is authorized.

Tracking: PAPA `PJ2611-0001:R001`, AH-005 #3271,
AH-001 #3267; acceptance G2/G3/G7/G8, licensing AH-008.
