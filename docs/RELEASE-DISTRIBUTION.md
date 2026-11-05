# AudioHub public SD image distribution – controlled path to Releases

**2026-11-05 status:** Engineering ALPHA, **no published GitHub Release**.
This document is not release approval. The operator controls production
publication; `.github/workflows/publish-image.yml` deliberately fails
until hardware, ownership security and redistribution rights are accepted.

## What exists now

The repository contains native ARM64 test images produced by GitHub Actions,
not persistent public GitHub Release assets. A signed-in GitHub user can
download an expiring ZIP from the run's Artifacts area:

- Latest independently verified development baseline: stacked
  [Draft PR #30](https://github.com/RIVANOXcom/rivanox-audiohub/pull/30),
  SHA `8ab26da637604723e4c29f114cc93a478e0d02f0`.
- [Source tests 42086920486](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086920486)
  **SUCCESS: 226 Python tests**.
- [Native ARM64 image build 42086909475](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086909475)
  **SUCCESS**: Pi image source tests, image production, rootfs pre-export
  guards, exact XZ+SHA256 validation and provenance manifest; status is still
  UNVERIFIED due to missing physical acceptance.
- [Download temporary Actions test ZIP #13443339137](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086909475/artifacts/13443339137),
  606,222,225 bytes; expires **2026-12-05**. GitHub sign-in can be required.
  The bundle contains a single `*-UNVERIFIED.img.xz`,
  `SHA256SUMS.txt`, `PREVIEW-MANIFEST.json` and a redacted `ROOTFS-PACKAGES.json`
  in the newer inventory-enabled development branch. The prior verified PR #30 ZIP
  has only the first three files.

These are **not** publicly downloadable long-lived Releases and they
cannot honestly be called "latest verified stable SD image". The user
should not use them on a trusted home/company network or as a secure
owner-controlled appliance. The Windows UDP receiver, if manually
started for testing, is unauthenticated.

## New automated offline bundle inspector (engineering-only)

`scripts/release_bundle_audit.py` independently checks an extracted
Actions ZIP for all of:

1. Exactly one properly named **UNVERIFIED** `.img.xz` plus only
   `SHA256SUMS.txt`, `PREVIEW-MANIFEST.json` and `ROOTFS-PACKAGES.json` — no accidental
   secret-bearing extra files, empty files or symlink shortcuts.
2. Expected source SHA (optionally supplied), pi-gen pin, workflow
   run ID, manifest schema, image size and SHA-256 digest.
3. Exact single-line checksum and actual compressed-image hash, and
   stream-verified full XZ decompression with a bounded allocation.
4. Explicit preview-only assertions: `hardware_verified=false`,
   `release_approved=false`, `supports_phone_wifi_setup=false`
   and a statement that it is not a release.
5. Inventory hash bound to the preview manifest: exact installed dpkg
   names/versions/architectures, SHA-256 of available Debian copyright files,
   counts of **missing copyright documents**, strict allowed fields and
   `legal_review_approved=false`. Missing notices remain explicit risks.
6. Always outputs `public_release_ready=false`, even when integrity
   passes: source tests and image integrity **cannot constitute**
   owner authorization, legal rights or real hardware approval.

On a trusted engineering workstation with the ZIP already unpacked:

```sh
python3 scripts/release_bundle_audit.py \
  --directory /path/to/extracted-zip \
  --expected-source-sha <exact-40-character-source-commit-from-this-four-file-zip>
```

Use the **SHA from the same new four-file bundle's manifest** above;
prior Draft PR #30 three-file artifacts use a different legacy schema and
cannot pass the current v2/four-file auditor. Replace the placeholder with
the exact reviewed source commit; the placeholder is not literal shell input.

This prints JSON about integrity and unresolved gates. It **does not**
upload files, open network sockets, install devices, change permissions,
create tags, sign images or publish a Release. The image build
workflow runs this as an **additional** quality gate before uploading
its temporary **UNVERIFIED** artifact.

## Separate owner-controlled public Release process (future)

**Mandatory minimum checkpoints before creating a release:**

- [ ] Reviewed, non-draft, legally authorized commit and PR integration
- [ ] Real Raspberry Pi 4 + intended Edifier USB speaker boot and audible
      low-volume playback, Bluetooth pairing/reconnect and USB hotplug
- [ ] Source 1/2/3 acceptance including actual alternate transport
      support, gain clipping, reconnection and failure handling
- [ ] Secure physical ownership claim, first-phone setup, authorized
      UI sessions, Wi-Fi/recovery and security threat-model validation
- [ ] Dependency rootfs SBOM, redistributed code/firmware copyrights,
      source obligations, accurate notices and legal/compliance approval
- [ ] Recovery/long-run tests, accessible five-language UI, upgrade
      and troubleshooting instructions, release notes and warranties
- [ ] Independent provenance, SHA256/XZ, privacy and credential audit
- [ ] Explicit owner/CEO public-release authorization and GitHub
      main protection with reviewed PR / required CI checks

**Only then**, create a new GitHub Release as a draft, attaching the
owner-reviewed `AudioHub-Pi4.img.xz`, `SHA256SUMS.txt`,
third-party notices/corresponding-source information and real
release notes. Review the draft download, exact SHA and provenance
before the **operator** publishes it; mark it prerelease if any
supported feature is still experimental, and do not advertise it as
stable. The `releases/latest` link is appropriate only for an
actually published, non-prerelease Release.

For a future authorized operator, GitHub UI path:
**repository → Releases → Draft a new release → create reviewed version
tag → upload reviewed assets → preview draft → publish**. None of
these actions is automated by a source PR or approval guess.
If workflow automation is later introduced, use an owner-controlled
protected GitHub Environment and minimum explicit token permissions,
revalidate commit/asset digest and prohibit preview-only builds from
tagging a stable release. Do not grant blanket admin access to an AI
app to bypass these gates.

## Funding and official provenance

GitHub's `.github/FUNDING.yml` already contains `ko_fi: RIVANOX`.
To display the standard GitHub **Sponsor** button on the public repo,
the owner may need to enable **Settings → General → Features →
Sponsorships**. The README and AudioHub web preview also include a
clear voluntary Ko-fi support call-to-action and commercial-license
information. Donations are **not required** for use, downloads or
modification of AGPL code, and do not grant a commercial license.

The copyright notice, AGPL license, project branding and
`THIRD_PARTY_NOTICES.md` remain independent from voluntary funding.
RIVANOX controls branding to the extent of applicable law, not the
already-issued AGPL recipient rights. See
[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md) for the
optional separately negotiated paid-license strategy.

**Next technical/human evidence:** attach a real *redacted* Pi4
`AUDIOHUB-TEST-REPORT.json` and audible result in
[Issue #2](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2).
This source development does not perform the device test itself.

## Automated rootfs package and license *evidence*, not license clearance

The next stacked development PR adds `scripts/rootfs_package_inventory.py`
(run inside pi-gen's actual built ARM64 rootfs), which produces deterministic
`ROOTFS-PACKAGES.json`. It exports only installed package name, architecture,
version and an optional SHA256 of an available Debian copyright notice —
**never** post-install scripts, email addresses, local credentials, Wi-Fi, MAC
addresses or device serials. A missing or linked copyright file is recorded
as **missing**, not silently treated as legally compliant. The artifact is
included in the **temporary test ZIP** and SHA-bound to its source/image
provenance manifest. Independent validation rejects extra keys, duplicates,
malformed metadata, symlinked inventory and fabricated legal approval.

This is a **package inventory, NOT a complete SBOM**: pip/vendor libraries,
firmware, kernel blobs, license text interpretation, source-offer obligations,
installed-but-untracked binaries and chain of title still require a separate
human/legal audit. It cannot authorize an official GitHub Release.

## Proposed Model C distribution requirements — NOT EFFECTIVE

RIVANOX has selected a *future* source-available personal-use-free /
paid-commercial-permission model (Model C). A source file's presence in
the public repository does not prove that RIVANOX has the right to
relicense it, nor may a later license withdraw valid AGPL grants.

For any actual future SD release, the human operator must check a
**version-specific license bill of materials**, separate RIVANOX-owned
files from upstream libraries/firmware, ship all third-party notices,
comply with corresponding-source and patent duties, identify the
effective licensor and rights holder, and attach both the actual
license grant and historical-version disclosure to the release.

Existing temporary image artifacts and the public `main` branch
remain AGPL. The [Model C document](../LICENSE-C-DRAFT.md) is **not an
operative agreement** and no commercial customer pricing is set.
The official image publisher stays blocked.

## Failed ARM64 package inventory export and guarded fix (2026-11-05)

[Native run #42092547313](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42092547313)
**FAILED** after 55/55 real rootfs checks; its inventory generator printed
689 installed packages, 631 copyright hashes and 58 unresolved paths, but
`deploy/ROOTFS-PACKAGES.json` was not produced, so the Actions archive
was not uploaded. The new `scripts/export_rootfs_inventory.py` is a
fail-closed bridge from final pi-gen stage work rootfs into deploy,
including stage uniqueness, symlink and schema/digest validation and an
explicit unresolved package-name list for legal triage. Its own tests do
**not** constitute an actual new image. A fresh successful native ARM64
run and **human legal review** are required before describing an image
bundle as available. The Model C source-available license is still only a
proposed future policy, not an operative switch.
