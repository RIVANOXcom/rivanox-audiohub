"""Verify sustainable funding UI and truthful licensing/release boundaries."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DistributionPolicyTests(unittest.TestCase):
    def test_funding_link_is_verified_existing_project_link(self):
        funding = (ROOT / ".github/FUNDING.yml").read_text()
        self.assertIn("ko_fi: RIVANOX", funding)
        self.assertNotIn("github: RIVANOX", funding)

    def test_visible_browser_support_is_voluntary_not_paywalled(self):
        html = (ROOT / "web/index.html").read_text()
        self.assertIn('class="support-feature"', html)
        self.assertIn('href="https://ko-fi.com/RIVANOX"', html)
        self.assertIn('data-t="sustainabilityDonate"', html)
        self.assertIn('data-t="sustainabilityDisclosure"', html)
        self.assertIn('data-t="sustainabilityCommercial"', html)
        self.assertNotIn("data-payment-token", html)
        self.assertNotIn("stripe.com", html)
        self.assertNotIn("paywall", html.lower())

    def test_all_five_languages_distinguish_donations_and_licenses(self):
        names = ("en", "de", "es", "fr", "it")
        keys = (
            "sustainabilityEyebrow",
            "sustainabilityTitle",
            "sustainabilityDescription",
            "sustainabilityDisclosure",
            "sustainabilityDonate",
            "sustainabilityCommercial",
        )
        for language in names:
            data = json.loads((ROOT / "web/locales" / (language + ".json")).read_text())
            with self.subTest(language=language):
                self.assertTrue(all(data.get(key) for key in keys))
                self.assertNotIn("<", "".join(data[key] for key in keys))
                self.assertNotIn("http", "".join(data[key] for key in keys).lower())

    def test_readme_does_not_claim_royalty_on_agpl_users(self):
        readme = (ROOT / "README.md").read_text()
        licensing = (ROOT / "docs/COMMERCIAL-LICENSING.md").read_text()
        self.assertIn("Commercial use under AGPL is allowed", readme)
        self.assertIn("does **not**", licensing)
        self.assertIn("cannot unilaterally retroactively", licensing)
        self.assertIn("RIVANOX cannot sublicense upstream", licensing)
        self.assertIn("commercial alternative", licensing)
        self.assertIn("Ko-fi", readme)

    def test_public_release_workflow_still_fail_closed(self):
        publish = (ROOT / ".github/workflows/publish-image.yml").read_text()
        image = (ROOT / ".github/workflows/build-image-preview.yml").read_text()
        self.assertIn("No hardware-verified Pi image", publish)
        self.assertIn("exit 1", publish)
        self.assertNotIn("contents: write", publish)
        self.assertIn("scripts/release_bundle_audit.py", image)
        self.assertIn("UNVERIFIED", image)
        self.assertNotIn("gh release create", image)
        self.assertNotIn("softprops/action-gh-release", image)

    def test_distribution_documentation_requires_human_approval(self):
        doc = (ROOT / "docs/RELEASE-DISTRIBUTION.md").read_text()
        self.assertIn("human", doc.lower())
        self.assertIn("pi4", doc.lower())
        self.assertIn("AGPL", doc)
        self.assertIn("SHA256", doc)
        self.assertIn("operator", doc.lower())

    def test_new_ui_is_still_only_a_preview_and_read_only(self):
        webserver = (ROOT / "src/audiohub/webserver.py").read_text()
        html = (ROOT / "web/index.html").read_text()
        self.assertIn("Read-only preview", webserver)
        self.assertIn("def do_POST(self):", webserver)
        self.assertIn('data-t="previewNotice"', html)
        self.assertNotIn('action="/api/donate"', html)

    def test_legal_license_unmodified(self):
        license = (ROOT / "LICENSE").read_text()
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", license)
        self.assertIn("Version 3, 19 November 2007", license)
        self.assertNotIn("commercial use prohibited", license.lower())


if __name__ == "__main__":
    unittest.main()
