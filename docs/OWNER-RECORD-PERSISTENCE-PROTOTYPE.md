# Persistent owner record prototype (AH-005 / AH-001)

**STATUS: OFFLINE SOURCE PROTOTYPE — NOT AN OWNER IDENTITY OR PHONE
ONBOARDING IMPLEMENTATION.** No image or service installs or invokes this
module. It is a security building block pending hardware and design review.

The existing claim policy in draft PR #16 is in-memory and resets on reboot.
Its `trusted_factory_unowned` and `trusted_physical_event` booleans are
untrusted without a privileged local adapter. This follow-on branch adds
`src/audiohub/owner_record_store.py`, **not** an automatic connection between
those parameters and the filesystem.

## Persisted record behavior

- The trusted host must create a protected, preexisting owner-state directory
  (Linux mode exactly 0700, owned by the invoking UID). The module rejects
  unknown, permissive, missing or symlinked final directory components.
- `inspect()` reports three **structural** conditions:
  `missing_untrusted`, `invalid`, or `record_present_unverified`.
  Missing or malformed state **never** implies that factory enrollment may
  begin. All results have `durable_owner_verified: false`,
  `network_onboarding_enabled: false`, and `release_ready: false`.
- `seal(public_key, trusted_physical_approval=True,
  trusted_factory_unowned=True)` accepts a 32-byte *public-key candidate*
  from an as-yet-undefined authorized adapter. The booleans are NOT a proof
  of genuine physical owner presence and are NOT safe to expose as HTTP or
  Bluetooth parameters. This code does **not** validate the public key
  cryptographically or prove its possession.
- Only a SHA-256 fingerprint of the supplied public bytes is stored; neither
  a private signing key nor the temporary proof/session token is written.
  The record has a rigid schema, duplicate JSON keys are rejected, and the
  file must be regular, UID-owned, mode 0600, have one link and be no larger
  than 512 bytes. No credentials are included in status output.
- A single `O_CREAT | O_EXCL | O_NOFOLLOW` write protects against replacing
  an existing or symlinked owner record. The code fully writes the file,
  fsyncs the file and its containing directory before returning. A
  mid-write power loss may leave an **invalid** record requiring controlled
  recovery. The implementation deliberately does not delete, overwrite or
  recreate it automatically. This is fail-closed, NOT automatic crash
  recovery or power-loss durability proof.

The store has no web/BlueZ/NetworkManager/shell access and no default path
used by a running daemon. Tests run only against temporary local folders.

## Remaining integration and security gaps

1. Choose and validate a user-friendly, physically plausible trusted
   presence mechanism and an independent out-of-band phone proof channel.
   A caller passing `True` does not prove an event occurred.
2. Design an authenticated first-owner credential with **proof of private
   key possession**, supported mobile platform transport, and protection
   against replay, cross-site requests, account/session theft and repeated
   unauthorized enrollment. A fingerprint on disk cannot verify a signature.
3. Specify the immutable factory-unowned root of trust, directory owner,
   boot sequence, privilege separation and power-loss recovery policy.
   For ordinary SD cards, UID-only filesystem permissions do **not**
   protect against a malicious user with root or offline filesystem access.
   Full SD rollback/copy detection or an anti-rollback root of trust is
   **not** implemented.
4. Only after owner verification may an explicitly reviewed adapter
   connect this record with the short-lived claim policy and enable
   authenticated phone Wi-Fi provisioning. The read-only status web UI
   stays on loopback by default per PR #15, and this branch does not change
   its bind policy or image services.
5. Validate recovery after a torn write, dual claiming requests, read
   corruption, symlink/hardlink attacks, factory reset, power cycle,
   no-network first boot and real Pi4/Edifier/phone security behavior.
   Current tests do **not** prove hardware behavior or product security.

Possible recovery approaches requiring owner review: (A) a verified
physical factory-reset flow with explicit data-loss acknowledgement,
or (B) a trusted recovery credential issued during initial enrollment
and presented with local presence. Neither is implemented or authorized.

Project `PJ2611-0001:R001`, requirement AH-005 #3271, linked AH-001 #3267,
and release acceptance G2/G7. **No approval, production installation,
working smartphone onboarding, completed security audit, or release.**
