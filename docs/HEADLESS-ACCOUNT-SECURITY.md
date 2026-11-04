# Headless account hardening — alpha

Workbench `PJ2611-0001:R001`, AH-005 ID 3271. This change is staged on the Bluetooth security review branch and is **not merged or released**.

The pinned pi-gen builder requires `FIRST_USER_PASS` for the initial `audiohub` user. It currently generates a strong random build-time value, but that password would be identical for all SD cards flashed from the same public image. A password shared at image level is not acceptable as the final ownership mechanism.

The custom image-install stage now creates the user-owned EQ configuration first, then performs `passwd -l audiohub` and `gpasswd -d audiohub sudo` inside the image root. This removes interactive password authentication and unnecessary administrative group privileges from the headless service account. SSH is separately disabled in the image-builder configuration.

Before integration/release, verify the produced image's `/etc/shadow` entry is locked, its `/etc/group` entry excludes `audiohub` from `sudo`, and the user-level PipeWire/WirePlumber, Bluetooth routing and status services still start under persistent user lingering. Unit tests check the packaging commands and order only; they **do not** prove actual image contents or first-boot behavior.

Production secure owner-claim, device recovery, newly authorized pairing and any explicit maintenance access remain separate design and hardware-acceptance tasks. No stable image may be released from these source-only checks.