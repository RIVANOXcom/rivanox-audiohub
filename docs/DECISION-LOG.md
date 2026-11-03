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

## Engineering observations (not product acceptance)

- Source-level tests and policy checks have succeeded on GitHub Actions.
- Native ARM64 `pi-gen` completed a development image build in run [41730586400](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41730586400), producing `image_2026-11-03-AudioHub-Pi4-UNVERIFIED.img.xz` during CI.
- Run 41730586400 **failed** at SHA256SUMS creation due to filesystem permissions; it did not upload an image.
- A subsequent isolated preview-build workflow stages the image in a writable `dist/` directory and checks SHA256/XZ integrity. Its outcome must be checked before marking artifact delivery complete.
- USB output detection, virtual PipeWire EQ config and Bluetooth runtime routines currently have test coverage at the software level, not proven stable hardware routing.

## Change control

Link future decisions to Workbench requirement IDs, source commit SHA, GitHub issues, CI run IDs and specific hardware results. Record superseding decisions explicitly. Do not imply that GH issue closure automatically updates Workbench.
