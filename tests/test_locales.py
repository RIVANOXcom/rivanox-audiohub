"""Five-language app contract: parity, content, and absence of unsafe HTML."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "web" / "locales"


class LocalizationTests(unittest.TestCase):
    def test_five_languages_with_exact_same_keys(self):
        languages = ("en", "de", "es", "fr", "it")
        base = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(base), 25)
        for language in languages:
            with self.subTest(language=language):
                data = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
                self.assertEqual(set(data), set(base))
                self.assertTrue(all(isinstance(v, str) and v.strip() for v in data.values()))

    def test_no_markup_or_remote_font_dependencies(self):
        for file in LOCALES.glob("*.json"):
            self.assertNotIn("<script", file.read_text().lower())
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertIn('id="language"', html)


if __name__ == "__main__":
    unittest.main()
