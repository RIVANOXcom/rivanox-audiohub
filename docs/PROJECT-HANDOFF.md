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
