# RIVANOX AudioHub — Model C rights, provenance and licensing due diligence

**Assessment date:** 2026-11-05. **Status: legal review required — NO LICENSE SWITCH.**
**Latest verified technical evidence:** [ARM64 #42106833667](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42106833667) SUCCESS, 336 source tests, 55/55 real rootfs gates, 689 dpkg packages (538 arm64/151 all), 680 copyright hashes, 8 two-hop link-chain copyright paths and 1 absent expected `raspberrypi-net-mods` copyright file. All 49 one-hop aliases have matching dpkg Source/direct Depends observations; these findings **do not grant distribution rights**. [Canonical handoff](../PAPA_CANONICAL_RESUME_20261105.md) and [79-file pending source-rights ledger](SOURCE-RIGHTS-LEDGER.json).
**Project:** PJ2611-0001:R001. **Base:** draft PR #34
`c28a61bea275f8602458c2961e06454430cc4319`.
**Target:** publicly viewable source; private personal usage without a fee;
separately contracted paid business / commercial use of future eligible code.

This is an engineering rights inventory and decision record, **not** an
ownership certificate, copyright opinion, third-party clearance, contract
or approval to publish an image.

## Evidence actually observed

| Topic | Recorded observation | Assessment / consequence |
| --- | --- | --- |
| Repository | `RIVANOXcom/rivanox-audiohub` is **public**, default `main`, checked 2026-11-05. | Source may have been cloned/downloaded; absence of a published SD image says nothing about recipients of source. |
| Current copyright grant | `main/LICENSE` is unmodified **GNU AGPL-3.0-only**; code comments also reference AGPL. | For valid AGPL recipients, commercial use is permitted under AGPL. No retroactive revocation. |
| GitHub commit metadata | 16 commits visible on `main`; GitHub author identity `RIVANOX | Software & SmartTools`, account `RIVANOXcom`. 26 GitHub PRs returned with `RIVANOXcom` as PR creator. | Helpful provenance, **not** a contractual chain-of-title or a determination of human authorship. Commit author may be an account/bot. |
| Public releases | GitHub Releases API returned `[]`. Existing Actions preview archives are unverified. | No published official SD image observed; not evidence of no prior source distribution. |
| Foreign/individual rights | Raspberry Pi OS/Debian, pi-gen, PipeWire, WirePlumber, BlueZ, system libraries and firmware; optional Scream experiment (MS-PL upstream). | Component and image-specific copyright, source availability, patent and trademark review required. |
| Image inventory | PR #34 generates hashes/versions from dpkg installation. | This is only an **incomplete technical input**, not a complete dependency/SBOM/license analysis. |
| Contributor policy | `CONTRIBUTING.md` explicitly says an AGPL PR does not grant proprietary relicensing rights. | Verify every copied snippet and contributor grant; do not accept new foreign-code PRs as if owned. |
| AI-assisted authorship | ChatGPT-generated output is generally assigned to users by OpenAI to the extent permitted by law, but output need not be unique. German copyright protects human creative contributions. | No categorical exclusive copyright ownership claim merely because ChatGPT produced files. Document human design/revision, assignments and imported code separately. |
| GitHub forks | Public GitHub repositories permit viewing/forking subject to platform terms. | Model C cannot promise download-only without all forks; already issued AGPL permissions persist. |
| Brand | `TRADEMARKS.md` reserves names/marks to their rightsholders. | Check actual trademark ownership/registration; a copyright license does not itself confer mark rights. |
| Project language | Documentation and GitHub engineering in English; app UI five locales. | Policy docs in English; consumer-facing translations must not contradict enforceable legal terms. |

## Open chain-of-title questions — blocking

- [ ] Identify the legally entitled licensor (exact natural/legal person),
      whether `RIVANOX` is a trademark, company, trade name or licensed brand;
      record appropriate signature authority.
- [ ] Collect repository/source contribution history, exact code origins,
      human authorship, employment/freelancer/contractor assignments, reused
      snippets, GitHub PRs and permission records.
- [ ] Determine whether any AI-generated program portion lacks independent
      copyright protection, whether any foreign rights may attach, and how
      human creativity/editorial decisions are documented.
- [ ] Obtain explicit relicensing grants for any retained contributor code,
      or exclude / lawfully rewrite contributions without derivative copying.
- [ ] Identify exact old-AGPL snapshot and all earlier source versions,
      maintain continued access to appropriate license notices and source,
      distinguish existing recipients from newly published release grants.
- [ ] Check whether internally created or third-party **AGPL/GPL** components
      are modified, linked or combined; assess dependencies vs mere aggregation.
      A file header/license swap by itself is **not** sufficient.
- [ ] Inspect complete actual SD rootfs: dpkg inventory, pip modules, firmware,
      kernel, legal/copyright files, corresponding-source and written-offer
      requirements, installers and EULAs. No blanket 'RIVANOX owns the image'.
- [ ] Have qualified DE/EU counsel review a specifically effective, versioned
      non-commercial community license and separately priced commercial terms,
      copyright enforcement, consumer exceptions, EU rules and governing law.
- [ ] Decide treatment of non-profits, schools, mixed-use households,
      research, contractors, public bodies, family members and commercial
      hardware sellers in the finalized license/FAQ.
- [ ] Verify Ko-fi account/receipts/tax treatment separately; donation never
      gives redistribution or a paid license.
- [ ] Obtain written owner authorization for a precisely versioned LICENSE
      change and publication; do not rely on a check box in source control.
- [ ] Complete physical Pi4/Edifier, owner authentication, Wi-Fi and safety
      acceptance before official GitHub Releases.

## Preferred commercialization model (business direction, NOT yet operative)

**Proposed Model C** — eligible future RIVANOX source available for private
individual, household, non-commercial download/use/local modification, with
commercial/company redistribution, installation, hosting, hardware bundling
or professional use subject to a separately negotiated written license.
Do not set unagreed royalty percentages or claim collection rights on older
AGPL copies. Official software images should remain free for permitted private
use; voluntary Ko-fi support remains visible and optional.

A bespoke source-available contract is **not OSI-approved open source**:
a license restricting business use is inconsistent with OSI Open Source
Definition criterion 6. Commercial-use restrictions must not be
misrepresented as limitations of GNU AGPL-3.0.

## Transition plan — gates and no-regression controls

1. Keep the current `LICENSE` and its existing AGPL header references
   **untouched** during legal scoping. Put the proposed contract in
   `LICENSE-C-DRAFT.md`, prominently labeled NOT EFFECTIVE.
2. Use `docs/licensing/TRANSITION-STATE.json` as a transparent, read-only
   machine-checked record: current AGPL, target C, evidence/approvals false.
   The CI safety check MUST reject invented "approved" status or an unexpected
   rewrite of `LICENSE` in the preparation branch.
3. On legal sign-off, establish a new effective version and audit each
   RIVANOX-owned source file, SPDX tags, notices, README, website/locales,
   public releases and all scripts/CI policy. Preserve exact old-AGPL
   versions and rights. Do **not** relabel third-party source.
4. Only an explicit owner-approved release/tag/version may activate new
   terms. Keep `publish-image.yml` blocked until all hardware/security,
   distribution and redistribution gates also pass.
5. Place both the effective future grant and separate commercial inquiry
   channel next to downloads. Avoid confusing AGPL older snapshots with
   Model C binaries. No public stable release is implied by this review.

## Legal source links (for counsel; exact scopes require professional review)

- [OpenAI Terms for Europe — Content/Output ownership](https://openai.com/de-DE/policies/eu-terms-of-use/)
- [German Copyright Act § 2 — human personal intellectual creations](https://www.gesetze-im-internet.de/urhg/__2.html)
- [German Federal Ministry of Justice: AI and copyright FAQ](https://www.bmjv.de/SharedDocs/Downloads/DE/Themen/Nav_Themen/240305_FAQ_KI_Urheberrecht.pdf?__blob=publicationFile&v=2)
- [GNU AGPLv3 full text and § 10 downstream recipient rights](https://www.gnu.org/licenses/agpl-3.0.html)
- [GitHub docs: Licenses, public repository view/fork rights](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
- [OSI Open Source Definition](https://opensource.org/osd)
- [SPDX custom LicenseRef format](https://spdx.github.io/spdx-spec/v2.3/SPDX-license-expressions/)

**Disposition:** MODEL C IS THE OWNER'S COMMERCIAL DIRECTION,
BUT CURRENT EFFECTIVE REPOSITORY LICENSE REMAINS AGPL-3.0-only
UNTIL CHAIN-OF-TITLE, LEGAL REVIEW AND EXPLICIT CHANGE ARE COMPLETED.

## Third-party technical follow-up (2026-11-05)

[Detailed source and binary review](THIRD-PARTY-REVIEW-2026-11-05.md):
AudioHub Python imports are largely standard library plus D-Bus and
PyGObject; checked UI uses local JavaScript/CSS. The Scream test receiver
appears implemented in the AudioHub tree, with no bundled Windows driver,
but independent code provenance/similarity is **not** proven. The real
PR #34 ARM64 build [42092547313](https://github.com/RIVANOXcom/rivanox-audiohub/actions/runs/42092547313)
recorded 689 packages / 631 copyright hashes / 58 unresolved copyright
paths, then **FAILED** at missing `deploy/ROOTFS-PACKAGES.json`.
No inventory-containing test ZIP or legal sign-off resulted. Human
license review and corrected image export remain mandatory.

### 2026-11-06 new source-rights files under review

Draft PR #47 adds `src/audiohub/process_capture.py` and `tests/test_process_capture.py`, so the fail-closed provenance inventory now lists **81** application/source/CI/test files (previously 79), with every rightsholder, third-party similarity and Model C eligibility assertion still **FALSE**. Adding a ledger entry is not a legal approval. Refer to [PAPA canonical resume](../PAPA_CANONICAL_RESUME_20261105.md) section O for exact PR/CI state.

### 2026-11-06 noncommercial developer diagnostics pending rights review

Draft PR #48 adds `src/audiohub/manual_acceptance.py` and `tests/test_manual_acceptance.py` to the legacy AGPL test/diagnostic suite. Pending-rights ledger now covers **83** checked-in source/test/build/CI files. An entry means only provenance and future commercial Model C eligibility STILL REQUIRE HUMAN REVIEW; no ownership or redistribution permission is inferred. The manual harness always sets release_ready and legal_redistribution_approved FALSE; even all-positive subjective hardware answers do not create rights.
