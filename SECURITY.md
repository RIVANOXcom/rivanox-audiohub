# Security Policy

## Reporting vulnerabilities

Do not disclose a vulnerability through a public GitHub issue. Use GitHub's **Report a vulnerability** feature when enabled; otherwise contact [RIVANOX Support](https://rivanox.com/support/) with a request for a private security reporting channel. Do not send secrets or exploit details through public forms.

## Supported versions

No general-availability version exists. Preview builds are for controlled research only. Hardware-specific exploits, exposed setup credentials, Bluetooth pairing bypass, network exposure, and persistence problems are considered release-blocking issues.

## Security principles

- No remotely accessible default administrative password in a public release.
- No permanent unrestricted Bluetooth pairing after device ownership is established.
- Web settings require authenticated access and protection against cross-origin changes.
- No public Internet access, port forwarding, or cloud telemetry by default.
- Per-device onboarding must be usable without SSH or an attached display.
- Never publish an SD image until physical boot, input, output and recovery tests have passed.

Security fixes may be published independently of feature releases. There is no promised response time for this alpha project.

## Preview status/web local-file security baseline (2026-11-05)

The experimental HTTP service is **read-only and loopback-bound by default**;
manual non-loopback binding is an unauthenticated development exception,
not a supported remote management interface. It cannot claim the Pi owner
or change Bluetooth/audio settings.

Static web assets are selected by an allowlist of fixed URLs. Runtime reads
must reject all symlinked path components, FIFOs/devices, empty or oversized
files (512 KiB maximum for any static asset). The runtime status JSON must
also be read as a bounded (32 KiB), ordinary non-symlinked file; malformed,
overlarge, removed or otherwise unsafe status must report **stale/false**
health with zero counters, never raw identifiers or user secrets.

The native Pi rootfs pre-export audit now rejects nonregular, symlinked,
empty or oversized installed web assets, and checks the installed Python
handler retains bounded nofollow reads. Automated source and image tests
are necessary but are not proof of physically secure owner enrollment,
network threat resistance, Pi4/Edifier sound, legal redistribution rights
or GA readiness. Never expose the alpha web port on the public Internet.
