// SPDX-License-Identifier: AGPL-3.0-only
// UI prototype only: controls intentionally do not send device commands.
"use strict";
(() => {
  const LANGUAGES = ["en", "de", "es", "fr", "it"];
  const CHANNELS = ["music", "laptop", "tablet"];
  const BANDS = ["bass", "mid", "treble"];
  // Stable PipeWire slots are internal routing IDs, not device categories.
  const SLOT_INDEX = { music: 1, laptop: 2, tablet: 3 };
  const PREVIEW_LABEL_KEY = "audiohub.preview.input-labels.v1";
  const previewLabels = Object.create(null);
  const validName = raw => {
    if (typeof raw !== "string") return null;
    const name = raw.trim();
    // Mirror the device-local model. User-controlled content is NEVER HTML.
    if (!name || Array.from(name).length > 32 || /[\p{C}<>]/u.test(name)) return null;
    return name;
  };
  try {
    const stored = JSON.parse(localStorage.getItem(PREVIEW_LABEL_KEY) || "{}");
    if (stored && typeof stored === "object" && !Array.isArray(stored)) {
      for (const slot of CHANNELS) {
        const name = validName(stored[slot]);
        if (name) previewLabels[slot] = name;
      }
    }
  } catch (_) { /* localStorage is optional in embedded/private browsing */ }
  const state = {
    master: 70,
    music: { volume: 65, mute: false, bass: 0, mid: 0, treble: 0 },
    laptop: { volume: 50, mute: false, bass: 0, mid: 0, treble: 0 },
    tablet: { volume: 50, mute: false, bass: 0, mid: 0, treble: 0 }
  };
  let words = {};
  let languageRequestId = 0;
  let deviceHealth = null;
  const byId = id => document.getElementById(id);
  const tr = key => words[key] || key;
  const displayName = channel => previewLabels[channel] || tr("input" + SLOT_INDEX[channel]);
  function savePreviewLabels() {
    try { localStorage.setItem(PREVIEW_LABEL_KEY, JSON.stringify(previewLabels)); }
    catch (_) { /* A browser without storage still supports session-only preview names. */ }
  }
  const selectedLanguage = () => {
    let stored;
    try { stored = localStorage.getItem("audiohub.locale"); } catch (_) {}
    if (LANGUAGES.includes(stored)) return stored;
    for (const name of (navigator.languages || [navigator.language || "en"])) {
      const language = name.toLowerCase().split("-")[0];
      if (LANGUAGES.includes(language)) return language;
    }
    return "en";
  };
  function control(key, min, max, value, channel, unit = "") {
    const container = document.createElement("div");
    container.className = "control";
    const label = document.createElement("label");
    label.className = "slider-title";
    const id = channel + "-" + key;
    label.setAttribute("for", id);
    const title = document.createElement("span");
    title.textContent = tr(key);
    const readout = document.createElement("output");
    readout.setAttribute("for", id);
    readout.textContent = value + unit;
    label.append(title, readout);
    const range = document.createElement("input");
    Object.assign(range, { type: "range", min, max, value, id });
    range.setAttribute("aria-label", tr(key) + ": " + displayName(channel));
    range.addEventListener("input", () => {
      state[channel][key] = Number(range.value);
      readout.textContent = range.value + unit;
    });
    container.append(label, range);
    return container;
  }
  function drawChannels() {
    const target = byId("channels");
    target.replaceChildren();
    for (const channel of CHANNELS) {
      const card = document.createElement("section");
      card.className = "card";
      const top = document.createElement("div");
      top.className = "card-top";
      const heading = document.createElement("h3");
      heading.textContent = displayName(channel);
      const mute = document.createElement("button");
      mute.type = "button";
      const updateMute = () => {
        mute.textContent = tr(state[channel].mute ? "unmute" : "mute");
        mute.setAttribute("aria-pressed", String(state[channel].mute));
      };
      mute.addEventListener("click", () => {
        state[channel].mute = !state[channel].mute;
        updateMute();
      });
      updateMute();
      top.append(heading, mute);
      card.append(top);
      const identity = document.createElement("div");
      identity.className = "channel-identity";
      const label = document.createElement("label");
      label.className = "channel-name-label";
      const inputId = channel + "-display-name";
      label.htmlFor = inputId;
      label.textContent = tr("inputName");
      const nameInput = document.createElement("input");
      Object.assign(nameInput, {
        id: inputId, type: "text", maxLength: 32, autoComplete: "off",
        value: displayName(channel)
      });
      nameInput.className = "channel-name-input";
      nameInput.setAttribute("aria-label", tr("inputName") + ": " + tr("input" + SLOT_INDEX[channel]));
      const renameStatus = document.createElement("span");
      renameStatus.className = "channel-name-status";
      renameStatus.setAttribute("role", "status");
      nameInput.addEventListener("change", () => {
        const name = validName(nameInput.value);
        const fallback = tr("input" + SLOT_INDEX[channel]);
        if (!name || CHANNELS.some(slot => slot !== channel &&
            displayName(slot).toLocaleLowerCase() === name.toLocaleLowerCase())) {
          nameInput.value = displayName(channel);
          renameStatus.textContent = tr("invalidInputName");
          return;
        }
        if (name === fallback) delete previewLabels[channel];
        else previewLabels[channel] = name;
        heading.textContent = displayName(channel);
        nameInput.value = displayName(channel);
        // Browser display preference only. No authenticated device API exists.
        savePreviewLabels();
        renameStatus.textContent = tr("previewNamesOnly");
      });
      const source = document.createElement("p");
      source.className = "channel-hint";
      source.textContent = tr("sourceHint" + SLOT_INDEX[channel]);
      identity.append(label, nameInput, source, renameStatus);
      card.append(identity);
      card.append(control("volume", 0, 100, state[channel].volume, channel, "%"));
      const headingEq = document.createElement("p");
      headingEq.className = "eq-title";
      headingEq.textContent = tr("equalizer");
      card.append(headingEq);
      for (const band of BANDS) card.append(control(band, -12, 12, state[channel][band], channel, " dB"));
      target.append(card);
    }
  }
  function renderHardwareStatus() {
    const node = document.querySelector('[data-t="speakerState"]');
    if (!node) return;
    node.textContent = (deviceHealth && deviceHealth.fresh)
      ? tr(deviceHealth.usb_connected ? "speakerConnected" : "speakerDisconnected")
      : tr("speakerState");
  }
  async function readDeviceStatus() {
    try {
      const response = await fetch("./api/status", {cache: "no-store"});
      if (!response.ok) throw new Error("Status unavailable");
      const json = await response.json();
      deviceHealth = json && typeof json === "object" ? json : null;
    } catch (_) {
      deviceHealth = null;
    }
    renderHardwareStatus();
  }
  function translate() {
    document.querySelectorAll("[data-t]").forEach(node => { node.textContent = tr(node.dataset.t); });
    byId("master").setAttribute("aria-label", tr("master"));
    drawChannels();
    renderHardwareStatus();
  }
  async function setLanguage(language) {
    // Late locale replies must not overwrite newer user choices.
    const requestId = ++languageRequestId;
    if (!LANGUAGES.includes(language)) language = "en";
    let data;
    try {
      const response = await fetch("./locales/" + language + ".json", {cache: "no-cache"});
      if (!response.ok) throw new Error("Locale unavailable");
      data = await response.json();
    } catch (_) {
      if (requestId !== languageRequestId) return;
      if (language !== "en") return setLanguage("en");
      words = { tagline: "All your audio. One place." };
      translate();
      return;
    }
    if (requestId !== languageRequestId) return;
    words = data;
    document.documentElement.lang = language;
    byId("language").value = language;
    try { localStorage.setItem("audiohub.locale", language); } catch (_) {}
    translate();
  }
  byId("language").addEventListener("change", event => setLanguage(event.target.value));
  byId("master").addEventListener("input", event => {
    state.master = Number(event.target.value);
    byId("master-value").textContent = state.master + "%";
  });
  setLanguage(selectedLanguage());
  readDeviceStatus();
  setInterval(readDeviceStatus, 5000);
})();
