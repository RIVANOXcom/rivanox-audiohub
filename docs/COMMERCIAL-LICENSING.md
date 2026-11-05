# RIVANOX AudioHub: open-source rights and commercial licensing

**Status:** Public policy explanation, not a commercial license agreement,
price list, trademark registration, or legal clearance. Reviewed 2026-11-05.

## What the existing LICENSE actually grants

The repository's complete [LICENSE](../LICENSE) is **GNU AGPL-3.0-only**.
It is an open-source license and expressly permits **commercial use**,
commercial redistribution, modification, and selling copies if the
license terms are met. A company following AGPL-3.0 does **not**
automatically owe RIVANOX a fee, royalties, revenue share or donation.
We cannot unilaterally retroactively withdraw rights already granted
for versions validly obtained under AGPL-3.0.

Broadly, redistribution of covered versions triggers license notices,
corresponding source availability and copyleft obligations. For covered
modified network software, AGPL section 13 includes an additional
source-offer requirement to remote users. The actual scope of a combined
work, internal use, aggregated independent packages and exceptions
must be assessed on its specific technical and legal facts; simply
using a program at work does not itself incur a royalty.

## RIVANOX's separate, OPTIONAL commercial path

RIVANOX may negotiate a **paid alternative proprietary license** for
the RIVANOX-authored portions for which it controls sufficient copyright
and any contributor relicensing rights. Such a license is useful when a
customer wants different conditions: e.g. proprietary redistribution,
commercial integration, maintenance commitments or contractual terms
that would otherwise be incompatible with its chosen AGPL obligations.
Whether they actually need this depends on how they combine and
distribute software. **It is not automatically mandatory for all
commercial or business users.**

No automatic commercial sublicensing rights are conferred by a donation,
download, GitHub sponsorship, inquiry or this policy document. The
terms, price, usage scope, updates, support, liability and customer
restrictions require an individually negotiated, legally reviewed
agreement. No royalty percentage is being advertised or collected.

RIVANOX cannot sublicense upstream Raspberry Pi OS/Debian, BlueZ,
PipeWire, WirePlumber or independently copyrighted code as if it owned
them. The optional Windows Scream sender has separate third-party
conditions. Contributor PRs under AGPL do **not automatically give**
RIVANOX the rights to distribute that contribution under an alternative
proprietary license. Before accepting such code into a commercially
dual-licensed component, obtain an appropriate separate contributor
license grant or contribution agreement, with legal review.

## Independent income streams

- **Voluntary community support:** [Ko-fi / RIVANOX](https://ko-fi.com/RIVANOX)
  helps pay for device compatibility tests, security, maintenance and
  accessibility. Donations are **not** a prerequisite to download or
  use AGPL code or a future public SD image; no priority support or
  commercial license is implied.
- **Commercial alternative licensing:** quote-based, only for rights
  RIVANOX can lawfully grant, with a signed agreement.
- **Hardware, setup, customization and support:** voluntary professional
  services; can be sold separately from AGPL code. Avoid promises about
  support SLAs or warranties without an executed contract.
- **Brand and official distributions:** the RIVANOX identity can help
  users recognize trustworthy original releases. See
  [TRADEMARKS.md](../TRADEMARKS.md). Legitimate descriptive reference
  rights remain intact; trademarks do not cancel open-source licenses.

## Legal and release blockers

1. Confirm chain of title for every author/contractor, any employer
   ownership claims, third-party contributions and licensed snippets.
2. Review the binary Raspberry Pi image's **actual rootfs package
   inventory and license notices**, not only this source repository.
3. Verify AGPL corresponding-source obligations, network source offers,
   dependencies, firmware, trademark claims and relevant EU/DE rules
   with an appropriately qualified legal advisor.
4. Confirm whether the RIVANOX Ko-fi page is active and payouts legally
   and operationally configured before marketing donations as income.
   No payout setup or payment action is executed from this repo.
5. Only release after explicit owner approval and real Pi4 acceptance;
   the presence of an image in GitHub Actions does not mean it is
   suitable for public download under GitHub Releases.
6. If RIVANOX later decides **every** commercial deployment must pay,
   stop describing future code as OSI-approved open source and develop a
   distinct forward-looking source-available/commercial license with
   legal advice. That change cannot revoke the existing AGPL grants.

**For commercial inquiries:** use the existing public
[RIVANOX website](https://rivanox.com). No unverified email address,
pricing, payment instructions or guaranteed licensing options are
published here.

Related: [Third-party notices](../THIRD_PARTY_NOTICES.md),
[release distribution controls](RELEASE-DISTRIBUTION.md),
[security & acceptance requirements](RELEASE-ACCEPTANCE.md) and
[GitHub project handoff](PROJECT-HANDOFF.md).
