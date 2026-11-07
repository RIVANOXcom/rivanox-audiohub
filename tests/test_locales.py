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


def preview_control_labels_source():
    """Extract the exact helper shipped to browsers, not a reimplementation."""
    source = PREVIEW.read_text(encoding="utf-8")
    start = source.index("  function updateChannelControlLabels(channel) {")
    end = source.index("\n  }\n  function drawChannels()", start) + len("\n  }")
    return source[start:end]


class BrowserRenameAccessibilityTests(unittest.TestCase):
    """Renaming a preview input must update its existing focusable controls."""

    def test_rename_event_refreshes_mute_and_slider_accessible_names(self):
        source = PREVIEW.read_text(encoding="utf-8")
        start = source.index('nameInput.addEventListener("change", () => {')
        end = source.index('const source = document.createElement("p")', start)
        handler = source[start:end]
        self.assertIn("updateMute();", handler)
        self.assertIn("updateChannelControlLabels(channel);", handler)
        self.assertIn('mute.setAttribute("aria-label"', source)
        self.assertIn("state[channel].mute ? \"unmute\" : \"mute\"", source)
        self.assertNotIn('method: "POST"', source)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipped_slider_helper_updates_labels_after_rename_and_locale_change(self):
        setup = r'''
const assert = require("node:assert/strict");
const BANDS = ["bass", "mid", "treble"];
const labels = {};
const elements = {};
for (const key of ["volume", ...BANDS]) {
  const id = "music-" + key;
  elements[id] = {setAttribute(attr, value) {
    assert.equal(attr, "aria-label");
    labels[id] = value;
  }};
}
const byId = id => elements[id] || null;
let words = {volume: "Volume", bass: "Bass", mid: "Mid", treble: "Treble"};
const tr = key => words[key] || key;
let display = "Living room TV";
const displayName = channel => {
  assert.equal(channel, "music");
  return display;
};
'''
        verify = r'''
updateChannelControlLabels("music");
assert.deepEqual(labels, {
  "music-volume": "Volume: Living room TV",
  "music-bass": "Bass: Living room TV",
  "music-mid": "Mid: Living room TV",
  "music-treble": "Treble: Living room TV"
});
display = "Kitchen speaker";
words = {volume: "Lautstärke", bass: "Bass",
         mid: "Mitten", treble: "Höhen"};
updateChannelControlLabels("music");
assert.deepEqual(labels, {
  "music-volume": "Lautstärke: Kitchen speaker",
  "music-bass": "Bass: Kitchen speaker",
  "music-mid": "Mitten: Kitchen speaker",
  "music-treble": "Höhen: Kitchen speaker"
});
// A transiently absent control (e.g. during re-render) must not crash.
delete elements["music-bass"];
updateChannelControlLabels("music");
'''
        program = setup + "\n" + preview_control_labels_source() + "\n" + verify
        result = subprocess.run(["node", "-e", program], capture_output=True,
                                text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)



def preview_channel_renderer_source():
    """Exercise the shipped card construction and focus preservation together."""
    source = PREVIEW.read_text(encoding="utf-8")
    start = source.index('  function control(key, min, max, value, channel, unit = "") {')
    end = source.index("  function renderHardwareStatus()", start)
    return source[start:end]


class BrowserLocaleInputEditTests(unittest.TestCase):
    """Async translations must not erase user input or steal keyboard focus."""

    def test_input_length_matches_unicode_validator_and_previews_early_feedback(self):
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn('maxLength: 64, autoComplete: "off"', source)
        self.assertNotIn('maxLength: 32, autoComplete: "off"', source)
        self.assertIn('renameStatus.textContent = hasInvalidName() ?', source)
        self.assertIn('const hasInvalidName = () => {', source)

    def test_draft_and_focus_are_captured_before_replacing_cards(self):
        source = PREVIEW.read_text(encoding="utf-8")
        start = source.index("  function drawChannels() {")
        end = source.index("  function renderHardwareStatus()", start)
        body = source[start:end]
        self.assertLess(body.index("captureChannelEditState(target)"),
                        body.index("target.replaceChildren()"))
        self.assertIn("restoreChannelEditState(editState);", body)
        self.assertIn('nameInput.addEventListener("input", () =>', body)
        self.assertIn('nameInput.dataset.editing = "false";', body)
        self.assertNotIn('method: "POST"', source)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_actual_browser_cards_keep_unsaved_name_caret_and_slider_focus(self):
        setup = r'''
const assert = require("node:assert/strict");
class Node {
  constructor(tag) {
    this.tag = tag;
    this.id = "";
    this.type = "";
    this.value = "";
    this.children = [];
    this.handlers = {};
    this.dataset = {};
    this.attributes = {};
  }
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children = items;}
  addEventListener(kind, handler) {this.handlers[kind] = handler;}
  setAttribute(key, value) {this.attributes[key] = String(value);}
  contains(node) {
    return this === node || this.children.some(child => child.contains(node));
  }
  focus() {document.activeElement = this;}
  setSelectionRange(start, end) {
    this.selectionStart = start;
    this.selectionEnd = end;
  }
}
const document = {activeElement: null, createElement: tag => new Node(tag)};
const root = new Node("div");
root.id = "channels";
function find(el, id) {
  if (el.id === id) return el;
  for (const child of el.children) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}
const byId = id => id === "channels" ? root : find(root, id);
const CHANNELS = ["music", "laptop", "tablet"];
const BANDS = ["bass", "mid", "treble"];
const SLOT_INDEX = {music: 1, laptop: 2, tablet: 3};
const previewLabels = Object.create(null);
const state = {
  music: {volume: 65, mute: false, bass: 0, mid: 0, treble: 0},
  laptop: {volume: 50, mute: false, bass: 0, mid: 0, treble: 0},
  tablet: {volume: 50, mute: false, bass: 0, mid: 0, treble: 0}
};
const saved = [];
const savePreviewLabels = () => {saved.push({...previewLabels});};
let words = {
  input1: "Input 1", input2: "Input 2", input3: "Input 3",
  inputName: "Input name", volume: "Volume", bass: "Bass",
  mid: "Mid", treble: "Treble", mute: "Mute", unmute: "Unmute"
};
const tr = key => words[key] || key;
const displayName = channel =>
  previewLabels[channel] || tr("input" + SLOT_INDEX[channel]);
'''
        verify = r'''
drawChannels();
const oldName = byId("music-display-name");
oldName.focus();
oldName.value = "Living room TV";
oldName.selectionStart = 4;
oldName.selectionEnd = 11;
oldName.handlers.input();
state.music.volume = 37;
// A delayed locale request finishes while the user is still editing.
words = {
  input1: "Eingang 1", input2: "Eingang 2", input3: "Eingang 3",
  inputName: "Eingangsname", volume: "Lautstärke",
  bass: "Bass", mid: "Mitten", treble: "Höhen",
  mute: "Stumm", unmute: "Ton an"
};
drawChannels();
const newName = byId("music-display-name");
assert.notEqual(newName, oldName);
assert.equal(newName.value, "Living room TV");
assert.equal(newName.dataset.editing, "true");
assert.equal(document.activeElement, newName);
assert.equal(newName.selectionStart, 4);
assert.equal(newName.selectionEnd, 11);
assert.equal(byId("music-volume").value, 37);
assert.equal(byId("laptop-display-name").value, "Eingang 2");
assert.equal(byId("music-volume").attributes["aria-label"], "Lautstärke: Eingang 1");
assert.deepEqual(saved, []); // no implicit persistence on locale load

// Explicit change still performs the original browser-local save.
newName.handlers.change();
assert.equal(newName.dataset.editing, "false");
assert.equal(previewLabels.music, "Living room TV");
assert.equal(saved.length, 1);
assert.equal(byId("music-volume").attributes["aria-label"],
             "Lautstärke: Living room TV");

// A focused existing slider also retains its focus after a redraw.
const oldRange = byId("music-volume");
oldRange.focus();
drawChannels();
const newRange = byId("music-volume");
assert.notEqual(oldRange, newRange);
assert.equal(document.activeElement, newRange);
assert.equal(newRange.value, 37);

// An external language selector must not be grabbed by a card redraw.
const languageDropdown = new Node("select");
languageDropdown.focus();
drawChannels();
assert.equal(document.activeElement, languageDropdown);

// A 32-codepoint name is valid even if it needs 64 UTF-16 code units.
const emoji = "🙂".repeat(32);
const tabletName = byId("tablet-display-name");
assert.equal(tabletName.maxLength, 64);
tabletName.value = emoji;
tabletName.handlers.input();
const tabletFeedback = root.children[2].children[1].children[3];
assert.equal(tabletFeedback.textContent, "");
tabletName.handlers.change();
assert.equal(previewLabels.tablet, emoji);

// Too many visible characters must be called out before commit.
words.invalidInputName = "Ungültiger Name";
const laptopName = byId("laptop-display-name");
laptopName.value = "A".repeat(33);
laptopName.handlers.input();
const laptopFeedback = root.children[1].children[1].children[3];
assert.equal(laptopFeedback.textContent, "Ungültiger Name");
laptopName.handlers.change();
assert.equal(laptopName.value, "Eingang 2");
assert.equal(previewLabels.laptop, undefined);

// Duplicate input names must also receive immediate feedback.
laptopName.value = emoji;
laptopName.handlers.input();
assert.equal(laptopFeedback.textContent, "Ungültiger Name");
laptopName.value = "Studio";
laptopName.handlers.input();
assert.equal(laptopFeedback.textContent, "");
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_validator_source() + "\n" +
             preview_channel_renderer_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
