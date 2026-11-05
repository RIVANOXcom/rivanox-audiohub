# RIVANOX AudioHub – authoritative developer handoff

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

**Release-go rule:** source CI is insufficient; image CI is insufficient;
only human-authorized real Pi hardware, owner security, compliance,
reproducible build provenance and release approval may close the gates.


## 2026-11-05 continuation: real PipeWire link observability (Draft PR #30)

Newest isolated stacked **DRAFT**: [PR #30](https://github.com/RIVANOXcom/rivanox-audiohub/pull/30), branch `wd-papa-5b2e6939-live-pipewire-graph-validation-20261105`, parent **PR #29 exact SHA `8077d39d624a5dabc797ca6f6977e6017272a004`**. PR #29 was inspected first and already implements dynamic source-to-slot routing (198 source tests / verified native ARM64 artifact #13441980660), so that work was **not** reimplemented or overwritten. `main` and all peer PRs remain unchanged.

This next step imports previously separate read-only hardware topology preflight PR #13, adds `src/audiohub/audio_graph.py` to inspect actual PipeWire Link `info.output-node-id` / `info.input-node-id` relationships and report observed direct `audiohub.<slot>.output`→selected USB sink links; stereo port links are deduplicated by node-pair. The runtime periodically inspects its existing `pw-dump` snapshot; first-boot FAT report stores only **numeric** counts `pipewire_links_inspected` (0..8192) and `eq_usb_direct_links` (0..3) with no node identifiers or personal data. No sound, pairing, source access, LAN service or owner authentication changes. Negative graph/privacy/real-image-rootfs checks added, and `docs/PIPEWIRE-LINK-OBSERVABILITY.md` describes evidence limitations. Direct-link absence does NOT prove no sound because PipeWire may insert intermediate adapter nodes.

**At next chat:** Look up PR #30 exact head SHA, latest source checks and native ARM64 run. Confirm full test count, 100% rootfs security checks, `sha256sum -c`, `xz --test`, manifest and uploaded temporary artifact **before** claiming a new SD image. Do not reuse artifact #13441980660 as if it includes these new link diagnostics. Update this paragraph with final CI IDs once confirmed. Existing gaps: hardware Pi4+Edifier/BT/3-way test, authenticated owner+phone Wi-Fi, real source enrollment, trustworthy Windows transport, main active ruleset (still empty), legal/official release.
