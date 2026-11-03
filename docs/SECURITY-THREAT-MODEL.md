# AudioHub security threat model (alpha)

## Assets and trust boundaries

Assets: local Wi-Fi credentials, Bluetooth trusted-device list, persisted audio settings, owner identity, system configuration, software update channel, and private diagnostic information.

Boundaries: nearby untrusted Bluetooth devices, local network clients, an optional setup access point, privileged OS-level Bluetooth/network services, unprivileged PipeWire audio routing, and unauthenticated browser clients.

## High-priority threats

| Threat | Risk | Required control before stable release |
| --- | --- | --- |
| Nearby attacker pairs during unowned first boot | Unauthorized audio or control | Time-bounded pairing, secure ownership claim and auditable state |
| Reboot reopens pairing forever | Trust bypass | Pairing closed by default once owned; explicitly authorized add-device flow |
| Shared setup hotspot/password | Public reusable entry point | Per-device setup authorization; avoid fixed shared passwords |
| Local network attacker alters settings | Unauthorized volume or credentials | Authenticated API, CSRF protections, origin validation and least privilege |
| DNS/network failure leaves headless device stranded | Unusable device | Recoverable phone-based setup mode with clear state |
| Untrusted image or compromised dependencies | Remote control/malware | Pinned source, checksums, dependency review, no secret embedding |
| Private Bluetooth identifiers in unauthenticated status | Privacy leak | Return only minimal redacted health before ownership |
| Service runs with broad privileges | Privilege escalation | Separate privileged device management from unprivileged audio runtime |
| Firmware/OS lacks maintained security updates | Exposure | Supported OS baseline, security patch policy and tested upgrade path |

## Known alpha limitations

The current pairing agent's no-input/no-output policy and limited window are **not** equivalent to secure cryptographic device ownership. The alpha image must not be promoted to a stable release without resolving this. Wi-Fi first boot/recovery, authenticated web settings, physical factory-reset procedure and a complete rootfs audit are pending.

No public image should contain a universal password, long-lived API key or enabled unauthenticated admin interface. Hardware acceptance remains mandatory.
