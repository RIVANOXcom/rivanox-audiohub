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
