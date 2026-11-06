"""Five-language app contract: parity, content, and absence of unsafe HTML."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "web" / "locales"
PREVIEW = ROOT / "web" / "app.js"


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


def preview_validator_source():
    source = PREVIEW.read_text(encoding="utf-8")
    start = source.index("  const validName = raw => {")
    end = source.index("\n  };", start) + len("\n  };")
    return source[start:end]


class BrowserNameUnicodeTests(unittest.TestCase):
    def test_preview_uses_real_unicode_property_escape(self):
        text = preview_validator_source()
        self.assertIn(r"/[\p{C}<>]/u.test(name)", text)
        self.assertNotIn(r"/[\\p{C}<>]/u.test(name)", text)
        self.assertIn("Array.from(name).length > 32", text)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_real_shipped_javascript_validator(self):
        cases = r'''
const assert = require("node:assert/strict");
for (const value of ["Laptop", "PC Audio", "Computer", "p", "C", "C++",
                     "Musica", "Música", "Straße", "🙂"]) {
  assert.equal(validName(value), value, "normal label rejected: " + value);
}
assert.equal(validName("  Laptop  "), "Laptop");
for (const value of ["A\u0000B", "A\u0001B", "A\u007fB", "A\u202eB",
                     "A\u200dB", "A<B", "A>B", "X".repeat(33), "  "]) {
  assert.equal(validName(value), null, "unsafe label accepted: " + JSON.stringify(value));
}
assert.equal(validName("🙂".repeat(32)), "🙂".repeat(32));
assert.equal(validName("🙂".repeat(33)), null);
assert.equal(validName(3), null);
'''
        result = subprocess.run(
            ["node", "-e", preview_validator_source() + "\n" + cases],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


def preview_language_loader_source():
    source = PREVIEW.read_text(encoding="utf-8")
    start = source.index("  async function setLanguage(language) {")
    end = source.index('\n  }\n  byId("language")', start) + len("\n  }")
    return source[start:end]


class BrowserLocaleRaceTests(unittest.TestCase):
    def test_both_success_and_fallback_have_stale_request_guards(self):
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("let languageRequestId = 0;", source)
        body = preview_language_loader_source()
        self.assertIn("const requestId = ++languageRequestId;", body)
        self.assertEqual(body.count("if (requestId !== languageRequestId) return;"), 2)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_real_async_locale_race_and_stale_failure(self):
        setup = r'''
const assert = require("node:assert/strict");
const LANGUAGES = ["en", "de", "es", "fr", "it"];
const document = {documentElement: {lang: "en"}};
const dropdown = {value: "en"};
const byId = id => {assert.equal(id, "language"); return dropdown;};
const localStorage = {value: null, setItem(k, v) {this.value = [k, v];}};
const translated = [];
let words = {};
let languageRequestId = 0;
const translate = () => {translated.push([document.documentElement.lang, words.tagline]);};
const pending = {};
const fetch = uri => new Promise((resolve, reject) => {pending[uri] = {resolve, reject};});
'''
        check = r'''
async function verify() {
  const slow = setLanguage("de");
  const fast = setLanguage("it");
  pending["./locales/it.json"].resolve({ok: true, json: async () => ({tagline: "Italiano"})});
  await fast;
  pending["./locales/de.json"].resolve({ok: true, json: async () => ({tagline: "Deutsch"})});
  await slow;
  assert.equal(document.documentElement.lang, "it");
  assert.equal(dropdown.value, "it");
  assert.equal(words.tagline, "Italiano");
  assert.deepEqual(localStorage.value, ["audiohub.locale", "it"]);
  assert.deepEqual(translated, [["it", "Italiano"]]);

  const staleFailure = setLanguage("es");
  const latest = setLanguage("fr");
  pending["./locales/es.json"].reject(new Error("temporary translation failure"));
  await staleFailure;
  assert.equal(pending["./locales/en.json"], undefined);
  pending["./locales/fr.json"].resolve({ok: true, json: async () => ({tagline: "Français"})});
  await latest;
  assert.equal(document.documentElement.lang, "fr");
  assert.equal(dropdown.value, "fr");
  assert.equal(words.tagline, "Français");
  assert.deepEqual(localStorage.value, ["audiohub.locale", "fr"]);
}
verify().catch(e => {console.error(e); process.exitCode = 1;});
'''
        program = setup + "\n" + preview_language_loader_source() + "\n" + check
        result = subprocess.run(["node", "-e", program], capture_output=True,
                                text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)



class BrowserLocaleFallbackTests(unittest.TestCase):
    """The genuine shipping loader must commit a consistent English fallback."""

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_double_locale_failure_commits_english_metadata(self):
        setup = r'''
const assert = require("node:assert/strict");
const LANGUAGES = ["en", "de", "es", "fr", "it"];
const document = {documentElement: {lang: "fr"}};
const dropdown = {value: "fr"};
const byId = id => {assert.equal(id, "language"); return dropdown;};
const localStorage = {value: ["audiohub.locale", "fr"],
  setItem(k, v) {this.value = [k, v];}};
const translated = [];
let words = {};
let languageRequestId = 0;
const translate = () => {translated.push([document.documentElement.lang, words.tagline]);};
const fetch = async () => {throw new Error("locale offline");};
'''
        verify = r'''
async function check() {
  await setLanguage("it");
  assert.equal(document.documentElement.lang, "en");
  assert.equal(dropdown.value, "en");
  assert.equal(words.tagline, "All your audio. One place.");
  assert.deepEqual(localStorage.value, ["audiohub.locale", "en"]);
  assert.deepEqual(translated, [["en", "All your audio. One place."]]);
  // A second directly failed English request must retain the same UI state.
  await setLanguage("en");
  assert.deepEqual(translated, [
    ["en", "All your audio. One place."],
    ["en", "All your audio. One place."]
  ]);
}
check().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_language_loader_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_stale_english_fallback_failure_cannot_replace_latest_locale(self):
        setup = r'''
const assert = require("node:assert/strict");
const LANGUAGES = ["en", "de", "es", "fr", "it"];
const document = {documentElement: {lang: "it"}};
const dropdown = {value: "it"};
const byId = id => {assert.equal(id, "language"); return dropdown;};
const localStorage = {value: ["audiohub.locale", "it"],
  setItem(k, v) {this.value = [k, v];}};
const translated = [];
let words = {};
let languageRequestId = 0;
const translate = () => {translated.push([document.documentElement.lang, words.tagline]);};
const pending = {};
const fetch = uri => new Promise((resolve, reject) => {
  pending[uri] = {resolve, reject};
});
'''
        verify = r'''
async function check() {
  const old = setLanguage("de");
  pending["./locales/de.json"].reject(new Error("German unavailable"));
  await Promise.resolve();
  assert.ok(pending["./locales/en.json"], "English fallback should be pending");
  const latest = setLanguage("fr");
  pending["./locales/fr.json"].resolve({
    ok: true, json: async () => ({tagline: "Français"})
  });
  await latest;
  pending["./locales/en.json"].reject(new Error("English fallback unavailable"));
  await old;
  assert.equal(document.documentElement.lang, "fr");
  assert.equal(dropdown.value, "fr");
  assert.equal(words.tagline, "Français");
  assert.deepEqual(localStorage.value, ["audiohub.locale", "fr"]);
  assert.deepEqual(translated, [["fr", "Français"]]);
}
check().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_language_loader_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
