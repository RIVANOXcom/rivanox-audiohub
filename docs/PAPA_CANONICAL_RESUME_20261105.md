# PAPA — RIVANOX AudioHub canonical resume and evidence handoff

**Captured:** 2026-11-05 (Europe/Berlin).  
**Authority:** current GitHub state and linked exact GitHub Actions runs; do NOT substitute prior chat assumptions.  
**Project:** `RIVANOXcom/rivanox-audiohub`, PAPA Workbench `PJ2611-0001:R001`.  
**Status:** development ALPHA; previous AGPL source publicly visible; future Model C **not effective**; public stable SD image **NOT authorized**.

> **Chat-change instructions:** Read this file first, then verify current GitHub PR HEADs, CI/artifact availability, branch visibility and PAPA workbench evidence. Work only from a specifically checked exact SHA. Do not resume by force-pushing, rewriting history, mixing parallel branches or assuming all tasks already completed. See the copy/paste recovery prompt near the end.

## A. Owner's binding product/business decisions

1. **Continue real technical development.** Demonstrate meaningful code changes, tests and native ARM64 image evidence rather than producing plans only. Keep the Pi 4 + Edifier R600USB audio appliance goal and usability in view.
2. **Future license preference is Model C:** RIVANOX-owned and independently relicensable NEW source is proposed to be source-available, with personal/noncommercial use free and commercial/organizational uses requiring a separately negotiated paid license. The draft is at [LICENSE-C-DRAFT.md](../LICENSE-C-DRAFT.md) and [rights audit](licensing/RIGHTS-AUDIT-2026-11-05.md). It is **not legally operative**; fees, licensor identity, contributor assignments and legal review are open.
3. **Historical AGPL remains legally applicable:** `main/LICENSE` remains **GNU AGPL-3.0-only**. Old legitimate AGPL recipients already may use it commercially subject to AGPL terms; rewriting commits does NOT revoke those rights. A public source repository need not have a functional executable or official SD image to be a public source publication. No one can reliably prove nobody has downloaded it.
4. **Future Model C product features must be developed in a separate PRIVATE repo**, not quietly added under the public AGPL tree. The recommended empty repo is `RIVANOXcom/rivanox-audiohub-next`. On this handoff, the connected GitHub app returned **404** for that name; private repo creation or access is **NOT CONFIRMED**. [Owner issue #37](https://github.com/RIVANOXcom/rivanox-audiohub/issues/37) lists owner steps. GitHub app currently has no repo-create/visibility-change action; do not claim private setup or initiate dangerous main/history changes. Also do not bulk-copy historical code into new proprietary rights without file-by-file provenance/rights review.
5. Public repo may stay readable/downloadable with only owner-authorized accounts able to modify upstream branches; public forks and PR proposals are not the same as upstream write permission. Donations/Ko-fi remain voluntary and cannot condition existing AGPL rights.
6. No official GitHub Releases or approved stable SD images exist as of this checkpoint. Experimental Actions artifacts DO exist, with explicit **UNVERIFIED/DO-NOT-DISTRIBUTE** labels; do not claim the source or binary has never been accessible to anyone. `.github/workflows/publish-image.yml` deliberately blocks publication.

## B. Software architecture and what remains unverified

- Target: Raspberry Pi 4 audio hub with USB playback to Edifier R600USB; sources include Bluetooth audio and a separately **manual opt-in** Windows Scream-compatible UDP PCM proof-of-concept.
- RIVANOX Python modules in `src/audiohub/` implement Bluetooth DBus/BlueZ pairing experiments, PipeWire/WirePlumber device discovery and routing, per-source EQ/mixer, three virtual audio channels, USB-only audio gate, local offline input naming, first-boot diagnostics and restricted status web service. `web/` contains local JS/CSS/HTML and five locale JSON files (EN, DE, ES, FR, IT).
- Key modules: `pairing.py` experimental BlueZ NoInputNoOutput owner-unverified initial window; `runtime.py` PipeWire supervision and fail-closed USB route; `mixer.py` gain/EQ model; `network_laptop.py` explicitly `--unsafe-lan-test`-gated unauthenticated UDP receiver; `webserver.py` Python `http.server` read-only status, **NOT Flask**; `firstboot_diag.py` offline privacy-bounded reporting. UI controls may be prototype-only: never claim all are wired to physical hardware.
- Build: pinned Raspberry Pi pi-gen source fetched by `build-image.sh`; `image/stage-audiohub/` installs third-party Debian/Pi OS packages including PipeWire, WirePlumber, BlueZ, kernel, firmware, DBus/PyGObject and system dependencies. Main app source imports primarily Python standard library plus `dbus`/`gi`. Software tool dependencies and their licenses are independent of RIVANOX's future license.
- **Not completed:** independent physical Pi4/Edifier audible playback, real three-input mixing and gain validation, secure owner claiming/re-pairing, genuine Windows sender authentication, stable on-device upgrade/user experience, complete image SBOM/firmware/patent/legal/source obligations, all supplier rights and tested consumer installation. Do not flash an experimental image on a trusted production network or call it sale-ready.

## C. Exact GitHub authority and stacked PR chain

**PUBLIC repo:** https://github.com/RIVANOXcom/rivanox-audiohub  
**Default branch:** `main`; verified snapshot at `84303e22b14da9e876ec6288af376671fd9898a9` (verify again on resume). `main` was not force-pushed or merged by the work below. Repo visibility **public**, zero official GitHub Releases at checkpoint.

The following are **open DRAFT stacked PRs**; do not merge to main without explicit owner review and verified branch dependencies:

| PR | Base -> topic branch | Exact checked HEAD | Delivered engineering |
| --- | --- | --- | --- |
| [#34](https://github.com/RIVANOXcom/rivanox-audiohub/pull/34) | earlier source branch -> `wd-papa-20261105-rootfs-license-inventory` | `c28a61bea275f8602458c2961e06454430cc4319` | Initial actual-rootfs package inventory; original ARM64 pipeline export failed |
| [#35](https://github.com/RIVANOXcom/rivanox-audiohub/pull/35) | #34 -> `wd-papa-20261105-model-c-licensing-transition` | `4a546690cddb09a8366dffac1ef864e6ea32774c` | Future Model C DRAFT terms, fail-closed legal readiness flags, rights audit and source dependency checks |
| [#36](https://github.com/RIVANOXcom/rivanox-audiohub/pull/36) | #35 -> `wd-papa-20261105-legal-inventory-export-fix` | `a5d11cc6a071baa11520dd9bd41f601520a9af64` | Fixed actual pi-gen rootfs inventory export into the 4-file preview ZIP |
| [#38](https://github.com/RIVANOXcom/rivanox-audiohub/pull/38) | #36 -> `wd-papa-20261105-rootfs-copyright-links` | `d0645965ae98082c3c3bdf5568938857df18c658` | Safe one-hop Debian shared-doc directory resolution, improved 631 -> 680 hashes |
| [#39](https://github.com/RIVANOXcom/rivanox-audiohub/pull/39) | #38 -> `wd-papa-20261105-copyright-triage-and-doc-alias-policy` | `065506961fad34448e75f513d39db684f65c7cd7` | Classified the 9 outstanding paths; matched dpkg Source and Depends for 49 resolved links |
| [#41](https://github.com/RIVANOXcom/rivanox-audiohub/pull/41) | #39 -> `wd-papa-20261105-dpkg-identity-reconciliation` | `5eae1104469a1585db8368e1bef00b5de204fb68` | Exact installed name/arch/version reconciliation, bounded multihop notice trace and 12 more adversarial tests |
| [#42](https://github.com/RIVANOXcom/rivanox-audiohub/pull/42) | #41 -> `wd-papa-20261105-canonical-resume-source-rights` | **Resolve branch HEAD live; this document is updated in the PR itself** | File-by-file rights ledger and this canonical recovery handoff |

**Latest source-rights/handoff CI (historical exact SHA):** [GitHub Actions run 42108997052](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42108997052) **SUCCESS** at `469dbb913deedfcb65c857bcee3903f40fe149cf`, **354 Python tests** including the 79-file rights-ledger and handoff regression checks; no new native image test is claimed for documentation-only PR #42. Any subsequent commit needs its own fresh CI run.

**Do not mix branches.** PRs #35/#36/#38/#39/#41 use parent-branch bases intentionally; the current checkpoint PR must target the #41 branch rather than `main`.

## D. Exact source CI and native ARM64 evidence (all historical SHA-bound)

| Topic | GitHub Actions run | Outcome / evidence |
| --- | --- | --- |
| PR #35 source/Model C guard | [42095313848](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42095313848) | **SUCCESS, 283 Python tests** on commit `c37fb7585ec883c31b7694b6bb4945f701cfcb7d` |
| PR #35 later source dependency audit | [42096290577](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42096290577) | **SUCCESS, 291 tests** at `4a546690cddb09a8366dffac1ef864e6ea32774c` |
| PR #36 source | [42098261940](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42098261940) | **SUCCESS, 302 tests** |
| PR #36 native ARM64 | [42098223599](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42098223599) | **SUCCESS, real 55/55 rootfs checks**, 689 dpkg/631 copyright hashes/58 unresolved; strict XZ, SHA256, 4-file manifest; artifact [13447794801](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42098223599/artifacts/13447794801) |
| PR #38 source | [42100769988](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42100769988) | **SUCCESS, 312 tests** |
| PR #38 native ARM64 | [42100728004](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42100728004) | **SUCCESS, real 55/55 rootfs checks**, 689/680/9, artifact [13448859215](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42100728004/artifacts/13448859215) |
| PR #39 source | [42105123054](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42105123054) | **SUCCESS, 324 tests** |
| PR #39 native ARM64 | [42105112961](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42105112961) | **SUCCESS, 55/55 rootfs checks**, 689/680/9; classified 8 multihop/1 missing; artifact [13452656211](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42105112961/artifacts/13452656211) |
| PR #41 source | [42106847455](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42106847455) | **SUCCESS, 336 tests** at `5eae1104469a1585db8368e1bef00b5de204fb68` |
| PR #41 native ARM64 | [42106833667](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42106833667) | **SUCCESS**, 336 Python tests, 55/55 actual rootfs checks, 4-file ZIP artifact [13453052359](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42106833667/artifacts/13453052359), expires **2026-12-05**. 689 packages, 680 hashes and 9 unresolved. No legal/hardware approval. |

Historical failed build: [42092547313](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42092547313) lacked `deploy/ROOTFS-PACKAGES.json` despite having generated it in the Pi rootfs; this was fixed and independently validated by PR #36. **Never** treat the old failure as the latest status.

Temporary ZIPs are **UNVERIFIED, NOT public GitHub Releases**. The four files are one `.img.xz`, `SHA256SUMS.txt`, `PREVIEW-MANIFEST.json` and `ROOTFS-PACKAGES.json`. In the native validator `public_release_ready=false`, `legal_review_approved=false`, and no physical test is claimed. GitHub Actions artifact expiry/access can change; always verify live.

## E. Current exact third-party legal and packaging evidence

At PR #41 native build run 42106833667:

- `installed_packages=689`; architectures **538 arm64 + 151 all**.
- `copyright_files_available=680`; `copyright_files_missing=9`.
- **49 one-hop shared `/usr/share/doc` directory aliases** were resolved safely and independently classified by installed dpkg `Source` and direct `Depends`; `49 same_source_and_direct_dependency_declared`, **0 mismatches found**. This is a technical metadata result only, not a legal signoff.
- Eight unresolved paths are **two-hop links**. Their exact safe no-follow trace is below; both observed hops match Source/Depends in the installed dpkg status, but the conservative inventory does not hash these multi-hop notices automatically:

| Package with unresolved hash | Real bounded link chain |
| --- | --- |
| `binutils-aarch64-linux-gnu` | `binutils-aarch64-linux-gnu -> libbinutils -> binutils-common` |
| `libctf0` | `libctf0 -> libbinutils -> binutils-common` |
| `libgprofng0` | `libgprofng0 -> libbinutils -> binutils-common` |
| `libpython3.13` | `libpython3.13 -> libpython3.13-stdlib -> libpython3.13-minimal` |
| `linux-headers-rpi-2712` | `linux-headers-rpi-2712 -> linux-base-rpi-2712 -> linux-base-6.18.60+rpt-rpi-2712` |
| `linux-headers-rpi-v8` | `linux-headers-rpi-v8 -> linux-base-rpi-v8 -> linux-base-6.18.60+rpt-rpi-v8` |
| `linux-image-rpi-2712` | `linux-image-rpi-2712 -> linux-base-rpi-2712 -> linux-base-6.18.60+rpt-rpi-2712` |
| `linux-image-rpi-v8` | `linux-image-rpi-v8 -> linux-base-rpi-v8 -> linux-base-6.18.60+rpt-rpi-v8` |

- One actual `copyright_file_missing` path: **`raspberrypi-net-mods`**. The [official upstream issue #14](https://github.com/RPi-Distro/raspberrypi-net-mods/issues/14) requests a `LICENSE`/`debian/copyright` file and was OPEN when checked. It is a **specific unresolved distribution-rights and notice question**, not proof of infringement or a reason to invent an upstream license.
- Debian Policy §§12.3/12.5: https://www.debian.org/doc/debian-policy/ch-docs.html . Installed binary package license *texts*, complete transitive source code/firmware and corresponding-source obligations, patents, trademarks, provenance and publisher rights still require qualified review.
- Upstream components include PipeWire, WirePlumber, BlueZ, Raspberry Pi OS/kernel/firmware, pi-gen, Python, DBus, PyGObject, and publicly specified Scream protocol (upstream MS-PL project). **No Scream Windows driver binary was identified as bundled in inspected AudioHub application source.** A complete similarity/plagiarism check has NOT been done.

**Do not change all 9 nulls to 'legally approved' merely because 8 link chains end at documented directories.** Presence and checksums alone cannot prove commercial redistribution rights. [Issue #40](https://github.com/RIVANOXcom/rivanox-audiohub/issues/40) tracks the legal work.

## F. Source-level chain-of-title and future Model C protections

Legal drafting on [PR #35](https://github.com/RIVANOXcom/rivanox-audiohub/pull/35):
- `LICENSE-C-DRAFT.md` = **DRAFT/NOT EFFECTIVE**.
- `docs/licensing/RIGHTS-AUDIT-2026-11-05.md` documents old AGPL rights, authorship, contributors, AI-assisted code and third-party obligations.
- `docs/licensing/TRANSITION-STATE.json` holds fail-closed future-version, owner, legal and rights flags; `license_switch_effective=false`.
- `scripts/license_transition_audit.py` prevents an unreviewed effective license switch, false legal approval or accidental release permission.
- `scripts/source_dependency_audit.py` checks the bounded source-only Python imports (stdlib plus `dbus`/`gi`) and local web runtime assets, **not a complete software composition analysis**.
- In this checkpoint PR, `docs/licensing/SOURCE-RIGHTS-LEDGER.json` enumerates **79 checked-in application, web, image stage, scripts, tests, CI and build-source files**, all with **human rights-holder verification, third-party source checks, Model C eligibility and authorizations set to false**. `scripts/source_rights_ledger.py` + CI tests refuse newly added/unaccounted files or fabricated approvals; adding a record is **NOT** clearance. Code generation with ChatGPT does NOT automatically guarantee exclusive human copyright in Germany or eliminate third-party rights.

**Existing AGPL source is not converted by setting a new header.** Future Model C eligibility is assessed per work/file and separate release, ideally in a new private repo after owner action and qualified legal counsel.

## G. Next tasks in strict practical order

**P0 — legal source rights:** [Issue #32](https://github.com/RIVANOXcom/rivanox-audiohub/issues/32) tracks Model C rightsholder, source-origin, AI/contributor rights, counsel-reviewed terms and explicit effective-version owner acceptance. Draft legal terms are NOT a license switch.

**P0 — owner action / separate future proprietary development:** [Issue #37](https://github.com/RIVANOXcom/rivanox-audiohub/issues/37): owner must create an **empty PRIVATE** repo, verify scope of connected app and authorize access. Do **not** use a public fork, assume the new repo exists or grant admin access without authorization. When verified, do a reviewed rights-only import, then write genuinely new Model C product code there.

**P0 — shipping rights:** [Issue #40](https://github.com/RIVANOXcom/rivanox-audiohub/issues/40): get explicit license and exact source/notice for `raspberrypi-net-mods`, review eight multi-hop notice rights, exact binary package version notices, kernel/firmware/copyleft obligations, any Scream code similarities, AI/contributor/employment rights. This is not solvable by deleting AGPL history.

**P0 — real hardware and secure ownership:** [Issue #2](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2) tracks real Pi4/Edifier R600USB device acceptance; physically test Pi4+Edifier audible audio, Bluetooth pairing, multi-input routing and EQ, USB unplug/recovery, local UI and owner authentication. No existing source-only or CI test proves those.

**P1 — preserve public legacy and build evidence:** ensure parent PRs and this checkpoint remain DRAFT, inspect CI and artifacts at exact SHAs, update English source docs/decision log as findings become concrete, keep `publish-image.yml` hard-failed and README/FUNDING truthful. Address actual new CI defects, not imagined ones.

**P1 — final commercial license rollout:** only with verified legal entity/rightsholder, versioned source tree and license legal review DE/EU, upstream notices/source offers, explicit owner authorization and private repo setup. Publish a fresh separately identified license-aware version; preserve old valid AGPL permissions.

## H. Workbench and handoff record

Authoritative project workbench: PAPA `PJ2611-0001:R001`. Prior evidence IDs for this chain: **#2779** (Model C draft), **#2781** (source/third-party review), **#2782** (export fix), **#2784** (real Pi image pass), **#2785** (Debian aliases), **#2787/#2788** (9-gap and upstream license), **#2790** (exact 9 classification), **#2791** (dpkg identity branch). This checkpoint should add a new Workbench evidence with the **exact new PR URL, source CI run and this canonical file**; use the live Workbench context on next chat.

Key source docs: [rights audit](licensing/RIGHTS-AUDIT-2026-11-05.md), [source third-party review](licensing/THIRD-PARTY-REVIEW-2026-11-05.md), [private development separation](licensing/MODEL-C-PRIVATE-DEVELOPMENT.md), [distribution policy](RELEASE-DISTRIBUTION.md), [owner decisions](DECISION-LOG.md), [legacy handoff](PROJECT-HANDOFF.md), [source rights ledger](licensing/SOURCE-RIGHTS-LEDGER.json).

## I. What to verify immediately after a chat switch

1. Open `https://github.com/RIVANOXcom/rivanox-audiohub/pulls`, confirm exact HEAD/base for PRs #35/#36/#38/#39/#41 and this handoff PR. New commits may have appeared since this document; NEVER assume recorded SHA is current.
2. Open GitHub Actions for active PR, verify **source** CI and independent **native ARM64** runs; confirm failure/success, exact source SHA, 55 rootfs checks, four-file ZIP and public-release gate. Artifacts are expiring.
3. Check `main/LICENSE` and `docs/licensing/TRANSITION-STATE.json`; avoid declaring Model C active when flags false.
4. Inspect issues #37 and #40 and latest upstream raspberrypi-net-mods#14; don't reimplement tasks already merged or resolved by other work.
5. Read Workbench project context and add progress evidence. Do not overwrite parallel engineering branches, change default branch/visibility/permissions, delete old commits, publish stable binaries or fill in legal approval flags without independent evidence.

**Source CI baseline commands** on a checked out full clone (commands are examples, not claims that they ran in this chat):
```bash
python3 scripts/license_transition_audit.py
python3 scripts/source_dependency_audit.py
python3 scripts/source_rights_ledger.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q src
node --check web/app.js
bash -n build-image.sh
```

**Reference exact CI and artifact safety before writing a release:** source tests are not sound on a physical speaker; an experimental image is not a stable product; a hash inventory is not legal clearance.

### Copy/paste prompt for the next ChatGPT conversation

```text
PAPA / RIVANOX AUDIOHUB WEITER — CANONICAL RESUME
Read first:
https://github.com/RIVANOXcom/rivanox-audiohub/blob/wd-papa-20261105-canonical-resume-source-rights/docs/PAPA_CANONICAL_RESUME_20261105.md
Project PAPA Workbench: PJ2611-0001:R001.
Verify LIVE repo, current PR HEADs/CI and issue status before any changes.
The public main and historical source remain AGPL-3.0-only; Model C
personal-free/commercial-paid is a future NOT-EFFECTIVE draft.
Continue evidence-backed engineering and code/license verification
on the correct isolated branch; do NOT rewrite AGPL history, merge
stacked PRs blindly, publish a release, or claim hardware/legal
clearance. New proprietary product features require a separate
owner-created PRIVATE repo (issue #37). Upstream Pi third-party
copyright review is tracked in issue #40.
Save exact commits, CI proof, decisions and detailed new handoff
updates to GitHub and PAPA Workbench for future chat switches.
```

**END OF HANDOFF.** If a live run/PR contradicts this document, treat
the live GitHub evidence as authoritative, reconcile and update this file.
