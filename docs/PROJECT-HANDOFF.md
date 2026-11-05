# RIVANOX AudioHub – authoritative developer handoff

**Last synchronized:** 2026-11-05, project `PJ2611-0001:R001`,
MissionPilot WD_JOB `PAPA-5B2E6939`.
**Read this file first when a chat breaks.** Then open
[ENGINEERING-BACKLOG.md](ENGINEERING-BACKLOG.md),
[GITHUB-SECURITY-RULESET.md](GITHUB-SECURITY-RULESET.md)
and GitHub [PR #26](https://github.com/RIVANOXcom/rivanox-audiohub/pull/26)
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

## Latest verified build before the current naming change

**PR #25** `wd-papa-5b2e6939-three-input-laptop-integration-20261105`
head `ed89d4ede47cf026d4dc49a41bc8088207dbe4d1`:
[CI 42057376647](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057376647)
**SUCCESS, 159 Python tests**;
[native ARM64 42057278883](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057278883)
**SUCCESS, 48/48 rootfs checks**, verified compressed image SHA256,
XZ integrity and provenance manifest.
[Temporary test ZIP artifact #13428684879](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057278883/artifacts/13428684879)
(604,922,855 bytes; expires **2026-12-05**; GitHub sign-in).
It contains `.img.xz`, `SHA256SUMS.txt`, `PREVIEW-MANIFEST.json`.
The image is **UNVERIFIED, NOT a release**, no Pi boot/audio evidence.

**Current development branch (new):**
`wd-papa-5b2e6939-configurable-input-names-and-handoff-20261105`,
[stacked draft PR #26](https://github.com/RIVANOXcom/rivanox-audiohub/pull/26)
based on PR #25's exact head. It adds **neutral Input 1–3 labels**,
editable personal UI names persisted **in browser localStorage only**,
a separate **private local audiohub console** name-storage model,
five UI locales, rootfs safety guards and tests. The private Pi CLI
is `python3 -m audiohub.input_profiles show` or
`python3 -m audiohub.input_profiles set music "Wohnzimmer-TV"`
(as the `audiohub` Linux user, on a physically controlled console).
Neither interface changes physical source mapping; real authenticated
phone owner UI and transport assignment remain backlog items.

**Important:** Before marking PR #26 deliverables CI-validated,
look up its **exact latest head SHA**, CI Source checks run, test count,
and if triggered, full ARM64 export/checksum/manifest/ZIP upload.
The image artifact from #25 does **NOT** contain #26's new labels.
If the new branch lacks a verified artifact, do not link #25's
artifact as if it contained the changes.

## Branch graph (preserve all parallel work)

- `main` → legacy separate unmerged drafts #5–#10.
- Legacy Windows Scream source-only drafts **#11 → #12 → #19**.
- Original USB hardware preflight **#13**, package inventory **#14**.
- Original localhost web guard **#15**, owner state/claim **#16 → #17 → #18**.
- Image/functional integration stack:
  **#6 → #20 → #21 → #22 → #23 → #24 → #25 → #26**.
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
BlueZ first/second A2DP may feed music/tablet if hardware supports
two streams. A dormant manual Scream LAN receiver (not encrypted or
authenticated) can feed `audiohub.laptop`. The source code enforces
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
