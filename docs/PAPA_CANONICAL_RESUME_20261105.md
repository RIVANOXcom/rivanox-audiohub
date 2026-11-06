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
https://github.com/RIVANOXcom/rivanox-audiohub/blob/wd-papa-20261106-bounded-pipewire-process-output/docs/PAPA_CANONICAL_RESUME_20261105.md
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

**Validation:** added live child-process regression tests in `tests/test_process_capture.py`, parser tests in `tests/test_discovery.py`, updated preflight mock tests and four new real-rootfs guard negative/positive tests. New `scripts/audit_rootfs.py` check `pipewire_stdout_bounded_no_shell` requires the actual installed capture helper and both runtime/preflight call sites. **Expected native image check total 62** only if verified against the exact final PR47 SHA (PR46 verified 61). Added two new files to the pending-review rights ledger, now **81 files** with ALL ownership/third-party/Model C eligibility assertions FALSE. No license has been switched.

**Next new-chat action:** verify LIVE PR47 HEAD and exact source + ARM64 Actions outcomes, fix any test/image failures, record final guard count, expiration and provenance. Only source CI and actual native image evidence may be marked PASS; no physical Edifier sound/no commercial rights. Open owner/private repo issue #37, legal issue #32, Raspberry Pi third-party license issue #40, hardware issue #2. Keep all stacked PRs DRAFT, public AGPL main unchanged, no official GitHub Release.

**END OF HANDOFF.** If a live run/PR contradicts this document, treat
the live GitHub evidence as authoritative, reconcile and update this file.
