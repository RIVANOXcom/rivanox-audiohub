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
https://github.com/RIVANOXcom/rivanox-audiohub/blob/wd-papa-20261106-private-status-file-identity/docs/PAPA_CANONICAL_RESUME_20261105.md
Project PAPA Workbench: PJ2611-0001:R001.
Verify LIVE repo, PR #46/#45/#44 stacked heads, exact source and ARM64 CI, and open issues before changing anything.
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


## J. Next verified engineering branch after canonical PR #42: web file safety

**Branch (child of #42):** `wd-papa-20261105-readonly-web-file-hardening`.
**Base exact commit:** `76dc6a0900126bb41b4b691bd4782c4553eea4b0`.
**Change scope:** existing AGPL alpha web security *maintenance only*;
no new commercial-only Model C feature, no public main merge.

**Root cause:** the original read-only `src/audiohub/webserver.py`
selected allowlisted URLs but used `(WEBROOT / filename).read_bytes()`.
If the installed web tree or selected file were a symlink, the service
could read outside the intended static asset tree, and could consume
unbounded memory or block on special files. The status endpoint used
the same unbounded legacy `runtime.read_json(STATE, {})` path.

**Implementation:** `_bounded_regular_bytes()` opens every absolute
path component relative to a previously opened directory fd using
`O_NOFOLLOW|O_DIRECTORY`, opens the last component using
`O_NOFOLLOW|O_NONBLOCK`, requires a nonempty regular file, rejects a
path traversal, and caps static files at 512 KiB and redacted state JSON
at 32 KiB. It rejects incomplete/growing reads. Status unavailable,
oversized, malformed or linked is reported as **stale** with
non-sensitive zero counts; unsupported static files produce 503.
No new HTTP mutation endpoints or LAN autostart flags are added.

**Native packaging guard:** `scripts/audit_rootfs.py` verifies actual
installed web assets are nonlinked regular files and below the static
limit, checks all web tree intermediate dirs and requires the installed
webserver source to include nofollow/bounded status controls.
`tests/test_web_status.py` and `tests/test_rootfs_audit.py` contain
15 + 6 new adversarial/security tests.

**Verification:** [Draft PR #43](https://github.com/RIVANOXcom/rivanox-audiohub/pull/43), exact code SHA `d4fb934ad4ed15cac20a79799d475b2956b94769` [source CI #42111311812](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42111311812) **SUCCESS, 375/375 Python tests**, including 15 live-GET-dispatch/file and 6 rootfs safety tests. Native ARM64 run [#42111297565](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42111297565) started for that exact SHA; verify final result, web safety guard count, archive and release NO-GO before claiming native success. **Validation status:** use LIVE GitHub Actions for this child branch.
No earlier PR #41/#42 source/native run proves the new code works.
Explicitly distinguish source regression CI from native ARM64 Pi
image build, which remains UNVERIFIED without real sound and secure
device-owner testing. Maintain `SOURCE-RIGHTS-LEDGER.json` with all
79 listed files, no false change of legal approval. Re-read the newer
PR and its CI before saying this fix is complete.

**Critical boundaries remain:** current AGPL recipient rights unchanged;
future Model C license NOT EFFECTIVE; no private Model C repo verified
(issue #37), no public Release, no hardware acceptance (issue #2), no
qualified legal approval (issue #32); the upstream Raspberry Pi net-mods
copyright/permission issue remains unresolved (#40).


## K. Additional runtime state safety development — stacked Draft PR #44

**Next child:** [Draft PR #44](https://github.com/RIVANOXcom/rivanox-audiohub/pull/44) on branch `wd-papa-20261105-runtime-state-atomic-security`, based on PR #43 exact baseline SHA
`9e92d95a539a6a8e54a2b433b0a6d9bcaf4fa975`.

**Parent PR #43 native evidence now VERIFIED:** [ARM64 run #42111542474](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42111542474) **SUCCESS**, source 375/375 Python tests, **57/57 actual Pi rootfs guards**, actual built OS package count 689, 680 copyright hashes and nine unresolved (eight linked doc chains + `raspberrypi-net-mods` absent expected file); strict XZ/SHA/provenance/bundle gate passed. Temporary non-release UNVERIFIED [artifact #13454668013](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42111542474/artifacts/13454668013), expires 2026-12-05. The public release-ready flag remains FALSE.

**New verified-in-source defect addressed, NOT YET verified on native Pi image for PR #44:** `src/audiohub/runtime.py` previously used unbounded `Path.read_text()` for private settings, assignments and runtime JSON, and wrote with fixed-name `path.with_suffix(".tmp")`, `open("w")` following symlinks. Since local user-owned storage can contain altered symlinks or raceable files, this could read or overwrite unintended local files or consume excess memory. This is *local state security maintenance* of existing AGPL software, NOT a new Model C-only product feature.

**Implementation:** `_private_parent_fd` traverses absolute path components using directory FDs and `O_NOFOLLOW`, requires private (no group/other) and correct owner for last directory; creates missing paths with restrictive permissions; `read_json` only opens nonlinked, regular, owner-only file with exactly one hard link, nonblocking and at most 32KiB; invalid values safely fall back. `atomic_json` serializes before writing, checks max 32KiB, rejects bad existing destinations, uses random `secrets.token_hex(12)` `O_CREAT|O_EXCL|O_NOFOLLOW` temp file and explicit mode 0600, `fsync` file and parent directory, `os.replace` atomically, and cleans up any leftover temporary file.

**Source tests:** adds 17 adverse tests in `tests/test_runtime_recovery.py` for normal roundtrip, strict permissions, missing directories, symlinked ancestor/destination, stale predictable .tmp symlink, FIFO, hardlinks, untrusted modes, oversized/corrupt/wrong-type/NaN JSON and atomic replacements. `scripts/audit_rootfs.py` adds native package guard `runtime_private_state_nofollow_atomic` and 3 synthetic rootfs tests in `tests/test_rootfs_audit.py`. Expected actual Pi rootfs guard count rises from **57 to 58** if implemented and verified.

**State at handoff writing:** Draft PR #44 created; precise CI and native ARM64 **NOT YET CONFIRMED**. Check current HEAD and source Actions runs, then run full native ARM64 on exact final SHA; do not state success until both finish. Update Workbench, PR comments and this runbook with observed outcomes, failures and SHA. Neither a source CI PASS nor a Pi image guard count proves physical audio/ownership security or legal rights.

**Unchanged legal boundary:** `main` and recipients' AGPL-3.0-only rights remain; future Model C NOT EFFECTIVE, private owner repo `rivanox-audiohub-next` not accessible/verified, legal issue #32, rights issue #40, device test issue #2 and owner setup issue #37 remain OPEN. No merge to `main`, no release, no history rewrite.


## L. Follow-up Draft PR #45: fail-closed supervisor audio route shutdown

[Draft PR #45](https://github.com/RIVANOXcom/rivanox-audiohub/pull/45)
`wd-papa-20261105-supervisor-error-route-cleanup` is stacked on
[Draft PR #44](https://github.com/RIVANOXcom/rivanox-audiohub/pull/44),
whose exact source CI [run #42120108827](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42120108827)
passed **395/395 Python tests** at SHA
`ea661f155a375238b79e44e01c48acf98a21b755`.
The PR44 independent native ARM64 run is
[42120100453](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42120100453);
**check its live final status** before asserting image 58/58 guard success.

**Concrete issue in historical alpha runtime:** `Supervisor.serve()` caught
every exception from `poll()` with a bare `pass`; previously spawned
`pw-loopback` child processes were not necessarily stopped after a failure
such as an unsafe/unwritable runtime status destination or malformed
local state. That could leave an unsupervised managed audio path running.

**Engineering change:** `_stop_all_managed_routes()` terminates each
managed process with the existing bounded wait + forced kill fallback,
clears retry tracking and refuses to swallow cleanup failure. The new
`poll_safely()` uses this on unexpected errors; `serve()` additionally
stops routes on service-loop shutdown. If cleanup itself fails, the
exception must propagate so systemd restarts and terminates the service
**control group**. `audiohub-runtime.service` now explicitly sets
`KillMode=control-group` and `TimeoutStopSec=8s`, retaining
`NoNewPrivileges=yes` and `Restart=always`.

**New tests:** 9 behavioral tests in `tests/test_runtime_recovery.py`,
3 rootfs guard tests in `tests/test_rootfs_audit.py`, and one
systemd-static test in `tests/test_runtime_static.py`. Rootfs
`unexpected_runtime_failure_stops_all_audio_routes` guard should
increment **58 to 59 checks** only when native ARM64 build has
actually passed. All tests must run on the exact PR45 SHA.

**Current PR45 acceptance state:** Draft and not merged; source CI
and native ARM64 must be observed independently. The old
AGPL-3.0-only grants remain valid, Model C future license NOT EFFECTIVE,
new private development repo not verified, nine third-party
copyright paths (including raspberrypi-net-mods) still need legal
review, and Pi4 + Edifier audible/hardware acceptance is open.



## M. 2026-11-05 follow-up: BlueZ automatic trust authorization gate (Draft PR #46)

**Parent [PR #45](https://github.com/RIVANOXcom/rivanox-audiohub/pull/45) COMPLETED CI:** exact SHA \`7ef7a107199a0b6cbf69f1c0b7d047b1feac5bf1\`, source [#42121266631](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42121266631) **SUCCESS 408/408**, native ARM64 [#42121261961](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42121261961) **SUCCESS 59/59** actual rootfs checks. Four-file preview [artifact #13459367136](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42121261961/artifacts/13459367136), **UNVERIFIED, DO NOT DISTRIBUTE**, expires **2026-12-05T22:32:25Z**. 689 installed packages / 680 copyright file hashes / 9 unresolved notice paths; public_release_ready=false. These are CI observations, not Pi4 speaker, ownership or legal acceptance.

**New DRAFT [PR #46](https://github.com/RIVANOXcom/rivanox-audiohub/pull/46)** on \`wd-papa-20261105-bluetooth-trust-authorization-gate\` (base PR45 branch), original audited implementation SHA \`f194b7740670c8549599844f5947edb4b1353bb4\`. On that SHA [source CI #42124595480](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42124595480) **SUCCESS 434/434 Python tests**, 79 existing source files included in pending-human-review rights ledger, all future Model C rights approvals FALSE. Note: the handoff document update itself changes PR46 HEAD and requires checking the NEW exact source CI. Native image [#42124587921](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42124587921) was running for the prior code SHA when documented; later commits can cancel and restart due per-branch concurrency. **Never state native PR46 success until the exact final run is checked.**

**Real legacy security defect:** BlueZ \`PairingAgent.changed()\` used to set \`org.bluez.Device1.Trusted=True\` whenever *any* \`Paired\` property change was observed; a previous RequestAuthorization or RequestConfirmation was **not checked**. \`AuthorizeService\` also accepted an untrusted client merely because boot-time discovery was temporarily open. These are unsafe even though initial pairing was limited to 600 seconds and two devices.

**Change:** an in-memory, per-device, one-use pending authorization is recorded only after real BlueZ agent callbacks. Requests require a strict local BlueZ path, expire after 45 seconds or the remaining boot-time window, and max 2 simultaneous requests. Actual \`org.bluez\` signal origin and real Device1.Paired state are checked before granting Trusted; a newly paired device must have an unexpired matching authorization. Unsolicited or stale signals consume no trust. New untrusted services require an authorized pending device; previously trusted devices can still reconnect normally after boot window. Errors reading BlueZ pairing counts deny new pairing rather than reopen discoverability. Agent Release discards pending authorization and closes discovery. **No MAC/peer identities are exported into logs or image artifacts.**

**Validation:** \`tests/test_pairing_static.py\` now runs the production pure authorization helper and genuine agent methods with DBus registration decorators substituted by local stubs (Raspberry Pi-only dbus/GLib unavailable in generic source CI); additional tests cover unsolicited trust, expiry, wrong paths, bus spoofing, missing Paired property, device limit, untrusted services, previously trusted reconnects and Release. \`scripts/audit_rootfs.py\` adds guard \`bluetooth_trust_requires_agent_authorization\` plus four negative/positive rootfs tests in \`tests/test_rootfs_audit.py\`. Image guard count should rise from **59 to 60** after native verification. This is a **bounded legacy AGPL security hardening**, NOT a cryptographic owner-claiming mechanism or new Model C commercial-only feature.

**Unresolved gates unchanged:** Public main and historical AGPL rights unchanged, future Model C NOT EFFECTIVE, private new product repo not verified (issue #37), source ownership/legal review issue #32, Raspberry Pi OS third-party notices issue #40 (particularly raspberrypi-net-mods), and physical Pi4/Edifier approval issue #2 OPEN. No public Release, merge, history rewrite or owner provisioning claim. The latest source CI and native run must be rechecked live before next development.


## N. Further PR46 BlueZ crash-safety fix: never allow infinite adapter discovery

**Newly confirmed upstream BlueZ property semantics:** [official BlueZ org.bluez.Adapter documentation](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst) states **DiscoverableTimeout=0** and **PairableTimeout=0** disable their respective timers, potentially leaving adapters discoverable/pairable indefinitely. The previous AudioHub agent explicitly set \`DiscoverableTimeout=dbus.UInt32(0)\` and did not set finite \`PairableTimeout\`. If the agent crashed or the OS unexpectedly lost its periodic refresh, the adapter could stay open.

**Security fix on PR46:** Set **both** adapter timeouts to \`dbus.UInt32(BOOT_WINDOW)\` (= 600 seconds), first set Pairable/Discoverable false on startup and then reopen only after the \`allowed()\` decision. The initial guest pairing deadline now uses **boot-relative Linux CLOCK_MONOTONIC uptime** \`float(BOOT_WINDOW)\`, rather than \`time.monotonic() + BOOT_WINDOW\` on every agent process start: a simple systemd service crash/restart cannot regrant a complete ten-minute window. A reboot is a separate owner-claiming problem and is **not** security enrollment.

**Test evidence:** code SHA \`0852894bde8504606cfdc32252a3c5c075c5771a\`, [source GitHub Actions run #42125422399](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42125422399) **SUCCESS, 441/441 Python tests**. Adds 3 static policy tests and 4 image-rootfs adversarial tests detecting infinite timeouts and restart-widened pairing window. New rootfs check \`bluetooth_pairable_discoverable_timers_bounded\` increases the total required real image checks to **61** (from PR45's verified 59 via PR46's two new guards). The independent native ARM64 run at this final docs update must be checked live; source CI does NOT establish BlueZ behavior on a real Pi.

**Prior exact source CI #42124897548** passed 434 tests at initial docs checkpoint SHA \`8341d2a7709c10d2810462f7a4455b51ac5b8adf\`; superseded by the later 441 tests at code SHA above. Additional checkpoint/docs edits may supersede this SHA; always verify latest exact-head Actions run and artifact before stating final success.

**Remaining limits:** still NoInputNoOutput experimental pairing, no cryptographically authenticated owner-claiming, no manual physical verification of BlueZ callbacks, no Pi4/Edifier loudspeaker acceptance, no effective Model C commercial license, no complete third-party OS permission review, no public image Release. Public AGPL recipients retain their rights.


## O. 2026-11-06: bounded PipeWire process output and topology parsing — Draft PR #47

**Verified parent:** [Draft PR #46](https://github.com/RIVANOXcom/rivanox-audiohub/pull/46) exact SHA `c37f309ec42b5a29e8254b76bf57f4f2ff21a1c9`. [Source run #42125603821](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42125603821) **SUCCESS 441/441 tests**, and [native ARM64 run #42125593262](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42125593262) **SUCCESS 61/61 real rootfs guards**, rootfs 689 dpkg packages (538 arm64, 151 all), 680 copyright hashes / 9 unresolved file paths. Four-file **UNVERIFIED / DO NOT DISTRIBUTE** ZIP [artifact #13461790759](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42125593262/artifacts/13461790759), size 605817619 bytes, expires **2026-12-05T23:03:39Z**. `public_release_ready=false`; no physical Pi, legal or owner acceptance.

**New [Draft PR #47](https://github.com/RIVANOXcom/rivanox-audiohub/pull/47)** branch `wd-papa-20261106-bounded-pipewire-process-output`, based on PR46. Existing legacy AGPL code used `subprocess.run(...capture_output=True)` for `pw-dump` in both the live audio supervisor and hardware preflight. This buffered untrusted metadata without a byte limit in Raspberry Pi RAM, despite a timeout. A malformed or high-volume PipeWire graph could degrade/stall playback or exhaust memory.

**Implemented:** a reviewed, pure-standard-library `src/audiohub/process_capture.py` helper launches argv-only subprocesses with `shell=False`, discards stderr to avoid accidental hardware/peer identifier exposure, incrementally reads stdout using `selectors.DefaultSelector` in 64 KiB chunks, caps the decoded stdout at **4 MiB**, rejects invalid UTF-8 and out-of-range/invalid arguments, respects the overall process timeout, and kills the dedicated subprocess process group on rejection. `runtime.run()` and the read-only `hardware_preflight.probe()` both use this bounded helper; `discovery.pipewire_nodes()` refuses snapshots above **4 MiB** or **8192 objects**. Large or unsafe readings are treated as **no trustworthy output**: the existing runtime USB route safety rules must continue to fail closed.

**Validation:** added live child-process regression tests in `tests/test_process_capture.py`, parser tests in `tests/test_discovery.py`, updated preflight mock tests and four new real-rootfs guard negative/positive tests. New `scripts/audit_rootfs.py` check `pipewire_stdout_bounded_no_shell` requires the actual installed capture helper and both runtime/preflight call sites. **Actual native image check total 63 confirmed on ARM64 run #42180343356** only if verified against the exact final PR47 SHA (PR46 verified 61). Added two new files to the pending-review rights ledger, now **81 files** with ALL ownership/third-party/Model C eligibility assertions FALSE. No license has been switched.

**Next new-chat action:** verify LIVE PR47 HEAD and exact source + ARM64 Actions outcomes, fix any test/image failures, record final guard count, expiration and provenance. Only source CI and actual native image evidence may be marked PASS; no physical Edifier sound/no commercial rights. Open owner/private repo issue #37, legal issue #32, Raspberry Pi third-party license issue #40, hardware issue #2. Keep all stacked PRs DRAFT, public AGPL main unchanged, no official GitHub Release.


## P. 2026-11-06: offline human-observed Pi4/Edifier test harness — Draft PR #48

**Parent** [Draft PR #47](https://github.com/RIVANOXcom/rivanox-audiohub/pull/47) exact code SHA `24dec6ed2ecde427ff606b77b900620f36cb6469` source [run #42180349159](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42180349159) **SUCCESS 460/460 Python tests**; it introduces bounded PipeWire capture. Parent independent native ARM64 [#42180343356](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42180343356) was in progress when this branch was opened; **parent native run PASSED 63/63 on its exact SHA**. PR46's parent native run #42125593262 independently passed 61/61 guards. Current public main AGPL unchanged.

**New [Draft PR #48](https://github.com/RIVANOXcom/rivanox-audiohub/pull/48)**, branch `wd-papa-20261106-offline-hardware-acceptance-checklist` stacked on PR47 (not main). This is a **legacy AGPL developer diagnostic**, NOT a new commercially restricted Model C product feature.

**Why:** Existing read-only `hardware_preflight.py` could identify expected Edifier USB and three PipeWire virtual sinks but could NOT prove any audible audio, successful three-input mixing, per-channel mute/EQ, safe USB removal or prolonged reliability. No source CI/native build can hear speakers or confirm physical behavior. The new manual harness `src/audiohub/manual_acceptance.py` runs **only when invoked by a person at a local Pi console** as `python3 -m audiohub.manual_acceptance`. It first calls the topology preflight; when prerequisites are incomplete it emits a small diagnostic and asks no questions. When ready it prompts for six deliberately physical observations (audible USB speakers, three-input mixing, channel isolation, USB unplug failsafe, clipping, independent 24h endurance). Answers accepted are ONLY `yes/no/skip`; free-form text, addresses/serials/passwords are discarded; three attempts max and EOF/Ctrl-C yields not tested. Output is bounded-schema privacy-safe JSON to stdout ONLY, no files, network, pairing, system state changes, or automatic audio generation. [English local Pi runbook](HARDWARE-OBSERVATION-RUNBOOK.md) gives exact execution commands and bench safety notes.

**Critical release gate:** Even if the human says yes to all six, `hardware_accepted=false`, `ownership_authenticated=false`, `legal_redistribution_approved=false`, `model_c_license_effective=false`, `release_ready=false`, and `persisted=false`. Human statements are observations, NOT independent certification or real device acceptance, legal rights, owner provisioning or image release approval.

**Validation:** 17 unit/CLI privacy/regression tests in `tests/test_manual_acceptance.py`, four actual image-rootfs guard tests in `tests/test_rootfs_audit.py`. New rootfs guard `manual_hardware_observation_not_auto_approval` expected to raise PR47's verified **63 to 65** only after a successful native image run on PR48's final HEAD. Adds two rights-pending files (new module and test), from 81 to **83 checked-in source/test/CI files**, all approvals FALSE. Rootfs build must include manual_acceptance.py, and CI must fail when code could mark hardware or release automatically. Check latest source and native ARM64 CI and collect real Pi bench operator results separately.

**Still BLOCKED:** physical Pi4 + Edifier R600USB independent acceptance issue #2; vendor OS notice/rights issue #40 (nine copyright paths incl. raspberrypi-net-mods), licensor/Model C legal issue #32, new empty private owner-created future Model C repo issue #37. No public GitHub Release or main merge, no AGPL history changes, no user ownership claims.


### Evidence correction: installed source-file checks also count

PR47 exact SHA `24dec6ed2ecde427ff606b77b900620f36cb6469` independently passed **460/460 source tests** ([#42180349159](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42180349159)) and **63/63 actual ARM64 rootfs checks** ([#42180343356](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42180343356)). The initial projection 62 missed that the installed new `process_capture.py` presence is its own guard in addition to the dedicated bounded-output safety rule. Native image passed XZ/SHA256/four-file proof; temporary UNVERIFIED [artifact #13485144050](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42180343356/artifacts/13485144050), 605962055 bytes, expires 2026-12-06T07:29:20Z. 689 packages / 680 copyright hashes / 9 unresolved; `public_release_ready=false`.

PR48 adds an installed `manual_acceptance.py` source check and independent no-release manual observation guard. Native target is therefore **65** (not the initially predicted 63). PR48 source CI [#42181382213](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181382213) **SUCCESS 481/481 Python tests** at code+docs SHA `0c07dcfa5fccb83db9b276f2b14c11ef45db8d53`. The independent ARM64 image [#42181376193](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181376193) was in progress when recorded; check final conclusion and newly built image against latest PR48 HEAD after this documentation correction.


## Q. 2026-11-06 — fail-closed ambiguous PipeWire node/route identities (Draft PR #49)

**Parent verified:** [Draft PR #48](https://github.com/RIVANOXcom/rivanox-audiohub/pull/48), exact SHA `aeafb0b06cc781c8470b502fe1ecf3484084696f`: [source CI #42181848095](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181848095) **SUCCESS 481/481**, and independent [native ARM64 #42181839470](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181839470) **SUCCESS 65/65 actual rootfs checks**. Four-file temporary **UNVERIFIED / DO NOT DISTRIBUTE** image artifact [#13485629030](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181839470/artifacts/13485629030), 605853769 bytes, expires **2026-12-06T07:43:50Z**. 689 installed packages, 680 observed copyright hashes and nine outstanding notice paths; `public_release_ready=false`. No physical Pi4/Edifier audible test, owner authentication or legal release permission is established.

**New DRAFT [PR #49](https://github.com/RIVANOXcom/rivanox-audiohub/pull/49)**, branch `wd-papa-20261106-failclosed-pipewire-identity-ambiguity`, stacked on PR48. Source-level defect: the legacy `virtual_sinks(nodes)` dictionary overwrote duplicate `audiohub.music/laptop/tablet` names with the *last* PipeWire Node ID; `bluetooth_sources()` selected the *first* matching profile when two candidate sources reported the same Bluetooth address. A duplicated global Node ID could also be incorrectly treated as a valid selected USB output or a trusted graph link. These are externally sourced metadata and must never silently decide where audio goes.

**Implemented fail-closed behavior:** `_conflicting_node_ids(nodes)` rejects a snapshot with repeated valid PipeWire Node IDs for USB selection, virtual EQ sinks and Bluetooth captures. If ANY logical sink name is repeated, `virtual_sinks` yields **no sinks** so the existing supervisor stops its previously managed `pw-loopback` routes. If two eligible Bluetooth sources represent one MAC address, neither ambiguous candidate is accepted; unrelated source identities still work. Malformed non-string virtual node names are ignored safely. `hardware_preflight.inspect_topology` refuses a `ready_for_manual_test` classification and `audio_graph.summarize_links` refuses positive link evidence when Node IDs conflict. This does not alter audio volume, device ownership, pairing permission, network exposure or release rights.

**Regression:** ten discovery tests for duplicate sink names, global ID conflicts, duplicate Bluetooth sources, unrelated valid devices and malformed metadata; one live supervisor process-termination test; one graph-link and one physical preflight test; six synthetic rootfs guard tests. `scripts/audit_rootfs.py` adds image check `pipewire_node_identity_ambiguity_fails_closed` across installed discovery, graph and preflight modules. Native guard count target **66** after independently verified PR48 **65**. Existing source rights ledger unchanged at **83 pending files**; all owner/origin/Model C approvals remain false. This is legacy AGPL safety maintenance.

**CI evidence on code-only SHA `27d13828011a50fff9cd7b664a508e2ffe76ce89`:** [source Actions #42200344244](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42200344244) **SUCCESS 500/500 Python tests**, rights ledger all FALSE. Earlier red run #42200238395 surfaced obsolete BT integration expected first-wins behavior; test updated to assert that ambiguous MAC is discarded; following source run GREEN. Independent native ARM64 [#42200336164](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42200336164) was IN PROGRESS on code SHA, not confirmed as native PASS. This combined documentation/checkpoint commit will change PR49 HEAD; **always recheck the final exact-head source/native runs before claiming completion**.

**Unchanged GO/NO-GO:** no public release or new commercial image. Main remains public AGPL-3.0-only; future Model C NOT EFFECTIVE, owner-created private repository `RIVANOXcom/rivanox-audiohub-next` not verified (issue #37). Open third-party OS rights issue #40, license/ownership issue #32 and actual Pi4/Edifier physical acceptance issue #2. Source/in-image static checks are NOT proof of sound, real Bluetooth compatibility, secure ownership or redistribution rights.


## R. 2026-11-06 — root-owned offline diagnostic status path protection (Draft PR #50)

**Parent:** [Draft PR #49](https://github.com/RIVANOXcom/rivanox-audiohub/pull/49) exact base SHA `1734042469c52aea21179d7ae40f7287fac5152e`, [source CI #42200628247](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42200628247) **SUCCESS 500/500 Python tests**. Parent independent [ARM64 run #42200618383](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42200618383) was in progress when PR50's source implementation completed; do not claim 66/66 without live verification. Last **independently verified native image** remains PR48 [#42181839470](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181839470), 65/65 rootfs checks, 481 source tests and temporary UNVERIFIED artifact #13485629030, 689 installed packages/680 copyright hashes/9 unresolved notices, no release permission.

**New [Draft PR #50](https://github.com/RIVANOXcom/rivanox-audiohub/pull/50)** on isolated branch `wd-papa-20261106-offline-diag-runtime-path-nofollow`, stacked on PR49. This is maintenance to existing legacy AGPL code, NOT future proprietary Model C product publication.

**Concrete security defect:** system-level `audiohub-firstboot-diag.service` runs with elevated OS credentials to collect redacted health statistics from unprivileged user-owned `/run/user/UID/audiohub/runtime-status.json`. Earlier `firstboot_diag._read_runtime` used `O_NOFOLLOW` only when opening the *final* file; a user-created symlink in a parent component could route the privileged reader to a different same-UID JSON file and falsify the health report. The previous reader also did not explicitly require the parent directory and status file to have private owner-only permissions. This would not directly export raw device identifiers but undermines the integrity of reported observations.

**Fix:** traverse the absolute runtime path from root with `O_DIRECTORY|O_NOFOLLOW` for **each** parent using directory FDs. Deny relative or `..` traversal paths and invalid user IDs. Check last directory is owned by target audiohub UID and has no group/other rights; open only the final plain regular file with nofollow/nonblocking, matching UID, one hardlink, no group/other rights and bounded nonempty 4 KiB JSON. Reject size changes or malformed JSON with safe stale/no-health output. No network connection or actual playback is triggered. Private valid runtime status still works.

**Regression:** eight new adversarial local tests in `tests/test_firstboot_diag.py` (symlinked directory, public state directory, insecure file mode, hardlinked status, wrong owner, malformed paths/UID and private normal state) plus four synthetic rootfs tests in `tests/test_rootfs_audit.py` and new image audit `offline_diag_runtime_directory_nofollow_private`. Native target PR49's expected **66 + 1 = 67** rootfs checks, provided parent PR49 actually passes. Source rights ledger remains **83 entries**, all ownership, third-party and Model C approvals FALSE.

**Initial PR50 code SHA `a362b1630e6001478634d2c1f4f6bfde9814a007`:** [source GitHub Actions #42201349549](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201349549) **SUCCESS 512/512 Python tests**. Child native ARM64 run [#42201386174](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201386174) was queued/in progress on later workflow SHA, not yet verified when this entry was written. This combined documentation/checkpoint commit itself changes PR50 HEAD: recheck exact-head source/native CI and rootfs count before claiming a new image or QA acceptance.

**Release and legal limits remain:** AGPL-3.0-only public main unchanged; Model C future license not legally effective; private future product repo issue #37 not verified; legal review #32, Raspberry Pi OS third-party notices #40 and real Pi4/Edifier testing #2 remain open. No official GitHub Release, owner claim, public hardware signoff, deployment, merge or license change. Human operator must manually install any eventual Umbrel build.


## S. 2026-11-06: bounded PipeWire output in the opt-in LAN test receiver — Draft PR #51

**Verified parent:** [Draft PR #50](https://github.com/RIVANOXcom/rivanox-audiohub/pull/50) exact SHA `275089e3d511e0d6c8fb68e601a9001b13b382b6`; [source CI #42201597233](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201597233) **SUCCESS 512/512 Python tests**, independent real [ARM64 image CI #42201589717](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201589717) **SUCCESS 67/67 rootfs checks**, XZ/SHA256/four-file provenance. Temporary **UNVERIFIED, DO NOT DISTRIBUTE** image [artifact #13494264314](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201589717/artifacts/13494264314), size **606104982 bytes**, expires **2026-12-06T10:27:02Z**. Rootfs: 689 actual packages, 680 copyright notice hashes, nine unresolved copyright paths; `public_release_ready=false`. All 83 source/test/build/CI files remain rights-pending; historical public AGPL remains effective.

**New [Draft PR #51](https://github.com/RIVANOXcom/rivanox-audiohub/pull/51)** on `wd-papa-20261106-laptop-pipewire-bounded-process` (base PR50). Existing legacy `src/audiohub/network_laptop.py` is a manually enabled, **UNAUTHENTICATED experimental Windows Scream UDP receiver**; it is NOT installed as an enabled service. Its `check_audio_target()` still invoked unbounded `subprocess.run(...capture_output=True)` for both `pw-dump` and `wpctl set-default`. This remained after PR47 successfully capped the regular supervisor/hardware preflight process output. Repeated health checks could allocate arbitrarily much untrusted PipeWire stdout/stderr and disclose local metadata in temporary process objects.

**Technical correction:** reuse the already unit-tested `process_capture.bounded_command_output` for **both** PipeWire graph inspection and reasserting the selected USB output. Enforce **4 MiB stdout cap**, **5-second timeout per command**, no shell, no stderr retention and process-group kill on oversized/hanging subprocesses. An unsafe/missing/failed `pw-dump` stops BEFORE any `wpctl` write; a bounded but unsuccessful `wpctl` never permits the test receiver to start or keep playback. The PR49 duplicate PipeWire ID/sink checks remain effective. Existing explicit `--unsafe-lan-test`, specific RFC1918/loopback sender and bind, private manual source policy and disabled-by-default receiver are unchanged. This is NOT network sender authentication or fit for a public/LAN product.

**Validation on pre-documentation code SHA `a4872f0bd66f38e48c1fe24a9f23304d68f76ced`:** [source CI #42208006876](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208006876) **SUCCESS 522/522 tests**, per-file source rights ledger **83** with ALL human origin / third-party / future Model C approvals FALSE. Six new direct manual receiver negative tests plus four synthetic rootfs guard tests. Existing `tests/test_flexible_routing_integration.py` mock still patched `subprocess.run`, so early source CI [#42207735994](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42207735994) failed one obsolete test; updated to verify `bounded_command_output` and its fixed timeout. Exact-head later source run is GREEN. Installed image guard `manual_laptop_pipewire_capture_bounded` extends PR50's 67 verified checks to a target **68/68**, **not yet native-verified at this entry**.

**Next MISSIONPILOT action:** check LIVE PR51 HEAD and exact source/native ARM64 run after this docs/checkpoint commit (docs change triggers new CI and cancels intermediate runs). Confirm true 68/68 rootfs checks, temporary artifact properties, 689/680/9 rights evidence and `public_release_ready=false`. Record passing/failing exact SHA, run IDs, PR comment and Workbench. Do NOT merge or publish GitHub Releases.

**Existing blockers unaffected:** no actual Pi4 + Edifier R600USB audible/multi-input hardware signoff (issue #2); nine missing supplier OS notice file paths and rights issue #40; rightsholder + commercial Model C counsel review issue #32; future independently created PRIVATE `RIVANOXcom/rivanox-audiohub-next` not visible to connector (owner task #37). Public main remains AGPL-3.0-only; future Model C license NOT EFFECTIVE. No Gitea software package release or permission to install.


## T. 2026-11-06: bounded HTTP status-preview clients and private request logs — Draft PR #52

**Parent [Draft PR51](https://github.com/RIVANOXcom/rivanox-audiohub/pull/51)** exact source/docs SHA `d4fd8053a13618f3f7ad35fb26888288f6586a1d`: [source GitHub Actions #42208450554](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208450554) **SUCCESS 522/522 Python tests**. Independent [native ARM64 #42208440878](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208440878) was still in progress during this section's initial writing, expected **68** real rootfs checks; no native pass may be inferred until checked live. Last verified native PR50 run #42201589717 achieved 67/67. Public main remains AGPL-3.0-only; no actual public release.

**New [Draft PR52](https://github.com/RIVANOXcom/rivanox-audiohub/pull/52)** on `wd-papa-20261106-bounded-status-http-workers-privacy`, stacked on PR51. The existing **read-only unauthenticated alpha status page** defaulted to IPv4 loopback but supported manual explicit insecure LAN opt-in. Standard `ThreadingHTTPServer` generated one Python thread **per accepted connection without a hard concurrency cap**; the default `BaseHTTPRequestHandler.log_message` recorded request lines, including attacker-provided URL queries and possible MAC/tokens, in journal stderr. A local or deliberate LAN test could consume resources with many stalled sockets or leak untrusted URL strings to status logs.

**Implemented:** `BoundedStatusHTTPServer(ThreadingHTTPServer)` with a **nonblocking `BoundedSemaphore(8)`** for maximum eight simultaneous request worker threads; other accepted connections are closed (never queued as unlimited work). HTTP accept backlog capped at eight; every accepted socket gets a **five-second read timeout**. Slots are released both after normal/failed processing and after unexpected thread-start failure; workers are daemon threads. `Handler.log_message` discards request URL, query and client strings instead of exposing them to journal. Existing `select_bind_address` explicit loopback/specific RFC1918 bind, manual opt-in for LAN, GET allowlist, read-only API and denied mutation methods are unchanged. This is **NOT authentication** or acceptable public Internet exposure.

**Validation on initial code SHA `f120ccaea9d217b317f2048b52844a9c8206b520`:** [source GitHub Actions #42209328344](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42209328344) **SUCCESS 535/535 Python tests**; source rights ledger still **83 files**, all human-rightsholder, third-party origin and proposed Model C eligibility flags FALSE. Nine new no-port unit tests in `tests/test_web_status.py` exercise bounded concurrent admission, overflow rejection, failure/normal worker slot release, 5-second timeout, timeout setup error close and no query log leakage. Existing startup mock tests now target the bounded class. Four negative/positive synthetic image tests plus new audit guard `status_http_clients_bounded_no_request_logs`. If PR51 final native truly passes expected **68**, PR52 native image target **69** real checks. This docs commit changes HEAD, so must verify exact post-documentation source and independent ARM64 run before claiming the package.

**Open GO/NO-GO gates:** historical AGPL cannot be retroactively switched; future Model C license NOT EFFECTIVE; source ownership/legal review #32; owner-created new independent PRIVATE repo #37 not verified; nine supplier OS copyright notice paths #40; physical Pi4/Edifier audible routing and secure owner claim #2 missing. Draft PRs not merged, no productive deployment, public GitHub release, Gitea installable product, Umbrel changes or permissions changed.

**Next authorized work:** verify PR51 and PR52 exact source/native CI, correct any image guard or test failures, record actual count/artifacts and Workbench evidence. Continue identifying alpha safety issues without exposing LAN features or claiming device hardware/license acceptance.


### Verification update — PR51 native ARM64 PASS at exact code/docs SHA

[PR51](https://github.com/RIVANOXcom/rivanox-audiohub/pull/51) SHA `d4fd8053a13618f3f7ad35fb26888288f6586a1d` has now independently passed **522/522 Python tests** ([source #42208450554](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208450554)) and **68/68 actual native Raspberry Pi image guards** ([ARM64 #42208440878](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208440878)). Verified XZ/SHA256/four-file temporary **UNVERIFIED / DO NOT DISTRIBUTE** archive [#13497588492](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208440878/artifacts/13497588492), **605887450 bytes**, expires **2026-12-06T11:20:20Z**. 689 installed packages, 680 copyright file hashes, nine missing file paths, `public_release_ready=false`. This confirms manual LAN receiver bounded PipeWire graph and wpctl command safety **only**, NOT authenticated LAN audio, real speaker sound or rights/release approval.

[PR52](https://github.com/RIVANOXcom/rivanox-audiohub/pull/52) first full code/docs SHA `ed9dbc68ccff2e03f2ae123aa066efc69d794971` source [run #42209656187](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42209656187) **SUCCESS 535/535** Python tests with pending rights 83 files. Independent [native run #42209649230](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42209649230) was in progress at the checkpoint. New `status_http_clients_bounded_no_request_logs` guard target **69** actual checks. **Re-check the final HEAD after this evidence commit**, because branch changes can restart native CI.


## U. 2026-11-06: require private owner-authored web runtime status — Draft PR #53

**Parent:** [Draft PR #52](https://github.com/RIVANOXcom/rivanox-audiohub/pull/52) exact parent SHA `8f8f8867de3951e69fcfc425161a984f75c3cdd5`, [source CI #42209878395](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42209878395) **SUCCESS 535/535 Python tests**. Independent native ARM64 [#42209873318](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42209873318) was IN PROGRESS during PR53 source testing; new parent image guard target 69, **do not claim 69 actual checks until real native run finishes**. Last independently verified native remains PR51 exact SHA `d4fd8053a13618f3f7ad35fb26888288f6586a1d`, source 522/522 and ARM64 [#42208440878](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208440878) **SUCCESS 68/68**, unverified temporary artifact #13497588492 (605887450 bytes, expires 2026-12-06T11:20:20Z). 689 OS packages, 680 observed copyright hashes, 9 unresolved and `public_release_ready=false`.

**New [Draft PR53](https://github.com/RIVANOXcom/rivanox-audiohub/pull/53)**, branch `wd-papa-20261106-private-status-file-identity` stacked on PR52. Real source defect: local read-only `webserver.read_public_status` used a bounded symlink-safe open, but it accepted a same-path JSON file despite **world/group-readable mode, wrong owner, multiple hardlinks, or a nonprivate final directory**. Such a file must not be treated as freshly reported health. Static public HTML/JS files are intentionally root-owned and world-readable, so those must NOT be blocked by the runtime-only check.

**Fix:** add optional `private_owner` to `_bounded_regular_bytes(path, limit, *, private_owner=None)`; only `read_public_status` passes the effective audiohub UID using `private_owner=os.geteuid()`. The runtime status *parent directory* must be owned by that UID and inaccessible to group/other; the regular status file must be same UID, `st_nlink==1`, have no group/other permissions and satisfy the preexisting bounded nofollow read. Failure returns an anonymized **stale/no USB health** response. Static assets keep using the unrestricted byte helper without `private_owner`, retaining 0644 visibility. This does not authenticate an owner, prove physical audio or expose local network.

**Tests:** 8 new privacy/negative/positive read-only web tests in `tests/test_web_status.py` for valid 0600, public/group mode, wrong owner, hardlink, insecure parent directory, fake health, invalid private-owner argument and static 0644 access. Four native rootfs guard tests in `tests/test_rootfs_audit.py`. New image check `status_runtime_private_owner_and_hardlink_guard` target **70** real guards after PR52's expected 69, **only when independently verified**. No new file has been added; rights ledger remains **83 files**, with every proposed Model C, rightsholder and third-party approval FALSE.

**Initial PR53 code SHA `2206e81d527afc6ce3a9c1a6c813f447b9556e2b`:** [source GitHub Actions #42210517166](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42210517166) **SUCCESS 547/547 Python tests**. [Native ARM64 #42210542483](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42210542483) was queued on a subsequent workflow-change commit. This documentation/rights checkpoint changes PR53 HEAD again: independently confirm final exact-head source and ARM64 runs. A red intermediate SHA is not a final failure; a cancelled native intermediate is not evidence of a passed image.

**No authorized GO:** public main remains AGPL-3.0-only, future commercial Model C NOT EFFECTIVE; owner-created new independent PRIVATE product repo unavailable (issue #37); rightsholder/legal license clearance issue #32; nine Raspberry Pi OS supplier copyright file gaps issue #40; actual Pi4 + Edifier R600USB audible, three-input mixing and secure owner acceptance issue #2 open. All PRs remain DRAFT, no merge, no official GitHub release, Gitea release, Umbrel manual installation or permissions change.

## V. 2026-11-06: verified PR53 and harden malformed read-only status requests — Draft PR54

**Verified parent:** Draft PR53 exact head `53e49521bc8fd24a3c622cd07c944c5ccced4287` has independent source [run #42210835227](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42210835227) **SUCCESS 547/547**, and actual native ARM64 [run #42210825401](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42210825401) **SUCCESS 70/70 rootfs checks**. The temporary, explicitly UNVERIFIED artifact [#13499596254](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42210825401/artifacts/13499596254) is 605800594 bytes ZIP, sha256 `243c812f7ad6e407c31f926bcf1729a8993b2f4c2397e6df33c01adf972ca9da`, expires 2026-12-06; bundle SHA256/XZ checks passed. 689 installed OS packages, 680 observed copyright files and nine unresolved. PAPA Workbench evidence #2984. Public main was `84303e22b14da9e876ec6288af376671fd9898a9` on recheck.

**New isolated Draft PR54**, branch `wd-papa-20261106-status-parser-failclosed`, stacked on PR53 without changing any parent branch. Two concrete input faults in `src/audiohub/webserver.py`: a private yet malformed, very deeply nested JSON status document (still below the existing 32 KiB size ceiling) can raise an uncaught `RecursionError` from `json.loads`; a malformed HTTP absolute request-target with invalid IPv6 brackets can raise uncaught `ValueError` from `urlsplit`. Both are fail-closed (anonymized stale/no USB health or 404), preserving 8-client cap, 5s per-client timeout, no access log, strict private-UID status file gate, loopback default, static 0644 assets, five locales and read-only API. Two new real behavior unit tests and three synthetic installed-image gate tests with new guard `status_malformed_inputs_fail_closed`: expected **71** rootfs image checks only after actual independent ARM64 CI. Existing per-file rights ledger remains 83 files; no rights, Model C, hardware or release authorization.

**Verification:** Run PR54 exact-head source and native ARM64 CI, inspect counts and temporary artifact before calling source/image tests PASS. If either fails, fix in this branch only; do not claim hardware or product release GO. No merges, deploys, owner permission changes or Gitea/Umbrel installations.

## W. 2026-11-06: strict duplicate-key and finite-number status JSON — Draft PR55

**Parent:** [Draft PR54](https://github.com/RIVANOXcom/rivanox-audiohub/pull/54) exact head `f08aa400f25a1307368c41adb79504fec059c4a3`, source [run #42219045806](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42219045806) **SUCCESS 552/552**. Independent ARM64 [#42219039337](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42219039337) was still running at the start of this step, so 71 actual image checks and its artifact cannot yet be claimed. Parent PR53 SHA `53e49521bc8fd24a3c622cd07c944c5ccced4287` last verified native 70/70.

**New isolated Draft PR55:** branch `wd-papa-20261106-strict-status-json-integrity`, stacked solely on exact PR54 head. Python's default `json.loads` silently resolves repeated object members to the last value and accepts non-standard `NaN`/`Infinity` numeric literals. A size-bounded, private-UID status file with inconsistent or corrupted health fields could therefore appear fresh. Keep the existing 32 KiB private nofollow / UID / hardlink / ownership checks, but pass `object_pairs_hook=_unique_json_object` and `parse_constant=_reject_json_constant` and use the existing ValueError catch to report anonymous stale/no USB health. Reject duplicates recursively, even in ignored metadata, and never include keys or secrets in exceptions or logs. Three real negative test methods and three synthetic rootfs guard tests, with new image guard `status_json_unique_keys_and_finite_numbers_only`, target **72** checks only when independent exact-head native ARM64 CI proves them. Five locales, static assets, no public mutations, loopback default, existing client caps and access-log privacy unchanged. Rights ledger remains 83 unreviewed files, legacy AGPL-3.0-only remains effective, Model C not activated.

**Validation:** Exact-head source CI then independently verify native ARM64 image and SHA256/XZ provenance if generated; no automatic release/installation or CI-as-hardware certification. Preserve all existing PRs/main; update PAPA Workbench evidence when verified.

## X. 2026-11-06: total HTTP client lifetime and private error handling — Draft PR56

**Verified parent ancestry:** PR54 exact head `f08aa400f25a1307368c41adb79504fec059c4a3`, source [#42219045806](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42219045806) **SUCCESS 552/552**, independent native ARM64 [#42219039337](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42219039337) **SUCCESS 71/71 actual installed rootfs checks**, 689 OS packages/680 copyright docs/nine still unresolved. Temporary UNVERIFIED [artifact #13502838048](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42219039337/artifacts/13502838048), ZIP size 606171782, SHA256 `d7eaa30e4e06220daa33d989617dcd0bd681d16b6b06dc0b860cdd9f7182232d`, expires 2026-12-06. Workbench #2986. Draft PR55 first code/docs SHA `76bb3b89e74f15b450fb49deba3e8b6c31f4e477` source #42220163954 SUCCESS 558/558, but native rootfs guard had stale one-line parser marker after strict multiline `json.loads` change. Safely repaired on **its own** PR55 branch, head `e7e8751ef1841c148274a2f85aefc950c2219fbb`; exact post-fix source and ARM64 run must be re-verified before claiming 72 image checks. Workbench #2987 covers the earlier source run, not new native approval.

**New isolated Draft PR56** on branch `wd-papa-20261106-status-http-total-deadline-privacy`, stacked on PR55 fixed head `e7e8751ef1841c148274a2f85aefc950c2219fbb`. Earlier PR52 caps 8 active HTTP connections and sets 5 seconds per socket receive; an attacker could send one byte every few seconds and keep all 8 worker slots indefinitely because receive timeouts reset. Add a maximum **15-second total active client lifetime**, enforced by a per-admitted-request `threading.Timer` that interrupts the socket on expiry; timer cancelled and bounded semaphore released even when processing fails. Also override `BoundedStatusHTTPServer.handle_error` so Python's default peer-address/traceback leak does not enter systemd logs. Read-only routes, no raw request logs, 5-second socket timeout, loopback default, private status file, static assets, locale count and historical AGPL unchanged. Five real no-network watchdog/privacy tests and four synthetic rootfs adversarial tests; one native installed guard `status_http_total_lifetime_and_peer_error_privacy`: target **73** if independent native ARM64 proves it, parent PR55 target 72 pending. No new rights-ledger file; 83 unreviewed. No physical speaker, owner authentication, legal relicense, permissions change, merge, release or deployment.

**Validation next:** exact-head source CI then independent ARM64 73 checks, bundle SHA256/XZ provenance, Workbench update and next safe maintenance step. This is security hardening of unreleased alpha only.

**END OF HANDOFF.** If a live run/PR contradicts this document, treat
the live GitHub evidence as authoritative, reconcile and update this file.
