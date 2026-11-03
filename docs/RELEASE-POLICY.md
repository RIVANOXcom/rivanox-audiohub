# Raspberry Pi image release policy

## Publication rule

**No official image without hardware acceptance evidence.**

The repository may host source commits and internal test artifacts. These must never be described as a stable, supported or ready-to-flash SD image. Preview build artifacts must be clearly marked unverified.

Release workflow:

1. Source tests, dependency and license inspection.
2. Create a reproducible image from a reviewed source ref.
3. Inspect the complete produced root filesystem, including secrets and service hardening.
4. Boot and exercise the image on a physical Raspberry Pi 4 using a supported USB audio speaker.
5. Confirm phone pairing without monitor or keyboard, all supported audio routes, control UI and recovery.
6. Review third-party licensing and security acceptance checklist.
7. Publish `AudioHub-Pi4.img.xz`, `SHA256SUMS.txt` and human-reviewed notes only after approval.

The image named `AudioHub-Pi4.img.xz` will be downloadable from GitHub Releases. The release with the most recent stable version is exposed at https://github.com/RIVANOXcom/rivanox-audiohub/releases/latest.

Do not embed reusable passwords, private keys, personal credentials, undisclosed upstream binaries or unsupported service claims in release assets.
