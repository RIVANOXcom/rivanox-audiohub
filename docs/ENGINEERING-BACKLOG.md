# AudioHub engineering backlog, defects and optimization register

**Last reviewed:** 2026-11-05. Project `PJ2611-0001:R001`.
This is the persistent, GitHub-readable task register for continued PAPA
development. Status must always refer to **which branch and evidence**
were verified; a green draft PR or GitHub Actions artifact is never a
hardware acceptance or a product release. Workbench tracks AH-001..009
requirements and validation leases. Keep this file, PR descriptions and
issue links synchronized when a task changes.

Legend: `IMPLEMENTED-DRAFT` = code exists only on an unmerged branch;
`SOURCE-CI` = tests passed in a named run; `HARDWARE-OPEN` = physical
test absent; `BLOCKED` = a specific trust/decision dependency exists.
No entry is `DONE` until its acceptance criteria are evidenced.

## P0: cannot ship without these gates

| ID | Current evidence / defect | Next executable action | Acceptance |
| --- | --- | --- | --- |
| SECURITY-01 | Public repo `main` has no effective ruleset (API `[]` on 2026-11-05). | Owner applies [GitHub ruleset guide](GITHUB-SECURITY-RULESET.md), verifies active main target, PR + Source checks and zero bypass. | Direct pushes/force-push/delete to main blocked; PR CI continues. |
| BOOT-01 / AH-001 | Firstboot status binds to loopback in draft PR #15 and integrated image chain, but ownership claim and phone setup are absent. | Decide physical/out-of-band owner proof, implement authenticating API and recovery without shared default passwords, test attack paths. | Owner-only initial claim, replay/rate/CSRF/session/recovery security and real phone proof. |
| OWNER-01 / AH-005 | Offline physical-claim policies, durable records and Ed25519 sketches in draft PRs #5/#16/#17/#18; no verified owner onboarding. | Threat-model pairing race, device proof and secure first-claim transport; integrate isolated owner identity with UI. | Real owner claim and nonowner rejection on Pi, durable/reboot/recovery success. |
| AUDIO-01 / AH-009 | Pi image build and USB/A2DP routing tests exist; **no actual Pi4 + Edifier playback report**. | Flash [latest experimental 3-channel image](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057278883/artifacts/13428684879) on spare SD; isolated phone→BT→Edifier test, review `AUDIOHUB-TEST-REPORT.json` (no credentials). | Audible playback proven with hardware notes, preflight, 10 reboot/unplug tests. |
| SEC-LAN-01 / AH-002 | Scream UDP 48 kHz source is bundled but OFF; its IP filter is spoofable, no encryption or sender authentication. | Choose authenticated Windows transport or isolate/manual-only engineering mode; prohibit auto listener. | Only enrolled sender accepted; negative network replay/spoof and loss tests. |
| AUDIO-02 / AH-003 | 3-source gain budget integrated draft #24/#25; **not a measured limiter**. | Lab full-scale summed peak measurements; implement actual safety limiter or keep conservative restricted controls. | No unsafe clipping in real three-way stress tests with Edifier and USB output. |
| COMPLIANCE-01 / AH-008 | Source package inventory draft #14, actual exported rootfs SBOM and licensing incomplete. | Extract binary/package SPDX SBOM from built rootfs, audit firmware/Codecs and MS-PL Scream driver distribution (currently NOT bundled). | Reviewed third-party notices, obligations and EU/DE hardware/software applicability. |
| RELEASE-01 / AH-006 | Native ARM64 Actions image is **UNVERIFIED ALPHA**; 0 official GitHub Releases. | Build from reviewed integrated SHA, signed/reproducible provenance, hash, archive/legal/security scan and owner release gate. | Verified hardware, security, compliance, signed digest and owner-approved official release. |

## P1: next product functionality / UX

| ID | Current state | Next action and acceptance |
| --- | --- | --- |
| INPUT-01 / AH-004 | New draft input naming model under development: stable technical slots `music/laptop/tablet` display as Input 1–3; labels can be browser-local and safely set by local audiohub CLI, **no owner API**. | Implement owner-authenticated save/sync, link browser/device state, editable default names, migrations and restarts; no label leakage in public status. |
| INPUT-02 / AH-002 | **IMPLEMENTED-DRAFT PR #29:** offline source-routing policy assigns two explicit Bluetooth peers and the manually enabled LAN source to any three distinct internal EQ slots; local file lock, strict perms, conflict rejection and fail-closed runtime enforcement. **Not an owner-authenticated UI nor proof that Bluetooth peers are trusted.** | Complete owner-verified enrollment/CSRF + phone UI, real Pi4 two-A2DP and manual LAN bench acceptance. See [routing lab guide](FLEXIBLE-SOURCE-ROUTING-LAB.md), [Issue #27](https://github.com/RIVANOXcom/rivanox-audiohub/issues/27). |
| UX-01 / AH-004 | Five-language `en/de/es/fr/it` UI is a browser preview; volume/EQ buttons are **not live audio controls**. | Authenticated owner API with CSRF, validated mixer changes, state-sync and optimistic concurrency; accessible phone-first tests in every locale. |
| WIFI-01 / AH-001 | No secure headless phone Wi-Fi setup, no lost-network recovery. | Physical bootstrap and authenticated provisioning in isolated local channel; never store/share credentials in GitHub or boot-partition diagnostic. |
| BT-01 / AH-005/AH-009 | Pi4 dual-A2DP receiver capability never tested. | Test two independent actual senders; if not supported, verify USB BT dongle or alternate network input. |
| WIN-01 / AH-002 | External Windows Scream driver must be installed/unicast manually; no automated safe setup. | Propose supported authenticated Windows client/protocol, installer/legal review, onboarding and reconnect tests. |
| EQ-01 / AH-003 | Three individual filter-chain EQ virtual sinks generated at install time; change propagation not user-controlled. | Safe atomic EQ update path and no-glitch reload under authenticated owner; test clipping and real graph routing. |
| STATUS-01 / AH-009 | SD offline 10-minute report source+image exist; physical execution not witnessed, file absent may be ambiguous. | Test FAT mount, one-shot sandbox, timestamps and recovery; add identifiable but privacy-safe failure states without MAC/SSID. |
| IO-01 / AH-007 | Recovery and backoff source tests; intermittent real USB and BlueZ behavior unmeasured. | Stress hotplug/power loss/wrong default sink, threshold alerts and small logs. |
| RADIO-01 | Internet radio/favorites is UI-only, not implemented. | After owner/wifi trust, add safe user-managed streams and media catalog, avoid uncontrolled metadata fetch. |

## P2: quality, maintenance and developer operations

| ID | Problem / optimization | Acceptance |
| --- | --- | --- |
| CI-01 | Source-checks workflow uses `actions/checkout@v4` / Node 20 runtime; prior GitHub deprecation warning. | Evaluate compatible current pinned SHA dependencies; update after trusted CI, no blind workflow rewrite. |
| CI-02 | Image artifacts expire (~30 days) and require GitHub login, missing from Releases by design. | README latest artifact, SHA, provenance and retention always linkable; never claim verified release. |
| CI-03 | Large number of **stacked, unmerged draft PRs** on older `main` complicates review. | Owner-approved dependency-ordered integration after hardware/security readiness; avoid destructive rebases or clobbering branches. |
| DOC-01 | README/old roadmap may still cite a 4 Nov artifact or unverified image as pending, and the naming used to imply mandatory phone/laptop/tablet. | Keep docs/PROJECT-HANDOFF.md, README, issues and this backlog synchronized at each verified CI/PR checkpoint. |
| TEST-01 | Mocked PipeWire tests do not validate on-device `pw-loopback` command compatibility, WirePlumber rule, `pw-cat` player or real EQ graph. | Capture redacted Pi4 graph and verify actual output/latency with accepted hardware. |
| TEST-02 | No long-run fault injection, 24h uptime, thermal/power, low-memory or SD endurance test. | 24h reliable playback and recovery with measured evidence. |
| SEC-02 | Rename API must never be added unauthenticated to loopback-only status service, and labels should not be treated as owner identity. | Tests prove public API read-only/redacted, file private 0600, no symlinks/control chars. |
| SEC-03 | Ensure GitHub App permission scopes remain least-privilege and public images do not contain secrets; no ruleset bypass. | Human repository admin verifies permission list and exported rootfs scan. |
| LOCALIZATION-01 | Five supported languages need parity, rename error/status messages and screen-reader review. | Automated keys parity + real keyboard/screen reader/mobile checks. |
| LEGAL-01 | AGPL/commercial dual licensing policy and voluntary support need separate distribution review. | Legal applicability and accurate third-party attribution documented before distribution. |

## Source evidence and dependency map

- Main unchanged at `84303e22b14da9e876ec6288af376671fd9898a9` when checked 2026-11-05; no GitHub Releases.
- Earlier audio/first-boot security drafts #5–#10 and #13–#18 are **not** automatically included in main.
- Windows prototype chain #11 → #12 → #19: manual-only Scream receiver and bounded PCM buffer.
- Native preview / security / diagnostic / audio integration chain:
  **#6 → #20 → #21 → #22 → #23 → #24 → #25** (all stacked **draft**).
- PR #25 source SHA `ed89d4ede47cf026d4dc49a41bc8088207dbe4d1`:
  GitHub [source CI 42057376647](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057376647) **159 Python tests SUCCESS**;
  [ARM64 image CI 42057278883](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057278883) **SUCCESS**, **48/48 rootfs checks**, ZIP [#13428684879](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42057278883/artifacts/13428684879), exp. 2026-12-05.
- Independently reviewed gain safety PR #9 is ported into draft #24; BT ownership challenge drafts #16–#18 are **not equivalent** to working phone setup.
- **PR #26** separate stacked naming/handoff branch SHA `9e612290841ed586effc19ca37d2edab479d4524`, CI [42064478374](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064478374) SUCCESS 172 tests; native ARM64 [42064465468](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064465468) SUCCESS 50/50 rootfs, [artifact #13433476966](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42064465468/artifacts/13433476966) (expires 2026-12-05).
- **PR #29** new stacked flexible source bindings (offline local routing policy and synthetic 3-channel tests), based exactly on PR #26. Source CI must be reverified on its final head before claiming success; a new ARM64 image is needed to contain the change. No explicit route assignment via phone, no owner authentication, no Pi4 hardware evidence.
- **Active stack:** #6 → #20 → #21 → #22 → #23 → #24 → #25 → #26 → **#29**, all **unmerged drafts**, main untouched.
- Follow-up issues opened specifically for the current user requirements: [#27 owner-verified input names and routing](https://github.com/RIVANOXcom/rivanox-audiohub/issues/27) and [#28 owner-only main branch ruleset setup](https://github.com/RIVANOXcom/rivanox-audiohub/issues/28).
- Primary issues: [#1 security onboarding](https://github.com/RIVANOXcom/rivanox-audiohub/issues/1), [#2 physical Pi/Edifier](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2), [#3 audio/network](https://github.com/RIVANOXcom/rivanox-audiohub/issues/3), [#4 authenticated web UI](https://github.com/RIVANOXcom/rivanox-audiohub/issues/4).

## Resume protocol after a lost chat

1. Read [PROJECT-HANDOFF.md](PROJECT-HANDOFF.md) and this ledger; verify live PR heads, CI conclusions, artifact expiry and `main` (do not trust stale SHA).
2. Open PAPA Workbench session `PJ2611-0001:R001` and claim the next truly open AH requirement without overwriting a concurrent lease.
3. Select the **exact, last verified stacked head** and create a **new branch**; never blindly update an active peer PR or merge to `main`.
4. Fix source + tests + documentation, get actual GitHub CI run/commit SHA, only claim image if the complete native ARM64 artifact upload and checksum succeeded.
5. Attach evidence to PR, relevant issue and Workbench. Update next action, blocker and source hashes in this file and PROJECT-HANDOFF.
6. All physical Pi4/Edifier, security, release, settings/permissions and deployment gates remain human-authorized. Never claim hardware PASS or release from code tests alone.
