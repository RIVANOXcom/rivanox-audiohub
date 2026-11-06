# RIVANOX AudioHub – authoritative developer handoff

> **2026-11-05 latest canonical recovery:** [PAPA_CANONICAL_RESUME_20261105.md](PAPA_CANONICAL_RESUME_20261105.md) and [machine-readable snapshot](PAPA_AUDIOHUB_CHECKPOINT_20261105.json) supersede older PR/#29-centered instructions below. Read the canonical file **FIRST**, verify all live GitHub PR HEADs/CI, then consult this historical incremental log. Current follow-up Draft PR #42 remains isolated from public AGPL `main`; future Model C is **NOT EFFECTIVE**.

**Last synchronized:** 2026-11-05, project `PJ2611-0001:R001`,
MissionPilot WD_JOB `PAPA-5B2E6939`.
**Read this file first when a chat breaks.** Then open
[ENGINEERING-BACKLOG.md](ENGINEERING-BACKLOG.md),
[GITHUB-SECURITY-RULESET.md](GITHUB-SECURITY-RULESET.md)
and GitHub [PR #29](https://github.com/RIVANOXcom/rivanox-audiohub/pull/29)
to verify the very latest live state. Do not trust a written SHA without
re-checking GitHub. The Workbench `PJ2611-0001:R001` AH requirements
remain the upstream task/validation authority; GitHub provides the
source, review, issues, artifacts and CI evidence.

## Current isolation boundaries (hard requirements)

- Public GitHub repo `RIVANOXcom/rivanox-audiohub`, default `main`;
  checked SHA `84303e22b14da9e876ec6288af376671fd9898a9`
  on 2026-11-05, **unmerged**; **0 official releases**.
- GET repository Rulesets returned **`[]`** and operator screenshots
  show the **main branch unprotected**. The GitHub ruleset is to be
  configured by **the operator**, not an engineering tool call.
  No AI/GitHub App bypass, admin/secrets grants or production
  permissions. Main and peers are not to be modified without
  explicit authority and a verified PR plan.
- Do not conflate successful source/ARM64 image CI with physical Pi4
  boot, audible Edifier sound, phone owner onboarding, 3-way concurrent
  playback, security/legal approval or a stable Release.
- All special/untrusted Windows UDP audio stays **MANUALLY OFF**,
  never systemd auto-enabled. Scream is plaintext/unauthenticated,
  sender IP filter spoofable. No third-party Windows driver is bundled.
- Web status is **read-only** and bound to localhost by default; no
  authenticated owner session and no remote audio mutation/rename API.
- User-facing channel names may be arbitrary distinct product names;
  stable technical slots are internal identifiers, not mandatory
  device categories. Renaming does NOT enroll or route a source.

## Latest actually proven image and current work

**Latest previous fully proven ARM64 build = PR #26**, source
`9e612290841ed586effc19ca37d2edab479d4524`,
[source CI 42064478374](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064478374)
SUCCESS **172 tests**, [Pi4 image CI 42064465468](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064465468)
SUCCESS **50/50 rootfs checks**, image integrity/manifest verified,
[temporary ZIP artifact #13433476966](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064465468/artifacts/13433476966)
expiring **2026-12-05**. Hardware/audio acceptance unverified;
GitHub sign-in required for the artifact. The PR #26 image includes
neutral local display names but **NOT the flexible source routing of PR #29**.

**Current in-progress DRAFT [PR #29](https://github.com/RIVANOXcom/rivanox-audiohub/pull/29)**,
branch `wd-papa-5b2e6939-flexible-source-route-assignment-20261105`,
stacked from PR #26 exact SHA
`9e612290841ed586effc19ca37d2edab479d4524`.
Adds private per-device 0600, schema-validated source mapping
`src/audiohub/source_routes.py`, three-slot manual LAN reservation,
at most two distinct Bluetooth sources on other slots, no duplicates,
new CLI `python3 -m audiohub.source_routes`, dynamic runtime A2DP
reassignment, fails closed on corrupt policy; the manually started
LAN UDP player reads its private slot once and **exits if slot changes**.
The source IP filter remains spoofable; do not use in trusted LAN.
Offline SD report gets only a boolean source-policy-valid flag.

**Current work checkpoint:** the integration tests and docs are in
this branch. Source checks must be confirmed against **the exact final
PR #29 head**; a fresh Pi image can be claimed only when native ARM64
CI passes its rootfs/pre-export checks, image SHA256/XZ, provenance,
and artifact upload. Previous artifact #13433476966 cannot be linked
as if it contains PR #29. Use PR #29 description and Issue #27 for
current CI run and artifact links, not stale copied SHA.

## Branch graph (preserve all parallel work)

- `main` → legacy separate unmerged drafts #5–#10.
- Legacy Windows Scream source-only drafts **#11 → #12 → #19**.
- Original USB hardware preflight **#13**, package inventory **#14**.
- Original localhost web guard **#15**, owner state/claim **#16 → #17 → #18**.
- Image/functional integration stack:
  **#6 → #20 → #21 → #22 → #23 → #24 → #25 → #26 → #29**.
  Each has its own branch and is a Draft; a new author should
  only edit **their own newly created branch based on a verified head**.
- Original per-source and conservative mix budget **#9** was ported
  into #24, not merged in place.
- No combined secure physical owner identity/phone Wi-Fi onboarding,
  no official published Release or operator hardware approval.

## Verified engineering architecture (not product acceptance)

Three independent internal EQ sink IDs
`audiohub.music`, `audiohub.laptop`, `audiohub.tablet`;
the **display names are user-controlled**, defaults `Input 1/2/3`.
**The proposed PR #29 policy now allows BlueZ A2DP streams to use any
two non-LAN-reserved EQ slots; the isolated, manually started LAN
receiver can feed the remaining slot.** No authenticated sender
or physical Bluetooth hardware concurrency is proven. The source code enforces
a finite 18,432-byte buffer, manual unsafe LAN opt-in, exact RFC1918
bind, explicit USB sink preflight and no auto network service.
USB default/loopback routing and recovery have mocked test coverage.
The 3-input master gain estimate budgets concurrent full-scale EQ
boosts, but no true-peak hardware limiter exists. A sandboxed one-shot
offline Pi report is intended to write
`AUDIOHUB-TEST-REPORT.json` to the SD boot partition; physical
execution has not been observed.

## Resume exactly – first next tasks and proof

1. **Verify PR #26** current diff and green source CI. If the
   local-name model is incomplete, correct safety, Unicode, locale,
   corruption and image-preexport tests before shipping any image.
2. **Get a new native ARM64 image artifact** for #26 only if relevant
   changes require Pi packaging, and verify the **exact** commit,
   100% rootfs checks, SHA256 of `.img.xz`, `xz --test`, manifest
   and a real uploaded temporary ZIP. Do not claim it as a release.
3. Owner configures the GitHub **main-only Active ruleset** using
   [operator guide](GITHUB-SECURITY-RULESET.md); do not change the
   permissions or grant the engineering app a bypass.
4. Continue **INPUT-02**: distinguish neutral names from authenticated
   physical device/source assignment. Design an authorized on-device
   state model that can reassign supported Bluetooth/LAN protocols
   to safe logical slots with collision checks. No unsupported dual
   Bluetooth promises or auto-start of insecure transport.
5. Continue **BOOT/OWNER/WIFI P0**: physical claim, phone onboarding,
   authenticated session+CSRF; blocked on concrete out-of-band
   ownership proof and real Pi hardware behavior, but tests/architecture
   can still progress without changing trust policy.
6. Operator runs isolated Pi4+Edifier USB/BT test with a **spare SD**
   and no trusted LAN/WLAN; capture redacted offline report,
   actual audible result and reproducible fault observations in Issue #2.
   Use Issue #3 for Windows/three-way mix and #4 for owner API/UI.
7. Integrate only in dependency order after a real review/approval;
   no hidden squash, rebase, merge, deployment, firmware installation,
   untracked deletion, security bypass or `WD_RELEASE_READY` claim.

## Persistent issue and evidence pointers

- [Engineering task, defects & optimization register](ENGINEERING-BACKLOG.md).
- [Ruleset setup & operator verification](GITHUB-SECURITY-RULESET.md).
- [Audio lab acceptance matrix](THREE-SOURCE-LAB-ACCEPTANCE.md).
- [Audio architecture](ARCHITECTURE.md), [release gates](RELEASE-ACCEPTANCE.md)
  and [device threat model](SECURITY-THREAT-MODEL.md).
- New follow-ups: [#27 owner-verified source assignment](https://github.com/RIVANOXcom/rivanox-audiohub/issues/27), [#28 main protection](https://github.com/RIVANOXcom/rivanox-audiohub/issues/28).
- GitHub issues:
  [#1 owner/Wi-Fi](https://github.com/RIVANOXcom/rivanox-audiohub/issues/1),
  [#2 Pi hardware](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2),
  [#3 network/mixer](https://github.com/RIVANOXcom/rivanox-audiohub/issues/3),
  [#4 authenticated UI](https://github.com/RIVANOXcom/rivanox-audiohub/issues/4).
- Workbench expected requirement IDs: AH-001 #3267, AH-002 #3268,
  AH-003 #3269, AH-004 #3270, AH-005 #3271, AH-006 #3272,
  AH-007 #3273, AH-008 #3274, AH-009 #3275.
  All were **validation_required** at the previous checkpoint;
  verify live status. Add Workbench evidence IDs only after actual save.

## 2026-11-05 commercial strategy and distribution continuation

**New separate development branch:** `wd-papa-5b2e6939-licensing-sustainability-release-checks-20261105`, based on the exact previous Draft PR #30 head `8ab26da637604723e4c29f114cc93a478e0d02f0` (the earlier chain #6 → #20 → #21 → #22 → #23 → #24 → #25 → #26 → #29 → #30 is unmerged). Keep every parent unchanged. Latest source and CI proof must be verified on this new branch/PR; no automatic merge or new Release.

The **LICENSE itself is still GNU AGPL-3.0-only**, granting commercial usage without a mandatory revenue share. Existing `docs/COMMERCIAL-LICENSING.md` already anticipated optional commercial licensing for owned rights; expanded explanation now covers legal ownership, independent services, community contributions, third-party packages, irreversible previously issued AGPL grants and voluntary donations. There is NO signed commercial contract or set fee. Sponsorship link `ko_fi: RIVANOX` already exists in GitHub main; new responsive, prominent `web/index.html` support call-to-action and all five locales explicitly disclaim paywalls and donation-as-license. No payment processing is embedded in AudioHub. README now highlights same optional support and links the latest verified source/image.

**Latest prior verified experimental ARM64 test image:** Draft PR #30 exact SHA `8ab26da637604723e4c29f114cc93a478e0d02f0`, source [42086920486](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086920486) SUCCESS **226 tests**, ARM64 [42086909475](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086909475) SUCCESS **55/55 real rootfs pre-export checks**, checksum XZ+manifest and uploaded artifact [#13443339137](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42086909475/artifacts/13443339137) **606,222,225-byte ZIP, expires 2026-12-05**. The artifact contains PR #30 graph diagnostics, NOT new funding/release-audit UI changes.

**New code in this branch:** `scripts/release_bundle_audit.py` validates strict three-file temporary preview ZIP, image SHA256, XZ decompression, commit and pi-gen manifest provenance, no extra files or forged approval flags, returns immutable `public_release_ready=false`. Integrated into experimental ARM64 CI before preview artifact upload. Fifteen adversarial Python tests plus new five-locale/readme policy tests. `.github/workflows/publish-image.yml` remains **blocked** until real Pi4+Edifier audio, phone secure ownership, 3-way mix, legal/rootfs compliance and owner/CEO publication authorization. No official Releases exist; don't announce a new image until new branch's full native ARM64 CI/ZIP upload has succeeded.

**If chat resets:** verify the newest PR's exact head SHA, CI source run, and any ARM64 build run and artifact. Update canonical docs only after observed result. For monetization: confirm Ko-fi payout operationally and enable the GitHub Sponsor UI *as owner* if required; negotiate specific commercial licenses only with verified RIVANOX code ownership and third-party counsel. Continue Pi4 hardware acceptance + safe phone-owner provisioning in separate owner-verified branches. User requires persistent GitHub updates but not an unreviewed public Release.

**Release-go rule:** source CI is insufficient; image CI is insufficient;
only human-authorized real Pi hardware, owner security, compliance,
reproducible build provenance and release approval may close the gates.


## 2026-11-05 continuation: real PipeWire link observability (Draft PR #30)

Newest isolated stacked **DRAFT**: [PR #30](https://github.com/RIVANOXcom/rivanox-audiohub/pull/30), branch `wd-papa-5b2e6939-live-pipewire-graph-validation-20261105`, parent **PR #29 exact SHA `8077d39d624a5dabc797ca6f6977e6017272a004`**. PR #29 was inspected first and already implements dynamic source-to-slot routing (198 source tests / verified native ARM64 artifact #13441980660), so that work was **not** reimplemented or overwritten. `main` and all peer PRs remain unchanged.

This next step imports previously separate read-only hardware topology preflight PR #13, adds `src/audiohub/audio_graph.py` to inspect actual PipeWire Link `info.output-node-id` / `info.input-node-id` relationships and report observed direct `audiohub.<slot>.output`→selected USB sink links; stereo port links are deduplicated by node-pair. The runtime periodically inspects its existing `pw-dump` snapshot; first-boot FAT report stores only **numeric** counts `pipewire_links_inspected` (0..8192) and `eq_usb_direct_links` (0..3) with no node identifiers or personal data. No sound, pairing, source access, LAN service or owner authentication changes. Negative graph/privacy/real-image-rootfs checks added, and `docs/PIPEWIRE-LINK-OBSERVABILITY.md` describes evidence limitations. Direct-link absence does NOT prove no sound because PipeWire may insert intermediate adapter nodes.

**At next chat:** Look up PR #30 exact head SHA, latest source checks and native ARM64 run. Confirm full test count, 100% rootfs security checks, `sha256sum -c`, `xz --test`, manifest and uploaded temporary artifact **before** claiming a new SD image. Do not reuse artifact #13441980660 as if it includes these new link diagnostics. Update this paragraph with final CI IDs once confirmed. Existing gaps: hardware Pi4+Edifier/BT/3-way test, authenticated owner+phone Wi-Fi, real source enrollment, trustworthy Windows transport, main active ruleset (still empty), legal/official release.

## 2026-11-05 continuation: rootfs package and copyright evidence (separate draft)

New branch `wd-papa-20261105-rootfs-license-inventory` starts from exact
previous draft PR #31 SHA `bb83f7de8a689f59fd2e1cbfcf077040122124ab`.
It collects dpkg package versions/architectures and hashes of available
`/usr/share/doc/<package>/copyright` from the **real built rootfs**,
records missing notices without assuming legal clearance and adds
`ROOTFS-PACKAGES.json` to the unverified ZIP. Its SHA-256 and exact package
counts are bound into `PREVIEW-MANIFEST.json` schema v2 and checked by an
independent strict-allowlist offline verifier. Parent PRs, main branch,
publish-image.yml, AGPL LICENSE and permissions are unchanged.
**Before claiming a build:** check the exact new PR head, source CI, native
ARM64 rootfs/export/integrity status and uploaded artifact ID. Physical Pi4
sound, authenticated phone ownership, license clearance and owner public
Release approval remain OPEN. No official release has been authorized.

## 2026-11-05 Model C licensing decision — resume checkpoint

Owner explicitly chose **Model C**: future RIVANOX-owned source made
viewable/downloadable; personal private non-commercial use free;
commercial/organizational use requires a separately agreed commercial
license. Create new stacked DRAFT from PR #34 exact SHA
`c28a61bea275f8602458c2961e06454430cc4319`, preserving
all parents and `main`, with `LICENSE-C-DRAFT.md`,
`docs/licensing/RIGHTS-AUDIT-2026-11-05.md`, transparent
`docs/licensing/TRANSITION-STATE.json` and fail-closed source CI.
**NOT EFFECTIVE**: historical/current GNU AGPL-3.0-only rights remain
and no SD Release is approved. Need verified RIVANOX legal rights holder
and human/AI/contributor chain of title, third-party complete rootfs
legal audit and qualified German/EU counsel, explicit reviewed future
version and owner signature before any effective switch. A user's
choice of business policy is not a fake proof of legal clearance.
Resume by verifying new Draft PR exact source CI, then keeping
human checkpoints open in Workbench AH-008 #3274 and GitHub Issue #32.

## 2026-11-05 next step: real image inventory export fix and private Model C boundary

Owner asks continued code/dependency review and development consistent with
prospective Model C commercial restrictions. Public `main` remains AGPL;
DO NOT add new commercial-only product features there and do not make a
public PR claiming Model C already operative. GitHub integration lacks an
operator action to create a new GitHub repository / set Private visibility.
Owner must create a separate empty PRIVATE repository with scoped app access;
see `docs/licensing/MODEL-C-PRIVATE-DEVELOPMENT.md`. Do not attempt to
hide history or unilaterally relicense third-party dependencies.

The prior inventory-enabled native ARM64 run #42092547313 built a valid
55/55 audited rootfs (689 dpkg, 631 hashed notices, 58 unresolved) but
**FAILED at deploy/ROOTFS-PACKAGES.json missing**. In isolated next PR,
`scripts/export_rootfs_inventory.py` validates the inventory generated
in pi-gen `work/<build-id>/stage-audiohub/rootfs` and copies verified,
unique, non-symlinked metadata into deploy; adversarial unit tests protect
against stale stages and fake approval. Native ARM64 build and artifact
must be verified at the final exact SHA before claiming success.

## 2026-11-05 build repaired, follow-up doc symlink inspection

Exact PR #36 `a5d11cc6a071baa11520dd9bd41f601520a9af64`,
source run 42098261940 SUCCESS 302 tests, native ARM64 build
42098223599 SUCCESS with real 55/55 rootfs guard checks,
689 packages, 631 copyright hashes, 58 unresolved. Four-file
temporary image ZIP artifact #13447794801 expires 2026-12-05.
`public_release_ready=false`, physical Pi4/Edifier and counsel
review still OPEN. Workbench evidence #2784 saved.

Next separate draft branch `wd-papa-20261105-rootfs-copyright-links`
based on exact PR36 SHA changes **only legacy AGPL compliance tooling**:
recognize one direct, safe sibling /usr/share/doc package directory
link using no-follow FD-based reads; reject multi-hop/absolute/traversal
symlinks. Add source regression tests and rerun ARM64, check actual
copyright hashes/missing count at exact new SHA. **Never treat hashes
as legal approval.** Public main and existing AGPL LICENSE untouched.
Model C product code must await separate PRIVATE repo, owner Issue #37.

## 2026-11-05: Nine notice gaps classified, next exact-dpkg reconciliation

PR #39 exact SHA \`065506961fad34448e75f513d39db684f65c7cd7\`
native ARM64 run #42105112961 **SUCCESS**, 324 Python tests,
55 real rootfs guards, unverified four-file artifact #13452656211.
689 dpkg packages, 680 copyright hashes, 9 unresolved: eight
\`doc_alias_target_link\` multi-hop doc chains and one expected copyright
file absent at \`raspberrypi-net-mods\`. All 49 one-hop shared-doc aliases
passed source/direct-dep metadata checks. This is **not** legal clearance.

New stacked development branch
\`wd-papa-20261105-dpkg-identity-reconciliation\` based exactly on
PR39 SHA strengthens runtime source-vs-inventory consistency:
set-equality of (package,architecture) records, precise installed
version verification, legitimately coinstalled multiarch package support
and bounded *read-only* chain metadata traces. New adversarial tests
cover forged versions and architectures, package additions/removals,
duplicate keys, chain cycles and unsafe targets. Verify the exact
new PR source CI + native ARM64 before claiming these changes run in
the real image. Current AGPL source unchanged; future Model C requires
separate PRIVATE repo and legal signoff.

## 2026-11-05 following PR #42: read-only web filesystem boundary

Owner requested continued AudioHub engineering and detailed future chat
recovery. Parent Draft PR #42 SHA
`76dc6a0900126bb41b4b691bd4782c4553eea4b0` has successful
source run `42109205398`, 354/354 Python tests; 79-source-file pending
Model C provenance ledger and canonical `docs/PAPA_CANONICAL_RESUME_20261105.md`.

On isolated child branch
`wd-papa-20261105-readonly-web-file-hardening` a real security defect
was found: original read-only `webserver.py` allowed fixed URL asset
paths to be opened using `Path.read_bytes()`, following malicious
`/opt/audiohub/web` or asset symlinks and reading files without limits.
The runtime `STATE` JSON was also read without an HTTP-specific size
bound or nofollow check. The change uses `O_NOFOLLOW` for **every**
absolute path component, `O_NONBLOCK` to refuse blocking special files,
regular-file checks and caps of 512 KiB per static asset and 32 KiB for
redacted runtime status. Unsafe/unavailable status is stale/false;
unsafe assets return 503. `scripts/audit_rootfs.py` adds pre-export
checks for nonregular, symlinked and oversized image web files and
required installed server read guards. Regression tests cover those
attacks; the image still does not expose write APIs.

This is legacy AGPL safety maintenance, **not new commercially
restricted Model C feature publication**. Check next Draft PR HEAD
and source/native ARM64 status before claiming completion. Do not
change `main/LICENSE`, publish a stable image, merge unrelated PRs,
or claim legal/physical hardware acceptance.

**2026-11-05 verified source security CI:** follow-up [Draft PR #43](https://github.com/RIVANOXcom/rivanox-audiohub/pull/43), commit `d4fb934ad4ed15cac20a79799d475b2956b94769`, [source run #42111311812](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42111311812) **SUCCESS, 375 Python tests**. Corresponding independent native ARM64 run #42111297565 was submitted and must be checked at that exact SHA before asserting build/test ZIP success. The canonical resume and machine-readable snapshot now list Draft PR #43. Never conflate source CI and Pi-native image validation.

## 2026-11-05 PR #43 native success and PR #44 runtime state hardening

Exact PR #43 SHA `9e92d95a539a6a8e54a2b433b0a6d9bcaf4fa975` source 375/375,
native ARM64 run [42111542474](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42111542474) **SUCCESS**, 57/57 rootfs security checks,
temporary non-release artifact #13454668013; 689 packages / 680 hashes / 9 open
notice paths, legal clearance false, Pi hardware acceptance false.

New stacked [Draft PR #44](https://github.com/RIVANOXcom/rivanox-audiohub/pull/44)
hardens existing `runtime.py` private state read/write: replaces predictable
fixed `.tmp` writes and unbounded, symlink-following JSON reads with user-owned
private directory-FD operations, per-path-component nofollow, bounded 32KiB
regular JSON reads and randomized O_EXCL 0600 fsynced atomic updates. Adds
17 adverse local runtime and 3 image-rootfs regression tests plus a new
rootfs security check; previous count 57, expected 58 only after real
native run. Exact source/native CI for #44 not yet established at this
documentation checkpoint. Existing AGPL rights unchanged; Model C
remains NOT EFFECTIVE pending issue #37 and human legal review.

## 2026-11-05 stacked PR #45 — unexpected supervisor errors stop managed audio

PR #44 source run #42120108827 PASSED 395 Python tests; native run
#42120100453 is independently checked for real 58/58 rootfs guards.
Draft [PR #45](https://github.com/RIVANOXcom/rivanox-audiohub/pull/45)
fixes a separate existing legacy AGPL flaw: in `Supervisor.serve()`,
exceptions from `poll()` were previously silently swallowed,
potentially leaving started `pw-loopback` processes routing without
supervision. The new safe wrapper stops every managed route on error,
clears retries and refuses to suppress a failed cleanup; systemd
KillMode=control-group makes child termination explicit on service
restart. New 9 runtime, 3 rootfs and 1 static service tests were added,
with a new native rootfs security guard (expected count 59 if verified).

Update canonical `docs/PAPA_CANONICAL_RESUME_20261105.md`, GitHub
PR45 and Workbench after precise HEAD source CI and native ARM64 run.
No release, merge, Model C effective license, upstream vendor license
clearance or physical audio acceptance is implied.

## 2026-11-05 PR45 native PASS and PR46 Bluetooth one-use trust guard

[PR45 native ARM64 run #42121261961](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42121261961) **SUCCESS**, exact SHA `7ef7a107199a0b6cbf69f1c0b7d047b1feac5bf1`, source 408 tests, **59/59 real rootfs guards**, temp UNVERIFIED 4-file archive #13459367136, 689 packages, 680 copyright hashes, nine paths unresolved. No public release.

Follow-up [Draft PR #46](https://github.com/RIVANOXcom/rivanox-audiohub/pull/46) hardens the previous Bluetooth agent auto-trust behavior, which accepted arbitrary `Device1 Paired` signal events without prior agent authorization. Exact initial code SHA `f194b7740670c8549599844f5947edb4b1353bb4` has **434 Python tests SUCCESS** via source run #42124595480. A DBus callback-authorized, 45-second, max-two, single-use pending-device policy, exact BlueZ sender origin and actual paired property now gate Trusted; trusted devices still reconnect, unknown untrusted services are denied. New actual Pi-rootfs guard should bring 59 -> 60, **ONLY IF** native build passes. Read canonical section M for risks, evidence and next-chat actions. No owner claiming or production security approval.

## 2026-11-05 PR46 BlueZ timeout hardening after authorization callback fix

Official [BlueZ Adapter properties](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst) confirm setting `DiscoverableTimeout=0` or `PairableTimeout=0` disables expiry. Follow-up PR46 now sets **both to 600 seconds**, disables old Pairable/Discoverable state at agent initialization, and uses a **boot-relative 600-second deadline** instead of starting a new ten-minute interval after every systemd restart. New source CI run [42125422399](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42125422399) SUCCESS **441/441 tests** at code SHA `0852894bde8504606cfdc32252a3c5c075c5771a`; native Pi rootfs guard target **61**, not yet proven at this doc update. See canonical PAPA section N, and verify latest exact-head source/native CI before future chats. Owner security and source/model C approvals remain unverified.

## 2026-11-06: PR #46 native PASS and draft PR #47 bounded PipeWire output

PR46 native ARM64 run #42125593262 verified **SUCCESS 61/61** on exact SHA `c37f309ec42b5a29e8254b76bf57f4f2ff21a1c9`. Source tests 441, unverified 4-file image artifact #13461790759, 689/680/9 OS copyright evidence, public release not ready. New [Draft PR #47](https://github.com/RIVANOXcom/rivanox-audiohub/pull/47) replaces the historical unbounded PipeWire subprocess stdout collection used in `runtime.py` and `hardware_preflight.py` with an incremental 4MiB/timeout capture helper, no shell and process-group termination, plus 8192-object graph limit. New source count **81 rights-pending files**, new native rootfs guard target **62**. Source and image checks pending at new exact HEAD; no physical sound or legal approval. Canonical section O is primary recovery context.

## 2026-11-06: interactive offline operator hardware observations (PR #48)

Parent [PR47 source #42180349159](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42180349159) SUCCESS 460 tests on SHA `24dec6ed2ecde427ff606b77b900620f36cb6469`; native ARM64 run #42180343356 must still be verified. New [Draft PR #48](https://github.com/RIVANOXcom/rivanox-audiohub/pull/48) adds offline `audiohub.manual_acceptance` which, if the PipeWire topology is ready, asks only fixed yes/no/skip physical Edifier speaker, three-input, mute/EQ, USB detach, clipping and independent 24h observations. No stored free text or untrusted device IDs, no network/file writes and no automatic playback. The JSON ALWAYS sets hardware_accepted, release_ready, ownership_authenticated, legal_redistribution_approved and model_c_license_effective to false. New 17 unit tests, four rootfs tests, native guard target 63 after real image confirmation; 83 source files now ledgered with future rights approvals still false. See docs/HARDWARE-OBSERVATION-RUNBOOK.md and canonical section P.

### 2026-11-06 CI evidence correction

PR47 native ARM64 run #42180343356 SUCCESS **63/63**, not projected 62, as installed new process_capture.py counts as a required source check. Its UNVERIFIED artifact #13485144050 expires 2026-12-06. PR48 native target becomes **65** (new manual_acceptance.py installed-file check plus independent no-release manual checklist check), not projected 63. PR48 source run #42181382213 passed 481 tests; latest exact-head native must be validated after docs update. Canonical section P correction supersedes earlier count estimates.

## 2026-11-06: PR48 native 65 PASS and PR49 ambiguous PipeWire topology rejection

Independent [PR48 native #42181839470](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181839470) **SUCCESS 65/65** real ARM64 rootfs safety checks and source [#42181848095](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42181848095) 481/481 tests, exact SHA `aeafb0b06cc781c8470b502fe1ecf3484084696f`; UNVERIFIED temporary image artifact #13485629030 expires 2026-12-06. New [Draft PR #49](https://github.com/RIVANOXcom/rivanox-audiohub/pull/49) fixes first/last-wins ambiguous PipeWire device ID, duplicate logical mixer sink and Bluetooth source MAC selection. An ambiguous virtual sink disables all managed routes; graph and preflight cannot report readiness on repeated Node IDs. Adds 19 source/rootfs adversarial tests, image guard target **66**; initial source Actions [#42200344244](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42200344244) **SUCCESS 500 tests** at SHA `27d13828011a50fff9cd7b664a508e2ffe76ce89`, ARM64 exact-head not yet verified. Read canonical section Q. No AGPL rights changes, public Release, hardware or commercial license approval.

## 2026-11-06: stacked PR #50 — prevent root-owned offline diagnostics from following user-owned symlink ancestors

Parent PR49 exact base SHA `1734042469c52aea21179d7ae40f7287fac5152e` source CI #42200628247 **SUCCESS 500 tests**, native #42200618383 must be checked live for expected 66 actual rootfs guards. New [Draft PR #50](https://github.com/RIVANOXcom/rivanox-audiohub/pull/50) prevents `firstboot_diag._read_runtime` (root-owned system service) from following symlinks through parent directory components, rejects nonprivate/foreign-owned final directories or status files, hardlinks, oversized and malformed input; preserves stale fail-closed privacy-safe status. Eight new runtime tests, four rootfs packaging tests, new actual guard target **67** after successful PR49 native. Initial code SHA `a362b1630e6001478634d2c1f4f6bfde9814a007` source [CI #42201349549](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201349549) SUCCESS 512 tests. Latest source/native exact-head evidence needed after docs commit. Legal owner/Model C and speaker acceptance all blocked.

## 2026-11-06: PR50 native 67-check PASS; Draft PR51 closes LAN receiver unbounded PipeWire capture

PR50 independent exact SHA `275089e3d511e0d6c8fb68e601a9001b13b382b6` source [#42201597233](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201597233) SUCCESS **512 tests** and native Pi ARM64 [#42201589717](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42201589717) SUCCESS **67/67**, temp UNVERIFIED image #13494264314 expires 2026-12-06, rootfs 689 packages/680 copyright hashes/9 missing, public_release_ready false. New [Draft PR51](https://github.com/RIVANOXcom/rivanox-audiohub/pull/51) eliminates unbounded `capture_output=True` for manual, unauthenticated, disabled-by-default Windows Scream UDP test receiver (`network_laptop.py`) in pw-dump and wpctl health checks; reuses 4MiB/5-second capped no-shell/no-stderr process capture; rejects failures before enabling output. Six receiver + four rootfs tests, native target **68**. Source CI [#42208006876](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208006876) SUCCESS **522/522** at code SHA `a4872f0bd66f38e48c1fe24a9f23304d68f76ced`. Exact post-docs HEAD native must be checked. Canonical section S is authoritative resume, no official release, license flip or actual Pi sound approval.

## 2026-11-06: Status HTTP resource limits and privacy fix in Draft PR #52

Parent PR51 SHA `d4fd8053a13618f3f7ad35fb26888288f6586a1d` source CI #42208450554 **SUCCESS 522/522 tests**, native #42208440878 expected 68 actual image guards still to be verified. New [Draft PR52](https://github.com/RIVANOXcom/rivanox-audiohub/pull/52) fixes the loopback-only default status-preview server's unbounded ThreadingHTTPServer worker spawning and inherited request-line logging of URLs/query strings. BoundedStatusHTTPServer caps **8** simultaneous clients, sets **5s** socket timeout, fails closed on saturation, always releases slots after threads, and Handler.log_message does not record raw request data. The explicit unsafe LAN bind exception and read-only API remain unchanged. Nine no-network client tests and four synthetic rootfs guard tests; new native image guard target **69** after parent 68 verified. Initial source Actions #42209328344 SUCCESS **535/535 tests** on code SHA `f120ccaea9d217b317f2048b52844a9c8206b520`; latest source/native exact-head checks necessary after checkpoint update. See canonical section T; no legal or physical device release GO.

### 2026-11-06 source/native CI reconciliation: PR51 and PR52

Parent PR51 exact SHA `d4fd8053a13618f3f7ad35fb26888288f6586a1d` source #42208450554 SUCCESS **522 tests** and [native ARM64 #42208440878](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42208440878) SUCCESS **68/68 actual rootfs guards**, four-file XZ/SHA256 proof, temporary UNVERIFIED artifact #13497588492 (605887450 bytes, expires 2026-12-06T11:20:20Z), 689 packages/680 copyright hashes/9 missing OS files, public_release_ready false. PR52 code/docs SHA `ed9dbc68ccff2e03f2ae123aa066efc69d794971` source #42209656187 SUCCESS **535/535 tests**, native #42209649230 pending/in progress at this update, target **69** actual checks. Update next-chat canonical section T; no public release, secure owner authentication or legal/physical hardware clearance.

## 2026-11-06: PR53 private runtime status file identity in read-only web UI

[Draft PR53](https://github.com/RIVANOXcom/rivanox-audiohub/pull/53) now rejects group/world-readable, foreign-owned and multiply hardlinked runtime JSON as fresh web status; checks the final status directory owner and private mode. The static HTML/JS assets remain 0644-readable. Eight new real helper tests, four rootfs image tests, native guard target **70** (parent PR52 target 69). Initial PR53 source Actions #42210517166 SUCCESS **547/547 Python tests** at code SHA `2206e81d527afc6ce3a9c1a6c813f447b9556e2b`; native run #42210542483 was queued, and parent PR52 native #42209873318 was in progress when first observed. Verify latest CI after docs commit; do not assert new image pass without evidence. PAPA canonical section U is new-chat authority, no physical Pi/Edifier or future Model C rights approval.

## 2026-11-06: PR53 verified; Draft PR54 malformed read-only status inputs

PR53 exact SHA `53e49521bc8fd24a3c622cd07c944c5ccced4287` source #42210835227 **SUCCESS 547/547**, independent native ARM64 #42210825401 **SUCCESS 70/70** rootfs checks, only temporary UNVERIFIED artifact #13499596254 with ZIP SHA256 `243c812f7ad6e407c31f926bcf1729a8993b2f4c2397e6df33c01adf972ca9da` (expires 2026-12-06). 689 installed OS packages, 680 copyright files, nine unresolved. New stacked Draft PR54 on isolated branch `wd-papa-20261106-status-parser-failclosed` makes deeply nested runtime JSON status fail to anonymized stale rather than uncaught RecursionError and malformed HTTP absolute target return 404 rather than uncaught ValueError. Includes adversarial source tests and new native image guard target **71**, pending exact SHA CI. No owner authentication, Model C activation, Pi4+Edifier physical evidence, legal review or official Release. See PAPA canonical section V.

## 2026-11-06: Draft PR55 rejects ambiguous private runtime status JSON

Draft [PR55](https://github.com/RIVANOXcom/rivanox-audiohub/pull/55), isolated branch `wd-papa-20261106-strict-status-json-integrity`, stacks on PR54 SHA `f08aa400f25a1307368c41adb79504fec059c4a3` (source #42219045806 SUCCESS 552/552; native #42219039337 pending at initial checkpoint). Prevent false fresh web health from duplicate JSON members or non-RFC JSON NaN/Infinity; unchanged trusted file ownership and web read-only/loopback controls. Three unit and three rootfs regression checks; new installed-image guard expected total 72 only after native verification. Rights ledger 83 files still all pending. Canonical section W; no AGPL-to-Model-C switch, no product release, no real Pi/Edifier hardware proof.

## 2026-11-06: Draft PR56 total HTTP client lifetime + private error handling

Prior Draft PR54 source #42219045806 552/552 and native #42219039337 **71/71 SUCCESS** at SHA `f08aa400f25a1307368c41adb79504fec059c4a3`, unverified temporary artifact #13502838048. PR55 initially 558/558 source at `76bb3b89e74f15b450fb49deba3e8b6c31f4e477`, but corrected a stale native audit marker on its own branch at HEAD `e7e8751ef1841c148274a2f85aefc950c2219fbb`; exact new source and ARM64 72 pending. New Draft PR56, branch `wd-papa-20261106-status-http-total-deadline-privacy`, adds max 15-second total HTTP worker deadline with shutdown and watchdog cleanup; inherited per-client error traceback/peer logging is disabled. Five live no-socket tests, four rootfs regression tests and one native guard target **73**. Workbench previous evidence #2986/#2987. No legal, physical, Model C or Release GO. See canonical section X.

## 2026-11-06: Draft PR57 hardens root-owned offline diagnostic JSON

New stacked Draft PR57, branch `wd-papa-20261106-offline-diag-json-integrity`, based exclusively on PR56 exact SHA `1e666234b307a249e593b0e5a99b523ccf4af060`. Root-owned offline SD status parser now rejects duplicate object members, NaN/Infinity and deep recursion without creating false USB-health readings or crashing the diagnostic worker. Four actual malformed-input tests plus four installed-image guard tests, new `offline_diag_json_integrity_fail_closed` rootfs check target **74** only if native ARM64 proves it. PR55 corrected source #42220634968 559/559 and PR56 source #42220925947 568/568 SUCCESS; independent native 72/73 pending at initiation. Last confirmed native PR54 71/71. No release, installs, merge, new network access, product ownership, physical Pi/Edifier acceptance, license approval or permissions change. See canonical section Y.

## 2026-11-06: Draft PR58 rejects valid JSON exponent overflow

New isolated stacked Draft PR58, branch `wd-papa-20261106-finite-exponent-status-json`, based on PR57 exact SHA `4a13707416da1e18d3d4ac9e223b18786ef5f0f2`. Both web status and root-owned offline SD diagnostic now reject JSON exponent overflow (`1e999` -> Python Infinity) with `parse_float` and `math.isfinite`; existing literal NaN/Infinity and duplicate key rejection remains. A corrupt status report becomes stale/no USB health; finite exponent metadata stays accepted without identifier disclosure. Four live unit tests, three rootfs synthetic regression tests, one installed-image guard target **75**, requiring new exact-head ARM64 CI. Parent PR55 exact source 559/559 + independent native 72/72 SUCCESS (artifact #13502859856); PR56 source 568/568 + independent native 73/73 SUCCESS (artifact #13504166490). PR57 source 576/576 SUCCESS and ARM64 #42221946079 pending at PR58 creation. Nine OS copyright gaps and real Pi/Edifier, owner authentication, legal and future Model C gates unresolved. No merge, release, install, deploy or permission change. Canonical section Z.

## 2026-11-06: PAPA-18B8B3C6 Draft PR59 private config hardening

Offline input names and source route policy readers now use O_NONBLOCK for unsafe FIFO leaf files, require full fstat-sized bounded reads and reject duplicated or over-nested JSON. Ten real no-hardware tests, six synthetic rootfs tests and two new native checks, 77 expected only after CI. PR57 source 576/576 native 74/74 SUCCESS, PR58 source 583/583 native 75/75 SUCCESS, Workbench #2996/#2997. All stacked PRs remain draft, main unmodified. No hardware/legal/owner authentication signoff or release GO. Canonical section AA.

## 2026-11-06: PAPA-18B8B3C6 Draft PR60 common PipeWire JSON guard

Draft PR60 branch `wd-papa-18b8b3c6-pipewire-json-identity-guard-20261106` stacked exclusively on PR59 exact SHA `0f27789f8b6ce1984e4a818f65bf9ce095b5a38d`. Both USB/BT discovery and EQ/USB Link observations now share the same bounded, duplicate-key-rejecting, finite-number and deep-JSON fail-closed PipeWire parser. Ten no-hardware unit tests and five synthetic rootfs tests add one native guard (expected **78**, not confirmed until CI). Graph nesting is limited to 64 levels and 262144 aggregate values using an iterative walker. PR59 source #42231228004 599/599 PASS and native #42231178394 77/77 PASS, test ZIP #13508977757 (605495982 bytes; sha256 f611a1b41165a591642f7f321a085bd605d4d46f8fc13df311377232977ce123). Workbench evidence #2999. All Draft, no physical Pi4/Edifier, ownership, licensing or public product release GO. Canonical section AB.

## 2026-11-06: Draft PR61 fail-closed private supervisor config JSON

PAPA-18B8B3C6 Draft PR61 on `wd-papa-18b8b3c6-runtime-private-json-integrity-20261106` is stacked on PR60 exact head `3ff954883f6dc254b19a61928883f94e6c1d4f3f`. The actual runtime `settings.json` and Bluetooth assignment `device-channels.json` now reject duplicate members, NaN/Infinity, exponent overflow, invalid shapes or overnested JSON with controlled fallback (32KiB, 64 levels, 8192 aggregate values) while retaining private UID/nlink/nofollow and atomic persistence protections. Six live and four rootfs synthetic tests; native guard target **79** only with exact-head build. Parent PR60 Source #42233692882 614/614 PASS; native #42233681180 pending at initial handoff. No parent/main branch overwrite, physical hardware, owner/third-party rights approval, release, installation or deployment. Canonical section AC.

## 2026-11-06: Final PR60 independent native verification

PR60 exact SHA `3ff954883f6dc254b19a61928883f94e6c1d4f3f`, Source CI #42233692882 614/614 PASS and ARM64 #42233681180 78/78 actual installed rootfs checks PASS; .img.xz checksum and bundle integrity PASS. Temporary UNVERIFIED GitHub artifact #13511741029 (605530653 bytes, ZIP sha256 `cb8daada90a0c56def4dcbcfc60b6ad7debc3034e38787682f49c58dd50dfdf8`, expires 2026-12-06). Still not a product release, Pi4/Edifier physical signoff or Model C approval. PR61 isolates strict supervisor-local JSON config loader and will require independent 79 checks.
