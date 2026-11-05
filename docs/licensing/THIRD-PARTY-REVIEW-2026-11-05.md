# AudioHub third-party code and image distribution — verified observations and open risks

**Date:** 2026-11-05. **Status: PARTIAL TECHNICAL REVIEW — NOT LEGALLY CLEARED.**
**Effective license:** historical/current AGPL-3.0-only.
**Future target:** Model C, not operative until ownership/legal review.

## Precisely inspected source and packages

- The GitHub development checkout based on PR #35 includes Python production
  modules under `src/audiohub`, browser-local `web/app.js` and `web/styles.css`.
  The checked Python application source imports only standard-library modules
  plus `dbus` and `gi` (PyGObject). This **does not prove** original authorship.
- The source-only web UI uses local JavaScript/CSS; no externally hosted JS/CSS
  dependency was identified in the inspected UI source. External Ko-fi and
  RIVANOX destinations are navigation links, not embedded runtime libraries.
- `src/audiohub/network_laptop.py` parses the public five-byte Scream PCM/UDP
  frame and routes raw PCM to `pw-cat`. The repository does **not** include the
  Scream Windows driver or a copied vendor receiver binary in the reviewed
  source tree. **Manual similarity/origin review remains open:** implementing a
  public protocol is not automatically the same as copying upstream code, but
  repository inspection alone cannot certify independent development.
- Runtime audio depends on third-party **executables/services** (PipeWire
  `pw-dump`, `pw-loopback`, `pw-cat`, WirePlumber `wpctl`, BlueZ / DBus),
  even where Python imports are from the standard library.
- `image/stage-audiohub/00-packages/00-packages-nr` installs 15 explicitly
  listed packages; **their transitive dependencies and Raspberry Pi OS base
  are much larger**. Do not confuse a 15-package declaration with complete
  SBOM evidence. `build-image.sh` fetches an exact pinned pi-gen commit,
  which is a build input; it is not by itself evidence that the entire
  pi-gen source is bundled as RIVANOX-owned code.

## Actual native ARM64 evidence — source and compliance not approved

[Build #42092547313](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42092547313),
exact PR #34 SHA `c28a61bea275f8602458c2961e06454430cc4319`,
finished **FAILURE** at `Stage and verify unverified image outside
root-owned builder directory`. The real rootfs packaging audit was
**55/55 checks passed**, and the new build log recorded:

- `installed_packages: 689`
- `copyright_files_available: 631`
- `copyright_files_missing: 58`

This count is **not evidence of 58 license violations**. The inventory
reports null when copyright/doc paths are missing, symlinked or otherwise
unreadable under its conservative checker. Debian Policy permits some
`/usr/share/doc/PACKAGE` **directory** symlinks where packages share a
source, although each `copyright` file itself must not be a symlink.
Each of the 58 unresolved entries must be enumerated from a reviewed
real rootfs inventory, investigated and given a reasoned status.
The build failed with:

```text
cp: cannot stat '.pi-gen-build/pi-gen/deploy/ROOTFS-PACKAGES.json': No such file or directory
```

The build generated the inventory in a rootfs stage but failed to bring
it to the expected deploy path. **No new inventory-inclusive image
artifact exists from that failed run.** PR #34 must correct the export
and run real native ARM64 CI again. A successful **source** CI run does
not prove the image-publishing path works.

## Third-party matrix (upstream evidence is not exact binary license proof)

| Component | Observed source/use | Upstream evidence | Risk before Model C/image release |
| --- | --- | --- | --- |
| Python standard library | AudioHub orchestration, HTTP, CLI | Distributed with Python | Python/package notices in actual image, no claims of code authorship |
| `python3-dbus`, `python3-gi` | Explicit imports in `pairing.py` | Debian packages | Verify exact binary source and Debian copyright files |
| PipeWire | Host audio transport and filters | https://github.com/PipeWire/pipewire/blob/master/LICENSE | Predominantly MIT; upstream exceptions (e.g. SPA ALSA LGPL and JACK GPL-related module) require exact installed binary check |
| WirePlumber | Session policy and Bluetooth role config | https://github.com/PipeWire/wireplumber/blob/master/LICENSE | Upstream MIT; ensure license/copyright notices are preserved |
| BlueZ | Bluetooth stack and CLI/DBus | https://github.com/bluez/bluez | Upstream GPL-2.0 primary repository license; some libraries/components can have distinct licenses; verify exact packages and corresponding source obligations |
| Scream | Third-party PCM UDP protocol referenced by an original-looking test receiver | https://github.com/duncanthrax/scream | Upstream MS-PL and based on Microsoft MSVAD example; no upstream binary claimed bundled; potential source-similarity and patents/terms require manual review |
| pi-gen | Pinned external build system | https://github.com/RPi-Distro/pi-gen | Verify license at pinned commit and source provenance; a build tool's license is not the whole image's license |
| Raspberry Pi OS / Debian | Entire built arm64 OS, 689 dpkg installed packages in failed run | https://www.debian.org/doc/debian-policy/ch-docs.html | 58 copyright-hash unresolved (not automatically violations), transitive copyleft, firmware, kernel, font, other notices and corresponding sources |
| Browser assets | Local `app.js`, `styles.css`; no CDN executable dependency observed | Repository UI files | No full external originality/plagiarism comparison performed |

**Correction to previous notices:** `Flask` is **not a used webserver
dependency** in the inspected `src/audiohub/webserver.py`: it uses
Python's `http.server`. Do not claim it as installed without inventory.

## Controls introduced in source CI

`scripts/source_dependency_audit.py` is a bounded *source-level
observation* check: AST-inspects Python imports, requires existing
AGPL SPDX on checked production files, requires local UI JS/CSS assets,
and rejects new unreviewed Python runtime dependencies, external
executable CSS/JS URLs and symlink-based check bypasses. It reports
`manual_code_origin_review_complete=false`,
`third_party_image_license_review_complete=false`, and
`model_c_relicense_approved=false`.

**Limits:** This is not a byte-wise upstream similarity search, exact
hash-based attribution database, SPDX/SBOM for 689 installed packages,
dependency license analyzer, firmware/source-offer analyzer, or a
lawyer's opinion. It cannot prove the rights of all code were obtained.

## Release and history disposition

- A public AGPL repository is already a form of publication, regardless
  of whether anyone is known to have downloaded a Pi SD image or code.
- Rewriting the git history cannot retract already-granted AGPL rights or
  remove copies in other people's clones, forks, PR refs or GitHub caches.
- With open stacked PRs and CI evidence, force-rewriting or wiping
  commits is a high-risk operation. **No history rewrite, deletion,
  private visibility change, license flip or release was performed**.
- Prefer preserving historical legal/evidence records, fixing inventory
  generation in a separate engineering PR, reviewing rights, then
  explicitly versioning a new eligible Model C release. If the owner
  wants a clean public launch, evaluate a separate new repository and
  private development workflow after a rights audit; this does not
  change the historical AGPL grants.

## Remaining mandatory sign-offs

1. Review a **complete real binary-rootfs package inventory** listing
   each unresolved copyright entry, including proper safe in-root
   resolution of allowed Debian documentation symlinks.
2. Record actual package licenses, GPL/LGPL/AGPL and firmware
   corresponding-source obligations and their fulfillment.
3. Independently compare suspect imported snippets and the Scream
   implementation to upstream sources; prove origin/contributor rights
   and verify commercial relicense permissions.
4. Have qualified DE/EU counsel assess Model C terms and compatibility
   with the precise software combination; obtain owner approval only
   after the source and binary facts are confirmed.
5. Fix PR #34 image export and achieve fresh successful native ARM64
   artifact integrity + a separate physical Pi4/Edifier acceptance.

## 2026-11-05 follow-up: safe Debian shared-documentation aliases

The real **subsequent** ARM64 [run 42098223599](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42098223599) for draft PR #36
**SUCCEEDED** with 302/302 Python tests, 55/55 real rootfs checks,
verified image/checksums, manifest schema v2 and temporary
[UNVERIFIED artifact #13447794801](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42098223599/artifacts/13447794801).
As before, the inventory recorded **689 packages / 631 available hashes /
58 unresolved copyright paths**. A failed older run is retained above
only as historical debugging evidence; its defect was corrected.

The 58 unresolved entries, now captured by exact-name native build logs,
are primarily package families for GCC/binutils, kernel/headers,
console/debconf, Python support and utilities (full itemization is
available in [PR #36 comment](https://github.com/RIVANOXcom/rivanox-audiohub/pull/36)
and the successful ARM64 build log). No conclusion is drawn that any
of these packages lack copyright, are unlicensed or are lawful to distribute.

**New narrow engineering attempt (not yet accepted for exact native image):**
the `_copyright_hash` routine in `scripts/rootfs_package_inventory.py`
now accepts *only* a single, direct, same-directory package-name
symlink (e.g. `/usr/share/doc/a -> b` if `b` is a real directory)
and verifies a real non-symlinked regular `copyright` file using
directory-fd-relative `O_NOFOLLOW` opens. It refuses parent/absolute
paths, multi-step symlinks, out-of-root links, oversized files and
symlinked copyright files. This is deliberately narrower than all
filesystem symlinks Debian may legally support.

**Important:** A newly discovered hash only means a file was located,
not that its licensing terms have been read, complied with or approved
for commercial redistribution. The full Pi rootfs image and source
provenance require human/legal review. New native ARM64 evidence for
this modified extractor must be verified at its exact source SHA,
not inferred from the earlier successful artifact.

## 2026-11-05 native copyright-file audit: 49 more verified paths, 9 remaining

At exact previous draft PR #38 source `d0645965ae98082c3c3bdf5568938857df18c658`,
[native ARM64 image run 42100728004](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42100728004)
finished **SUCCESS**, with 312 Python source tests, 55/55 actual Pi rootfs
guards and a checksum/XZ/provenance-verified **UNVERIFIED** temporary
[4-file archive #13448859215](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42100728004/artifacts/13448859215)
(expiry 2026-12-05). Rootfs inventory from the final built image:

- **689 installed dpkg packages** (same as before)
- **680 captured copyright-file hashes** (49 more than previously)
- **9 unresolved file paths**, not automatically license violations

**The exact nine unverified package paths** from rootfs export logs:

| Package | Follow-up concern |
| --- | --- |
| `binutils-aarch64-linux-gnu` | Compiler/binutils multiarch copyright/path and source mapping |
| `libctf0` | Binutils shared-library documentation and source mapping |
| `libgprofng0` | Binutils gprofng shared-library documentation and source mapping |
| `libpython3.13` | Python runtime package copyright/path and source mapping |
| `linux-headers-rpi-2712` | Raspberry Pi kernel header metapackage license notices |
| `linux-headers-rpi-v8` | Raspberry Pi kernel header metapackage license notices |
| `linux-image-rpi-2712` | Raspberry Pi kernel metapackage notices and corresponding source |
| `linux-image-rpi-v8` | Raspberry Pi kernel metapackage notices and corresponding source |
| `raspberrypi-net-mods` | Raspberry Pi network package copyright/firmware provenance |

**Caution:** The present ten-column summary is an investigation queue, not
a claim that any particular actual package has a missing license grant,
that a binary is illegally distributed, or that upstream versions have
been individually reviewed. Exact paths and package versions must be
matched to the actual image, which was a temporary CI artifact.

Debian Policy 12.3/12.5 permits same-source documentation directory links
only when the first binary package directly depends on the target package.
Merely accepting a safe single-hop path does **not** prove these semantic
conditions. [Debian Policy §§12.3,12.5](https://www.debian.org/doc/debian-policy/ch-docs.html).

**Next technical change in PR #39:** `scripts/rootfs_copyright_triage.py`
checks the real dpkg status `Source` and `Depends` metadata for every
captured same-directory doc alias, detects potential source mismatches,
classifies each of the nine remaining null hashes by specific fixed
reason codes, and verifies that each recorded hash matches actual
rootfs bytes. This extra evidence goes only to controlled **CI logs**,
not into the public image/4-file preview ZIP. All apparent matches
remain subject to independent legal/compliance review and do not
convert `legal_review_approved=false` into true.

Future Model C licensing remains **NOT EFFECTIVE**; no public stable
release, historical commit rewriting or publication authorization.
