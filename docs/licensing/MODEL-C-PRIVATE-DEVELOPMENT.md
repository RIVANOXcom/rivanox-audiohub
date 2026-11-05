# Model C: separated development and launch boundary

**Owner decision:** 2026-11-05. **Status:** operating proposal, not an effective
copyright grant or a commercial invoice. Existing published source remains
AGPL-3.0-only. See [future license draft](../../LICENSE-C-DRAFT.md),
[rights audit](RIGHTS-AUDIT-2026-11-05.md) and
[third-party review](THIRD-PARTY-REVIEW-2026-11-05.md).

## Why a separate PRIVATE repo is the prudent next step

A public GitHub project exposes new commits, pull requests, Actions logs and
source code before the planned Model C legal terms are ready. Simply adding
a different branch or deleting old commits **does not** make that branch
private or revoke AGPL rights already issued. GitHub public->private
conversion does not render detached public forks private either.

**Preserve** `RIVANOXcom/rivanox-audiohub` with its actual AGPL legal history,
unmerged draft PRs, CI evidence, open hardware risks and licensing
disclosures. Use it **only for narrowly scoped maintenance, transparency
and legacy AGPL compliance** until the separate business model has a
verified rights-holder, effective license and distribution process.

### Operator action (GitHub owner)

1. On GitHub, create a **new empty PRIVATE** repository under the intended
   rights-holding account, suggested name `rivanox-audiohub-next`.
   **DO NOT** create a public fork; a GitHub fork can preserve the parent
   network and history. Keep the initial repository empty.
2. Explicitly check `Settings → General → Danger Zone / visibility` and
   ensure **Private**. Limit collaborators to the owner and separately
   authorized development identities. Enable branch protection/ruleset for
   `main`, reviewed PRs, required source checks and no direct force-push.
3. Connect the new private repository to the development integration
   with **repository-scoped** permissions, not a blanket organization token.
   Confirm that the assistant can read/write its test branch and cannot
   publish external releases or adjust admin permissions without authorization.
4. Do not bulk-copy the public AGPL repo into the new repo and call it
   proprietary. First establish a file-by-file rights manifest and
   review which original code may be **independently** relicensed by the
   correct rights holder; preserve all relevant prior rights and notices.
   For any unverified third-party source, exclude or obtain permission.
5. Develop NEW proprietary/source-available product features in the private
   repository after that rights selection, keeping branch history isolated.
   Required CI uses original source tests and no production releases,
   nonpublic artifacts, no test secrets, no license approval auto-flags.
6. When legally ready, activate reviewed Model C only from a **new
   designated** version + commit with complete third-party notices,
   effective license, installation terms and explicit owner/counsel
   approval. Make a separate owner-approved public mirror/download
   repository with its own appropriate history and versioned license.
   Do not import third-party OS/firmware into `LICENSE-C` scope.

**Boundary:** creating a private repository is not the same as acquiring
exclusive rights in AI-generated source, an AGPL-covered third-party
contribution or a copyleft-derived combined program. Counsel must review
the actual facts for the future source tree.

## Automation that is deliberately impossible today

The currently connected GitHub integration has source branch/file/PR
operations, but **no action to create a new GitHub repository or set
its visibility**. Therefore no private project has been created by this
engineering work. Do not claim that work has moved to private storage.
The owner's GitHub UI action above is a real operational prerequisite.

## Legacy AGPL compliance work still permitted

- Fix the legacy unverified image's missing package inventory export in
  `scripts/export_rootfs_inventory.py` and verify the *real* final
  `stage-audiohub/rootfs` evidence without shipping an image publicly.
- Inventory all package copyright paths (the prior ARM64 build detected
  689 installed / 631 hashed / 58 unresolved); investigate all 58 rather
  than calling them violations or clean.
- Record precise dependencies and contractual licenses, correct
  third-party notices and independent copyright ownership.
- Preserve existing AGPL LICENSE, code headers and old public grants in
  this repo, and never rewrite `main` merely to hide AGPL history.
- Maintain release NO-GO until real Pi4/Edifier sound, secure owner
  setup, compliance approval and explicit separate publication signoff.

**References:** [GitHub repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility),
[Debian Policy 12.5 copyright](https://www.debian.org/doc/debian-policy/ch-docs.html#copyright-information).
