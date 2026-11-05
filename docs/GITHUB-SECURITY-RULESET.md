# GitHub main-branch ruleset – operator setup (2026-11-05)

**Scope:** `RIVANOXcom/rivanox-audiohub` on GitHub.com, PAPA `PJ2611-0001:R001`.
**Observed on 2026-11-05:** public repository, default branch `main`, GitHub
Rulesets API returns `[]`; the repository UI explicitly warns that `main`
is not protected. User's screenshot shows a **new, disabled** ruleset form
without target branches. Nothing was changed remotely by this engineering PR.

## Exact operator configuration

Navigate to **Repository → Settings → Rules → Rulesets → New branch ruleset**
(the page already shown in the screenshots). Set:

| GitHub control | Value | Why |
| --- | --- | --- |
| Ruleset name | `Protect main – PR + Source checks` | Unambiguous and project-specific |
| Enforcement status | **Active** | Disabled rulesets protect nothing |
| Bypass list | **Empty** initially | AI apps, administrators and owners should not bypass merge checks silently |
| Target branches → Add target | **Include default branch** or exact branch `main` | Avoid blocking separately named draft/feature branches |
| Restrict deletions | **On** | Protect branch from deletion |
| Block force pushes | **On** | Prevent rewriting accepted history |
| Require a pull request before merging | **On** | Code goes through visible PR with CI/review |
| Require status checks to pass | **On** | Require the existing **Source checks / documentation-and-safety** job (select the exact check name offered by the UI) |
| Require conversation resolution before merging | **On** if available | Address review comments before promotion |
| Require linear history | Optional **On** | Prefer squash/rebase merges, only if your merge strategy is compatible |
| Require signed commits | **Off for now** | Enable only after human and automation commit signing are configured and verified |
| Require deployments to succeed / code scanning | **Off for now** | No production deployment and no mandatory scanner gate is proven yet |
| Required approving reviews | **0 while one-person development**; **1** once a second authorized reviewer exists | A sole PR author cannot self-approve GitHub review; setting 1 prematurely can deadlock normal integration |

Then click **Create** and verify that the ruleset appears **Active** and
targets **main**. On GitHub's branch overview, the unprotected-main warning
should disappear when the relevant rules are enforced. Do not rely on the
ruleset name alone: inspect its enforcement and target match.

For required status checks: the repository workflow
`.github/workflows/source-checks.yml` defines workflow **Source checks**
with job **documentation-and-safety**. GitHub normally displays this as
`Source checks / documentation-and-safety` in PR checks. Pick the exact
recently reported check, not a guessed alternate name. Run it on the PR
head and test that an intentionally non-green or unreviewed PR cannot be
merged into `main`. The larger native ARM64 image workflow is presently
an **experimental** branch-scoped preview; do not require that job for all
PRs until its availability, trusted provenance, runner security and release
gates are decided.

## Preserve the assistant's GitHub development access safely

The connected GitHub App can continue to create feature branches,
commits, draft PRs, issues and documentation under its current explicitly
authorized permissions. It **does not need** a ruleset bypass, admin
rights, Actions secrets, or an unrestricted token to do that. Keep
`main` writes gated by a pull request, successful checks, and an
owner-approved merge. Never add the AI/app actor to the ruleset bypass
list solely for convenience.

Under **Settings → Integrations → GitHub Apps**, review the installed
app's **repository access** (only repositories it needs) and permissions.
Aim for only the needed read/write scopes for **Contents, Issues and Pull
requests**, plus read of **Actions/Checks** where available. Do not grant
Secrets, Administration, organization-wide or billing permissions to
resolve a code review bottleneck. Existing permissions must be read
before changing them; do not revoke the current connector blind.

Under **Settings → Actions → General**, use workflow token defaults with
**read-only repository contents** unless a specific release workflow
needs scoped write permission. In workflow YAML, declare explicit minimum
`permissions:` and review external third-party Actions; use a protected
release environment and manual owner approval only after a release
workflow is designed. Never store Wi-Fi credentials, pairing keys,
private certificates or API tokens in the public repository or CI logs.

The repository is **PUBLIC**. Confirm this is intentional before
publishing future artifacts: code and public issues/PRs are readable to
everyone; temporary Actions image artifacts may require GitHub sign-in,
but must not be treated as a secret store. Recheck uploaded SD images for
private keys, credentials and personal data even when behind login.

## Verification checklist (operator)

- [ ] Ruleset is **Active** and target is **main**
- [ ] Deletion and force-push prevention enabled
- [ ] PR required before merging; Source checks required by correct name
- [ ] No app/admin blanket bypass
- [ ] Feature-branch draft PR creation and CI still work
- [ ] Direct push to `main` fails; approved PR merge remains possible
- [ ] Required-review count matches the real reviewer team
- [ ] GitHub App access remains least-privilege; no extra admin/secrets grant
- [ ] `main` branch protection confirmed after creation (not just screenshot)

**Change authority:** Only the repository owner/operator enables or
changes GitHub rulesets, app authorizations, release permissions and
deployments. This document is guidance, NOT a recorded approval or
evidence that protection was actually applied.

Tracking: SECURITY-01 in [engineering backlog](ENGINEERING-BACKLOG.md).
