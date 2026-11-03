# PAPA Workbench traceability

**Project:** `PJ2611-0001:R001` — RIVANOX AudioHub  
**Authoritative project record:** R029 PAPA Workbench  
**GitHub source:** https://github.com/RIVANOXcom/rivanox-audiohub  
**Manual baseline:** 2026-11-03

The project was created manually in Workbench by the owner. The official Workbench project-context readback initially contained no project requirements, decisions, evidence or documents. The engineering requirements below were registered via the Workbench MCP in the confirmed project context.

| Workbench requirement | Scope | GitHub source |
| --- | --- | --- |
| 3267 — AH-001 | Flash-and-boot headless Pi appliance | [Issue 1](https://github.com/RIVANOXcom/rivanox-audiohub/issues/1) |
| 3268 — AH-002 | Three concurrent audio inputs | [Issue 3](https://github.com/RIVANOXcom/rivanox-audiohub/issues/3) |
| 3269 — AH-003 | Independent channel volume, EQ and safe master | [Issue 3](https://github.com/RIVANOXcom/rivanox-audiohub/issues/3) |
| 3270 — AH-004 | English-only project, five app languages | [Localization](LOCALIZATION.md) |
| 3271 — AH-005 | Secure Bluetooth, ownership, phone Wi-Fi setup | [Issue 1](https://github.com/RIVANOXcom/rivanox-audiohub/issues/1) |
| 3272 — AH-006 | Reproducible image and verified release pipeline | [Build logs](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/41730586400) |
| 3273 — AH-007 | Long-running reliability and low SD wear | [Issue 2](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2) |
| 3274 — AH-008 | Licensing / third-party / legal review | [Commercial licensing](COMMERCIAL-LICENSING.md) |
| 3275 — AH-009 | Physical hardware acceptance and release gates | [Issue 2](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2) |

## Limitations

GitHub-to-Workbench synchronization is **not yet implemented**. The Workbench project does not gain native GitHub repository mapping merely because this file contains a link. Internal R029 ticket `RVX-20261103-37A0D80441` (ID 121) requests this feature.

Until proven otherwise, every meaningful technical change requires **manual readback + Workbench evidence**, including source SHA, run URL, test result, blockers and next steps. Do not mistake existing GitHub Actions status for an automatically updated Workbench checkpoint.

## Working method

1. Read exact Workbench project and source state, then open the project session.
2. Queue and claim the next eligible Workbench requirement before development.
3. Commit isolated GitHub changes without overwriting unrelated branches.
4. Obtain exact CI result and record the commit SHA and run ID.
5. Append Workbench evidence, set requirement to `validation_required` or `blocked` if hardware/security acceptance is pending.
6. Read back Workbench state and use that state in subsequent work.

The Workbench currently exposes requirement/evidence MCP actions but not a supported native decision/document-writing action in this connector session. The architecture, decision log and baseline documents therefore live in the source repository, with their verified revision recorded as Workbench evidence.
