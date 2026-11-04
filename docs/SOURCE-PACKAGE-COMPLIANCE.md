# Source package inventory and release compliance gap (AH-008)

**Status: NOT AUDITED.** A source package list cannot establish the licenses or exact contents of a distributed SD image.

## Read-only source inventory

Run `PYTHONPATH=src python3 -m audiohub.package_inventory` in the source checkout. The command only reads the 15 declared Debian package names from `image/stage-audiohub/00-packages/00-packages-nr`, the `pi-gen` source pin in `build-image.sh`, and broad notice references in `THIRD_PARTY_NOTICES.md`. It makes no changes, installs nothing, does not contact the network, and never publishes or deploys.

Exit **0** means only the source list is syntactically valid and provisional upstream groups are mentioned; exit **2** indicates missing/invalid source declarations. JSON **always** states `license_audit_accepted: false` and `release_ready: false`.

The declared 15 source packages exclude transitive dependencies, base Raspberry Pi OS packages, exact versions, architectures, copyright files, copied software, and potential other binary inclusions. Mentioning the Debian group in notices does **not** resolve an individual package's license. Scream is listed in third-party notices for the optional network-audio architecture, but the current experimental AudioHub Python receiver does **not** bundle the upstream Scream Windows driver or C receiver in the image package set. If that changes, a separate redistribution audit is required.

## Mandatory pre-release root filesystem and legal audit

1. Build only in an approved isolated environment from a pinned source ref; retain commit SHA, pi-gen SHA, build log, artifact SHA256 and image integrity verification.
2. Inspect the **actual generated root filesystem**. Export installed `dpkg-query` package/version/architecture data; collect corresponding `/usr/share/doc/<package>/copyright` files and inventory non-package binaries/content. Save data in a restricted review location.
3. Review complete transitive dependencies, exact package copyright/licensing, redistributability, attribution, source-offer/copyright obligations, security exposure and notices. Tie a versioned SBOM to the actual image digest.
4. Obtain an independent legal/compliance review and explicit owner acceptance in addition to every applicable Pi4 physical and security gate G1–G10. Do not infer license terms merely from Debian package names, or transfer third-party rights via the RIVANOX commercial licensing option.

**This source-level inventory is neither a binary SBOM nor a legal opinion or release approval.** No installed package versions, full license texts or release digest have been validated by this task.

PAPA project `PJ2611-0001:R001`; AH-008 Workbench requirement 3274; refer to `docs/RELEASE-ACCEPTANCE.md` and `docs/RELEASE-POLICY.md`.
