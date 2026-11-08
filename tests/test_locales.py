"""Five-language app contract: parity, content, and absence of unsafe HTML."""
import json
import re
from html.parser import HTMLParser
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
        self.assertIn('renameStatus.textContent = invalid ? tr("invalidInputName") : "";', source)
        self.assertIn('setNameInvalid(invalid);', source)
        self.assertIn('const hasInvalidName = () => {', source)

    def test_invalid_name_feedback_is_exposed_to_assistive_technology(self):
        source = PREVIEW.read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('renameStatus.id = inputId + "-feedback";', source)
        self.assertIn('nameInput.setAttribute("aria-describedby", renameStatus.id);', source)
        self.assertIn('nameInput.setAttribute("aria-invalid", String(invalid));', source)
        self.assertIn('renameStatus.setAttribute("role", "status");', source)
        self.assertIn('.channel-name-input[aria-invalid="true"]', styles)
        self.assertIn('.channel-name-status[data-invalid="true"]', styles)
        self.assertNotIn('method: "POST"', source)

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
const musicFeedback = root.children[0].children[1].children[3];
assert.equal(musicFeedback.id, "music-display-name-feedback");
assert.equal(musicFeedback.attributes.role, "status");
assert.equal(newName.attributes["aria-describedby"], musicFeedback.id);
assert.equal(newName.attributes["aria-invalid"], "false");
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
assert.equal(newName.attributes["aria-invalid"], "false");
assert.equal(musicFeedback.textContent, "previewNamesOnly");
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
assert.equal(tabletName.attributes["aria-invalid"], "false");
assert.equal(tabletName.attributes["aria-describedby"], tabletFeedback.id);
tabletName.handlers.change();
assert.equal(previewLabels.tablet, emoji);

// Too many visible characters must be called out before commit.
words.invalidInputName = "Ungültiger Name";
const laptopName = byId("laptop-display-name");
laptopName.value = "A".repeat(33);
laptopName.handlers.input();
const laptopFeedback = root.children[1].children[1].children[3];
assert.equal(laptopFeedback.textContent, "Ungültiger Name");
assert.equal(laptopFeedback.id, "laptop-display-name-feedback");
assert.equal(laptopName.attributes["aria-describedby"], laptopFeedback.id);
assert.equal(laptopName.attributes["aria-invalid"], "true");
assert.equal(laptopFeedback.dataset.invalid, "true");
laptopName.handlers.change();
assert.equal(laptopName.value, "Eingang 2");
assert.equal(previewLabels.laptop, undefined);
assert.equal(laptopName.attributes["aria-invalid"], "false");
assert.equal(laptopFeedback.dataset.invalid, "false");

// Duplicate input names must also receive immediate feedback.
laptopName.value = emoji;
laptopName.handlers.input();
assert.equal(laptopFeedback.textContent, "Ungültiger Name");
assert.equal(laptopName.attributes["aria-invalid"], "true");
laptopName.value = "Studio";
laptopName.handlers.input();
assert.equal(laptopFeedback.textContent, "");
assert.equal(laptopName.attributes["aria-invalid"], "false");
assert.equal(laptopFeedback.dataset.invalid, "false");

// An invalid draft stays invalid and translated across asynchronous redraws.
laptopName.value = "B".repeat(33);
laptopName.handlers.input();
laptopName.focus();
words.invalidInputName = "Nombre inválido";
drawChannels();
const newLaptop = byId("laptop-display-name");
const newLaptopFeedback = root.children[1].children[1].children[3];
assert.equal(newLaptop.value, "B".repeat(33));
assert.equal(newLaptop.attributes["aria-invalid"], "true");
assert.equal(newLaptop.attributes["aria-describedby"], newLaptopFeedback.id);
assert.equal(newLaptopFeedback.dataset.invalid, "true");
assert.equal(newLaptopFeedback.textContent, "Nombre inválido");
assert.equal(document.activeElement, newLaptop);
'''
        result = subprocess.run(
            ["node", "-e", setup + "\n" + preview_validator_source() + "\n" +
             preview_channel_renderer_source() + "\n" + verify],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()


def preview_routing_planner_source():
    """Run actual shipped JS planner/renderer in Node with a minimal DOM."""
    source = PREVIEW.read_text(encoding="utf-8")
    start = source.index("  function planRoutingLayout(lan, bt1, bt2) {")
    end = source.index("  function statusIsRecent() {", start)
    return source[start:end]


class BrowserRoutingPlannerTests(unittest.TestCase):
    def test_five_language_preview_controls_have_identical_supported_keys(self):
        required = {
            "routingPlanTitle", "routingPlanNotice", "routingPlanLan",
            "routingPlanBt1", "routingPlanBt2", "routingPlanUnused",
            "routingPlanValid", "routingPlanConflict", "routingPlanReset",
            "routingPlanResetDone", "routingPlanScope",
            "routingGuideTitle", "routingGuideIntro", "routingGuideInspect",
            "routingGuideFromBt1", "routingGuideFromBt2", "routingGuideUnknown",
            "routingGuideNeedSlots", "routingGuideReady",
            "routingGuideCommandLabel", "routingGuideWarning",
            "routingGuideComparisonTitle", "routingGuideComparisonNotice",
            "routingGuideMoved", "routingGuideUnchanged"
        }
        for lang in ("en", "de", "es", "fr", "it"):
            with self.subTest(lang=lang):
                data = json.loads((LOCALES / (lang + ".json")).read_text(encoding="utf-8"))
                self.assertTrue(required.issubset(data))
                self.assertTrue(all(data[key].strip() for key in required))
                for key in ("sourceHint1", "sourceHint2", "sourceHint3"):
                    self.assertIn("sourceHint" + key[-1], data)
        markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        for id_ in ("routing-plan-lan", "routing-plan-bt1", "routing-plan-bt2",
                    "routing-plan-status", "routing-plan-list", "routing-plan-reset",
                    "routing-guide-from-bt1", "routing-guide-from-bt2",
                    "routing-guide-status", "routing-guide-command",
                    "routing-guide-comparison-list",
                    "routing-guide-comparison-note"):
            self.assertIn('id="' + id_ + '"', markup)
        self.assertIn('aria-live="polite"', markup)
        self.assertIn('data-t="routingPlanScope"', markup)
        self.assertIn('value="unused"', markup)
        self.assertIn('value="unknown"', markup)
        self.assertIn('readonly rows="3"', markup)
        self.assertIn('aria-live="polite"', markup)
        self.assertNotIn('method: "POST"', PREVIEW.read_text(encoding="utf-8"))

    def test_routing_layout_is_browser_only_and_does_not_expose_device_ids(self):
        source = preview_routing_planner_source()
        self.assertIn("new Set(selected).size !== selected.length", source)
        self.assertIn('status.dataset.invalid = String(layout === null);', source)
        self.assertIn('list.replaceChildren();', source)
        self.assertIn('row.textContent =', source)
        for absent in ("fetch(", "localStorage.", "innerHTML", "bluetoothctl",
                       "writeFile", "POST", "--confirm-local-route-change",
                       "navigator.clipboard", "eval("):
            self.assertNotIn(absent, source)
        self.assertIn("python3 -m audiohub.source_routes", source)
        self.assertIn("--format text --preview layout ", source)
        self.assertIn('field.value = command === null ? "" : command;', source)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_shipped_planner_conflicts_accessible_labels_reset_and_locale(self):
        setup = r"""
const assert = require("node:assert/strict");
const CHANNELS = ["music", "laptop", "tablet"];
const SLOT_INDEX = {music: 1, laptop: 2, tablet: 3};
const elements = Object.create(null);
for (const role of ["lan", "bt1", "bt2"]) {
  elements["routing-plan-" + role] = {value: ""};
}
for (const role of ["bt1", "bt2"]) {
  elements["routing-guide-from-" + role] = {value: "unknown"};
}
elements["routing-guide-command"] = {value: ""};
elements["routing-guide-status"] = {dataset: {}, textContent: ""};
elements["routing-plan-status"] = {dataset: {}, textContent: ""};
elements["routing-plan-reset-status"] = {textContent: ""};
elements["routing-guide-comparison-list"] = {
  children: [], attributes: {},
  setAttribute(name, value) {this.attributes[name] = value;},
  replaceChildren() {this.children = [];},
  append(value) {this.children.push(value);}
};
elements["routing-plan-list"] = {
  children: [],
  attributes: {},
  setAttribute(name, value) {this.attributes[name] = value;},
  replaceChildren() {this.children = [];},
  append(value) {this.children.push(value);}
};
const byId = id => {
  assert.ok(elements[id], "unknown DOM element: " + id);
  return elements[id];
};
const document = {createElement(tag) {
  assert.equal(tag, "li");
  return {textContent: ""};
}};
let words = {
  routingPlanTitle: "Example layout",
  routingPlanLan: "LAN",
  routingPlanBt1: "Bluetooth A",
  routingPlanBt2: "Bluetooth B",
  routingPlanUnused: "Unassigned",
  routingPlanValid: "Example only",
  routingPlanConflict: "Conflict",
  routingPlanResetDone: "Restored",
  routingGuideReady: "Preview prepared",
  routingGuideNeedSlots: "Missing verified current inputs",
  routingGuideComparisonTitle: "Assumed movements",
  routingGuideMoved: "would move",
  routingGuideUnchanged: "would stay",
  input1: "Input 1", input2: "Input 2", input3: "Input 3"
};
const tr = key => words[key] || key;
"""
        checks = r"""
const slots = elements["routing-plan-list"];
const status = elements["routing-plan-status"];
const lan = elements["routing-plan-lan"];
const bt1 = elements["routing-plan-bt1"];
const bt2 = elements["routing-plan-bt2"];
assert.deepEqual(planRoutingLayout("laptop", "music", "tablet"), [
  {slot: "music", role: "bt1"},
  {slot: "laptop", role: "lan"},
  {slot: "tablet", role: "bt2"}
]);
for (const [a, b, c] of [
  ["music", "music", "tablet"],
  ["laptop", "music", "music"],
  ["invalid", "music", "tablet"],
  ["laptop", "evil", "tablet"],
  ["unused", "music", "tablet"],
  ["laptop", 17, "tablet"]
]) assert.equal(planRoutingLayout(a, b, c), null);
assert.deepEqual(planRoutingLayout("music", "unused", "unused"), [
  {slot: "music", role: "lan"},
  {slot: "laptop", role: "unused"},
  {slot: "tablet", role: "unused"}
]);
lan.value = "music"; bt1.value = "music"; bt2.value = "unused";
renderRoutingPlan();
assert.equal(status.textContent, "Conflict");
assert.equal(status.dataset.invalid, "true");
assert.equal(slots.children.length, 0);
lan.value = "tablet"; bt1.value = "music"; bt2.value = "unused";
renderRoutingPlan();
assert.equal(status.textContent, "Example only");
assert.equal(status.dataset.invalid, "false");
assert.deepEqual(slots.children.map(item => item.textContent), [
  "Input 1: Bluetooth A", "Input 2: Unassigned", "Input 3: LAN"
]);
words.input1 = "Eingang 1";
words.routingPlanBt1 = "Bluetooth-Quelle A";
words.routingPlanTitle = "Beispielbelegung";
renderRoutingPlan();
assert.equal(slots.attributes["aria-label"], "Beispielbelegung");
assert.equal(slots.children[0].textContent, "Eingang 1: Bluetooth-Quelle A");
resetRoutingPlan();
assert.deepEqual([lan.value, bt1.value, bt2.value],
  ["laptop", "music", "tablet"]);
assert.equal(elements["routing-plan-reset-status"].textContent, "Restored");
assert.equal(slots.children.length, 3);
assert.equal(status.dataset.invalid, "false");
assert.equal(elements["routing-guide-command"].value, "");
assert.equal(elements["routing-guide-comparison-list"].children.length, 0);
assert.deepEqual(
  [elements["routing-guide-from-bt1"].value,
   elements["routing-guide-from-bt2"].value], ["unknown", "unknown"]);
"""
        script = setup + "\n" + preview_routing_planner_source() + "\n" + checks
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, timeout=15,
            check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_browser_guide_generates_only_guarded_readonly_local_preview(self):
        setup = r"""
const assert = require("node:assert/strict");
const CHANNELS = ["music", "laptop", "tablet"];
const SLOT_INDEX = {music: 1, laptop: 2, tablet: 3};
const elements = Object.create(null);
for (const id of ["routing-plan-lan", "routing-plan-bt1", "routing-plan-bt2",
                  "routing-guide-from-bt1", "routing-guide-from-bt2"]) {
  elements[id] = {value: "unknown"};
}
elements["routing-plan-status"] = {dataset: {}, textContent: ""};
elements["routing-guide-status"] = {dataset: {}, textContent: ""};
elements["routing-guide-command"] = {value: ""};
elements["routing-plan-reset-status"] = {textContent: ""};
elements["routing-guide-comparison-list"] = {
  children: [], attributes: {},
  setAttribute(name, value) {this.attributes[name] = value;},
  replaceChildren() {this.children = [];},
  append(value) {this.children.push(value);}
};
elements["routing-plan-list"] = {
  children: [], setAttribute() {},
  replaceChildren() {this.children = [];},
  append(value) {this.children.push(value);}
};
const document = {createElement(tag) {
  assert.equal(tag, "li");
  return {textContent: ""};
}};
const byId = id => {
  assert.ok(elements[id], "unrecognized node: " + id);
  return elements[id];
};
const tr = key => ({
  routingGuideReady: "Preview prepared",
  routingGuideNeedSlots: "Unverified current inputs",
  routingGuideComparisonTitle: "Assumed movements",
  routingGuideMoved: "would move",
  routingGuideUnchanged: "would stay",
  routingPlanLan: "LAN",
  routingPlanBt1: "Bluetooth A",
  routingPlanBt2: "Bluetooth B",
  input1: "Input 1", input2: "Input 2", input3: "Input 3"
})[key] || key;
"""
        tests = r"""
const command = "PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes " +
  "--format text --preview layout music music tablet tablet laptop";
assert.equal(buildLocalRoutingPreview(
  "music", "tablet", "laptop", "music", "tablet"), command);
for (const invalid of [
  ["music", "tablet", "unused", "music", "tablet"],
  ["music", "tablet", "laptop", "unknown", "tablet"],
  ["music", "tablet", "laptop", "music", "unknown"],
  ["music", "tablet", "laptop", "music", "music"],
  ["music", "tablet", "music", "laptop", "tablet"],
  ["music", "tablet", "laptop", "music;rm", "tablet"],
  ["music", "tablet", "laptop", "music", "laptop;touch"],
  ["music", "tablet", "laptop", "unused", "tablet"],
  ["music", "tablet", "laptop", "music", null],
  ["unknown", "tablet", "laptop", "music", "tablet"]
]) assert.equal(buildLocalRoutingPreview(...invalid), null);
const lan = byId("routing-plan-lan");
const bt1 = byId("routing-plan-bt1");
const bt2 = byId("routing-plan-bt2");
const from1 = byId("routing-guide-from-bt1");
const from2 = byId("routing-guide-from-bt2");
const field = byId("routing-guide-command");
const status = byId("routing-guide-status");
lan.value = "music"; bt1.value = "tablet"; bt2.value = "laptop";
from1.value = "music"; from2.value = "tablet";
renderRoutingPlan();
assert.equal(field.value, command);
assert.equal(status.dataset.invalid, "false");
assert.equal(status.textContent, "Preview prepared");
const movements = byId("routing-guide-comparison-list");
assert.deepEqual(movements.children.map(x => x.textContent), [
  "LAN: Input 2 → Input 1 · would move",
  "Bluetooth A: Input 1 → Input 3 · would move",
  "Bluetooth B: Input 3 → Input 2 · would move"
]);
assert.equal(movements.attributes["aria-label"], "Assumed movements");
assert.deepEqual(routeMovementPlan("music", "tablet", "laptop", "music", "tablet"), [
  {role:"routingPlanLan",from:"laptop",to:"music"},
  {role:"routingPlanBt1",from:"music",to:"tablet"},
  {role:"routingPlanBt2",from:"tablet",to:"laptop"}
]);
assert.equal(routeMovementPlan("music", "tablet", "laptop", "music", "music"), null);
assert.ok(!field.value.includes("--confirm-local-route-change"));
assert.ok(!field.value.includes("--if-preview-revision"));
from2.value = "music";
renderRoutingGuide();
assert.equal(field.value, "");
assert.equal(status.dataset.invalid, "true");
assert.equal(status.textContent, "Unverified current inputs");
assert.equal(movements.children.length, 0);
from2.value = "tablet";
renderRoutingGuide();
assert.equal(field.value, command);
assert.equal(movements.children.length, 3);
bt2.value = "unused";
renderRoutingPlan();
assert.equal(field.value, "");
assert.equal(movements.children.length, 0);
bt2.value = "laptop";
renderRoutingPlan();
assert.equal(field.value, command);
lan.value = "laptop"; bt1.value = "music"; bt2.value = "tablet";
renderRoutingPlan();
assert.equal(movements.children.length, 3);
assert.ok(movements.children.every(x => x.textContent.includes("would stay")));
resetRoutingPlan();
assert.equal(field.value, "");
assert.equal(from1.value, "unknown");
assert.equal(from2.value, "unknown");
assert.equal(status.dataset.invalid, "true");
assert.equal(movements.children.length, 0);
assert.deepEqual([lan.value, bt1.value, bt2.value],
  ["laptop", "music", "tablet"]);
"""
        script = setup + "\n" + preview_routing_planner_source() + "\n" + tests
        result = subprocess.run(["node", "-e", script],
                                capture_output=True, text=True, timeout=15,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_browser_source_preview_never_confirms_or_transmits(self):
        script = PREVIEW.read_text(encoding="utf-8")
        source = preview_routing_planner_source()
        assert "function buildLocalRoutingPreview" in source
        self.assertNotIn("--confirm-local-route-change", source)
        self.assertNotIn("--if-preview-revision", source)
        self.assertNotIn("window.open(", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("navigator.clipboard", source)
        self.assertIn('byId("routing-guide-command")', source)
        self.assertIn('byId("routing-guide-from-bt1")', source)
        self.assertIn('byId("routing-guide-from-bt2")', source)
        self.assertIn('byId("routing-guide-from-" + role).addEventListener("change", renderRoutingGuide);', script)
        self.assertIn('value="unknown"', (ROOT / "web" / "index.html").read_text(encoding="utf-8"))


class ControlsFirstDashboardTests(unittest.TestCase):
    """The live dashboard must remain useful without scrolling past a lab UI."""

    def test_mixer_controls_precede_long_diagnostics_and_are_unique(self):
        markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertLess(markup.index('id="channels"'),
                        markup.index('class="routing-summary"'))
        self.assertLess(markup.index('id="master"'),
                        markup.index('class="routing-summary"'))
        self.assertLess(markup.index('id="channels"'),
                        markup.index('class="routing-plan-disclosure"'))
        self.assertIn('data-t="previewNotice"', markup)
        self.assertIn('id="routing-routes"', markup)
        self.assertIn('id="routing-freshness"', markup)
        self.assertIn('id="routing-diagnostic"', markup)
        ids = re.findall(r'\bid="([^"]+)"', markup)
        self.assertEqual(len(ids), len(set(ids)), "Duplicate HTML id breaks JS events")
        for identity in (
                "channels", "master", "master-value", "routing-recheck",
                "routing-recheck-status", "routing-history-list",
                "routing-history-clear", "routing-observation-usb",
                "routing-observations-reset", "routing-export",
                "routing-compare-file", "routing-compare-table",
                "routing-compare-observations-table", "routing-plan-lan",
                "routing-plan-bt1", "routing-plan-bt2", "routing-plan-list",
                "routing-plan-reset", "routing-guide-from-bt1",
                "routing-guide-from-bt2", "routing-guide-command",
                "routing-guide-comparison-list", "routing-tools-panel"):
            with self.subTest(identity=identity):
                self.assertEqual(ids.count(identity), 1)

    def test_optional_disclosures_preserve_nested_tools_and_status_visibility(self):
        class DetailsTree(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.panel_attrs = {}
                self.belongs_to = {}
                self.sequence = []

            def handle_starttag(self, tag, attrs):
                attr = dict(attrs)
                if tag == "details":
                    name = attr.get("class", "")
                    self.stack.append(name)
                    self.panel_attrs[name] = attr
                    self.sequence.append(name)
                if "id" in attr:
                    self.belongs_to[attr["id"]] = tuple(self.stack)

            def handle_endtag(self, tag):
                if tag == "details":
                    if not self.stack:
                        raise AssertionError("Unexpected closing details element")
                    self.stack.pop()

        markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        dom = DetailsTree()
        dom.feed(markup)
        dom.close()
        self.assertEqual(dom.stack, [], "Advanced panels are not properly closed")
        self.assertEqual(dom.sequence, [
            "eq-operator-guide", "routing-tools-panel",
            "routing-history-panel", "routing-compare-panel",
            "routing-plan-disclosure"
        ])
        for name in ("eq-operator-guide", "routing-tools-panel",
                     "routing-plan-disclosure"):
            self.assertNotIn("open", dom.panel_attrs[name])
        for identity in (
                "eq-guide-slot", "eq-guide-preview-command",
                "eq-guide-copy-preview", "eq-guide-compare-command",
                "eq-guide-copy-compare", "eq-guide-copy-status",
                "eq-guide-transfer-mode", "eq-guide-transfer-source",
                "eq-guide-transfer-target", "eq-guide-transfer-command",
                "eq-guide-copy-transfer", "eq-guide-transfer-feedback",
                "eq-guide-neutral-slot", "eq-guide-preset-choice",
                "eq-guide-preset-curve", "eq-guide-neutral-command",
                "eq-guide-neutral-feedback", "eq-guide-copy-neutral"):
            with self.subTest(identity=identity):
                self.assertIn("eq-operator-guide", dom.belongs_to[identity])
        for identity in (
                "routing-history-list", "routing-history-clear",
                "routing-observation-usb", "routing-observation-three",
                "routing-observations-reset", "routing-export",
                "routing-compare-file", "routing-compare-table",
                "routing-compare-observations-table"):
            with self.subTest(identity=identity):
                self.assertIn("routing-tools-panel", dom.belongs_to[identity])
        for identity in (
                "routing-plan-lan", "routing-plan-bt1", "routing-plan-bt2",
                "routing-plan-status", "routing-guide-from-bt1",
                "routing-guide-command", "routing-guide-comparison-list"):
            with self.subTest(identity=identity):
                self.assertIn("routing-plan-disclosure", dom.belongs_to[identity])
        for identity in ("channels", "master", "routing-routes",
                         "routing-freshness", "routing-diagnostic",
                         "routing-recheck"):
            self.assertNotIn("routing-tools-panel", dom.belongs_to[identity])
            self.assertNotIn("routing-plan-disclosure", dom.belongs_to[identity])
            self.assertNotIn("eq-operator-guide", dom.belongs_to[identity])
        self.assertIn('<summary data-t="eqGuideTitle">', markup)
        self.assertIn('<summary data-t="routingToolsTitle">', markup)
        self.assertIn('<summary data-t="routingPlanDisclosureTitle">', markup)

    def test_disclosures_are_localized_keyboard_accessible_and_no_buttons_added(self):
        markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        for language in ("en", "de", "es", "fr", "it"):
            data = json.loads((LOCALES / (language + ".json")).read_text(
                encoding="utf-8"))
            for key in ("routingToolsTitle", "routingToolsNote",
                        "routingPlanDisclosureTitle",
                        "routingPlanDisclosureNote"):
                with self.subTest(language=language, key=key):
                    self.assertTrue(data[key].strip())
                    self.assertIn('data-t="' + key + '"', markup)
        self.assertIn(".routing-tools-panel>summary:focus-visible", styles)
        self.assertIn(".routing-plan-disclosure>summary:focus-visible", styles)
        self.assertIn("@media(max-width:560px)", styles)
        # Only native details/summary disclosures; retain existing buttons.
        self.assertNotIn('id="routing-tools-toggle"', markup)
        self.assertNotIn('id="routing-plan-toggle"', markup)
        self.assertEqual(markup.count('id="routing-export"'), 1)
        self.assertEqual(markup.count('id="routing-recheck"'), 1)
