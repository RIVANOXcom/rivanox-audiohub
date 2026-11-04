// SPDX-License-Identifier: AGPL-3.0-only
// Dependency-free browser simulation for locale loading and screen-reader labels.
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const locale = code => JSON.parse(fs.readFileSync(path.join(root, "web", "locales", code + ".json"), "utf8"));

class Element {
  constructor() {
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.listeners = {};
    this.textContent = "";
    this.value = "";
  }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
}

function browser() {
  const nodes = Object.fromEntries(
    ["language", "master", "master-value", "channels"].map(id => [id, new Element()])
  );
  const speaker = new Element();
  speaker.dataset.t = "speakerState";
  const document = {
    documentElement: {lang: "en"},
    getElementById: id => nodes[id],
    createElement: () => new Element(),
    querySelectorAll: selector => selector === "[data-t]" ? [speaker] : [],
    querySelector: selector => selector === '[data-t="speakerState"]' ? speaker : null
  };
  const values = new Map();
  const pending = [];
  const fetch = url => {
    if (url === "./api/status") {
      return Promise.resolve({ok: true, json: async () => ({fresh: false})});
    }
    return new Promise((resolve, reject) => pending.push({url, resolve, reject, active: true}));
  };
  vm.runInNewContext(app, {
    document,
    navigator: {languages: ["en-US"]},
    localStorage: {getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value)},
    fetch,
    setInterval: () => {}
  }, {filename: "web/app.js"});

  function request(code) {
    const item = pending.find(entry => entry.active && entry.url === "./locales/" + code + ".json");
    assert.ok(item, "expected pending locale " + code);
    item.active = false;
    return item;
  }
  return {
    document, nodes, values, pending,
    select(code) { nodes.language.listeners.change({target: {value: code}}); },
    resolve(code, payload = locale(code)) {
      request(code).resolve({ok: true, json: async () => payload});
    },
    reject(code) { request(code).reject(new Error("Simulated unavailable locale")); },
    mute(channelIndex = 0) { return nodes.channels.children[channelIndex].children[0].children[1]; }
  };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

async function main() {
  const ui = browser();
  ui.resolve("en");
  await settle();
  assert.equal(ui.nodes.language.attrs["aria-label"], "Language");
  assert.equal(ui.mute().attrs["aria-label"], "Mute: Phone · Music");

  // A slow old request must not overwrite the latest manual selection.
  ui.select("de");
  ui.select("fr");
  ui.resolve("fr");
  await settle();
  assert.equal(ui.document.documentElement.lang, "fr");
  assert.equal(ui.values.get("audiohub.locale"), "fr");
  assert.equal(ui.nodes.language.attrs["aria-label"], "Langue");
  assert.equal(ui.mute().attrs["aria-label"], "Couper le son: Téléphone · Musique");
  ui.mute().listeners.click();
  assert.equal(ui.mute().attrs["aria-label"], "Rétablir le son: Téléphone · Musique");
  ui.resolve("de");
  await settle();
  assert.equal(ui.document.documentElement.lang, "fr");
  assert.equal(ui.values.get("audiohub.locale"), "fr");

  // Invalid JSON shape triggers English fallback, and both language selectors agree.
  const invalid = browser();
  invalid.resolve("en");
  await settle();
  invalid.select("de");
  invalid.resolve("de", []);
  await settle();
  invalid.resolve("en");
  await settle();
  assert.equal(invalid.document.documentElement.lang, "en");
  assert.equal(invalid.nodes.language.value, "en");
  assert.equal(invalid.nodes.language.attrs["aria-label"], "Language");

  // A rejected stale request must not start a fallback that overrides a newer choice.
  const stale = browser();
  stale.resolve("en");
  await settle();
  stale.select("de");
  stale.select("fr");
  stale.resolve("fr");
  await settle();
  stale.reject("de");
  await settle();
  assert.equal(stale.document.documentElement.lang, "fr");
  assert.equal(stale.pending.filter(item => item.active && item.url.endsWith("/en.json")).length, 0);
  console.log("locale runtime: 3 scenarios passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
