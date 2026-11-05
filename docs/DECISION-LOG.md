# AudioHub decision log

These decisions capture user-confirmed requirements and current engineering architecture. The **Decision** section is binding for the current project baseline; a subsequent verified change should add a new record rather than silently rewrite history. Every implementation remains subject to required security, compatibility and license checks.

| ID | Decision | Status | Reason / qualification |
| --- | --- | --- | --- |
| ADR-001 | Official target hardware is Raspberry Pi 4 and Edifier R600USB USB speaker. | Accepted | Existing owner hardware, digital USB output intended. |
| ADR-002 | Distribution UX is **flash one image → insert card → connect speaker and power → Bluetooth pair → play**. | Accepted | No monitor, keyboard, SSH or Linux administration for normal use. |
| ADR-003 | Three simultaneously mixable logical audio channels, each with separate volume, mute and EQ, plus master volume. | Accepted target | Physical concurrency and master limiter remain to be proven. |
| ADR-004 | Phone input uses standard Bluetooth A2DP. Laptop prefers robust LAN/WLAN audio or optional cable. Tablet uses a supported independent BT or network input. | Accepted target | Do not guarantee two concurrent BT streams until tested. |
| ADR-005 | A lightweight PipeWire/BlueZ-based headless runtime is preferred over a full Android installation. | Accepted architecture | Keep audio independent from web UI and allow unattended recovery. |
| ADR-006 | GitHub project language is **English only**. | Accepted | Includes README, docs, issue/PR templates, code comments, project notes and Workbench engineering records. |
| ADR-007 | Application UI languages are **en, de, es, fr, it**. | Accepted | English fallback, automatic browser selection, user override, accessibility parity. |
| ADR-008 | Original eligible RIVANOX code is **AGPL-3.0-only** with an optional **separate paid commercial alternative**. | Accepted licensing policy | AGPL users, including commercial users, need not pay. Only RIVANOX-owned rights may be relicensed; third-party obligations remain. |
| ADR-009 | Public project is **powered by RIVANOX**, with links to https://rivanox.com and voluntary https://ko-fi.com/RIVANOX support. | Accepted | Donations do not include a license or guarantee support priority. |
| ADR-010 | Project identity in PAPA Workbench is **PJ2611-0001:R001**. | Accepted | Source is github.com/RIVANOXcom/rivanox-audiohub; native GitHub/Workbench sync is missing (internal ticket 121). |
| ADR-011 | Official GitHub Releases contain only verified images, checksums and notes. | Accepted release policy | Unverified CI build artifacts are short-lived, conspicuously labeled, and are not stable releases. |
| ADR-012 | First boot, pairing, network setup and administrative actions must be secure without a globally shared default secret. | Accepted release requirement | Ownership-claim UX not yet delivered. Release blocker. |
| ADR-013 | Store live runtime status in a volatile location and persist settings sparingly. | Implemented design | Reduce microSD writes and improve uptime. |
| ADR-014 | No silent assumptions about compliance, third-party licenses or EU/DE legal suitability. | Accepted | A reviewed software bill of materials, license notices and applicability assessment are release gates. |
| ADR-015 | Three mixer inputs are **generic, individually renameable logical slots**, not mandatory phone/laptop/tablet product categories. | Accepted product requirement 2026-11-05 | Keep existing technical PipeWire keys for compatibility; browser-only previews and offline private labels precede a secure owner-synced API. Dynamic real source/transport reassignment remains unimplemented until authorized, tested. |
| ADR-016 | An untrusted, unauthenticated Scream UDP receiver must never be auto-started by Pi image installation. | Existing security boundary | Manual isolated lab opt-in only, until an authenticated transport/owner API is reviewed. |
| ADR-017 | `main` must use an active, main-only PR+CI ruleset with no AI app bypass. | Proposed for operator action; not yet configured | Current repo ruleset query returned `[]`; only authorized owner enables protection, no permission changes by engineering agent. |
| ADR-018 | Actual A2DP and manually opted-in LAN sources may be assigned to any distinct pair/remainder of the three stable EQ slots, **independent of display labels**. | Source-only engineering implementation, Draft PR #29, physical/owner security validation pending | Private offline policy reserves one manual LAN slot and up to two eligible Bluetooth sources in remaining slots; no automatic unsafe network exposure or proof of trusted device identity. |

| ADR-019 | Maintain the existing AGPL-3.0-only grants, prominently offer **optional** Ko-fi community support, and explore separately negotiated paid commercial rights for eligible RIVANOX-owned code. | Confirmed monetization direction; contractual details pending legal review (2026-11-05) | Commercial AGPL use has no automatic royalty. Contributions and third-party software cannot be relicensed without necessary rights. No paywall or automatic payment. |
| ADR-020 | Build an immutable, fail-closed **offline preview-bundle audit** before any future GitHub Release workflow may be considered. | Engineering implementation, not release authorization | Verify exact compressed image SHA256/XZ, source/pi-gen provenance, no unexpected files or forged hardware PASS; always set public_release_ready=false. Real hardware, compliance, secure owner setup and CEO authorization still mandatory. |
| ADR-021 | Make an optional, accurately explained Ko-fi support section prominent in all five UI languages, while preserving download and open-source functionality without donating. | Historic accepted direction, superseded for future licensing only | Donations remain voluntary; historical AGPL rights persist. |
| ADR-022 | **Owner chooses Model C for future eligible RIVANOX-owned code**: free private non-commercial permission; business/commercial use requires separate written licensing. | Accepted business direction, **NOT EFFECTIVE** | Supersedes ADR-008 only as future policy. Current AGPL-3.0-only LICENSE remains operative; existing AGPL grants irrevocable per their terms. A draft is not an effective license. Must verify chain of title, AI-assisted rights, dependencies/copyright, legally approved contract, actual owner signature and version/tag before changing source license. Not OSI open source. |

| ADR-023 | Preserve historical public AGPL grants and make a **new PRIVATE repository** the boundary for future eligible Model C product features. | Accepted strategy; **owner setup pending** ([issue #37](https://github.com/RIVANOXcom/rivanox-audiohub/issues/37)) | No force-rewriting prior commits, no public fork presented as private, no bulk relicensing without file-by-file chain of title. Current GitHub integration cannot create a private repo. |
| ADR-024 | Maintain a **canonical PAPA resume** and complete pending-rights ledger in CI for legacy AudioHub source during license transition. | Technical requirement implemented in isolated Draft [PR #42](https://github.com/RIVANOXcom/rivanox-audiohub/pull/42), not legal approval | Source file inventory must cover every current application/build/test/CI source with all copyright, third-party and Model C authorizations false until independently verified. Handoff must record exact GitHub SHAs, run IDs, risks and next-chat instructions. |

## Engineering observations (not product acceptance)

- Source-level tests and policy checks have succeeded on GitHub Actions.
- Native ARM64 `pi-gen` completed a development image build in run [41730586400](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41730586400), producing `image_2026-11-03-AudioHub-Pi4-UNVERIFIED.img.xz` during CI.
- Run 41730586400 **failed** at SHA256SUMS creation due to filesystem permissions; it did not upload an image.
- A subsequent isolated preview-build workflow stages the image in a writable `dist/` directory and checks SHA256/XZ integrity. Its outcome must be checked before marking artifact delivery complete.
- USB output detection, virtual PipeWire EQ config and Bluetooth runtime routines currently have test coverage at the software level, not proven stable hardware routing.

## Change control

Link future decisions to Workbench requirement IDs, source commit SHA, GitHub issues, CI run IDs and specific hardware results. Record superseding decisions explicitly. Do not imply that GH issue closure automatically updates Workbench.
