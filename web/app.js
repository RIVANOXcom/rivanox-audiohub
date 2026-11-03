// SPDX-License-Identifier: AGPL-3.0-only
// UI prototype only: controls intentionally do not send device commands.
"use strict";
(() => {
  const LANGUAGES = ["en", "de", "es", "fr", "it"];
  const CHANNELS = ["music", "laptop", "tablet"];
  const BANDS = ["bass", "mid", "treble"];
  const state = {
    master: 70,
    music: { volume: 65, mute: false, bass: 0, mid: 0, treble: 0 },
    laptop: { volume: 50, mute: false, bass: 0, mid: 0, treble: 0 },
    tablet: { volume: 50, mute: false, bass: 0, mid: 0, treble: 0 }
  };
  let words = {};
  const byId = id => document.getElementById(id);
  const tr = key => words[key] || key;
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
    range.setAttribute("aria-label", tr(key) + ": " + tr(channel));
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
      heading.textContent = tr(channel);
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
      card.append(control("volume", 0, 100, state[channel].volume, channel, "%"));
      const headingEq = document.createElement("p");
      headingEq.className = "eq-title";
      headingEq.textContent = tr("equalizer");
      card.append(headingEq);
      for (const band of BANDS) card.append(control(band, -12, 12, state[channel][band], channel, " dB"));
      target.append(card);
    }
  }
  function translate() {
    document.querySelectorAll("[data-t]").forEach(node => { node.textContent = tr(node.dataset.t); });
    byId("master").setAttribute("aria-label", tr("master"));
    drawChannels();
  }
  async function setLanguage(language) {
    if (!LANGUAGES.includes(language)) language = "en";
    let data;
    try {
      const response = await fetch("./locales/" + language + ".json", {cache: "no-cache"});
      if (!response.ok) throw new Error("Locale unavailable");
      data = await response.json();
    } catch (_) {
      if (language !== "en") return setLanguage("en");
      words = { tagline: "All your audio. One place." };
      translate();
      return;
    }
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
})();
