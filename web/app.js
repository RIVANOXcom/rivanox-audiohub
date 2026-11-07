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
  let statusChecked = false;
  let statusRequestId = 0;
  let statusReceivedAt = null;
  let lastManualStatusRequestAt = -Infinity;
  const routingHistory = [];
  let lastRoutingHistorySignature = null;
  let comparisonBaseline = null;
  let comparisonLoadId = 0;
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
  // Locale requests can finish while someone is typing. Keep that unsaved,
  // browser-only draft and the focused control when rebuilding translated cards.
  function captureChannelEditState(target) {
    const drafts = Object.create(null);
    for (const channel of CHANNELS) {
      const input = byId(channel + "-display-name");
      if (input && input.dataset.editing === "true") drafts[channel] = input.value;
    }
    const focused = document.activeElement;
    const focusedId = focused && target.contains(focused) ? focused.id : null;
    const selection = focusedId && focused.type === "text" &&
      typeof focused.selectionStart === "number" &&
      typeof focused.selectionEnd === "number"
      ? [focused.selectionStart, focused.selectionEnd] : null;
    return {drafts, focusedId, selection};
  }
  function restoreChannelEditState(snapshot) {
    const focused = snapshot.focusedId && byId(snapshot.focusedId);
    if (!focused) return;
    focused.focus({preventScroll: true});
    if (snapshot.selection && typeof focused.setSelectionRange === "function") {
      focused.setSelectionRange(snapshot.selection[0], snapshot.selection[1]);
    }
  }
  // Keep screen-reader slider names in sync with renamed display inputs.
  function updateChannelControlLabels(channel) {
    for (const key of ["volume", ...BANDS]) {
      const range = byId(channel + "-" + key);
      if (range) range.setAttribute("aria-label", tr(key) + ": " + displayName(channel));
    }
  }
  function drawChannels() {
    const target = byId("channels");
    const editState = captureChannelEditState(target);
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
        mute.setAttribute("aria-label",
          tr(state[channel].mute ? "unmute" : "mute") + ": " + displayName(channel));
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
        id: inputId, type: "text", maxLength: 64, autoComplete: "off",
        value: displayName(channel)
      });
      nameInput.className = "channel-name-input";
      if (editState.drafts[channel] !== undefined) {
        nameInput.value = editState.drafts[channel];
        nameInput.dataset.editing = "true";
      }
      nameInput.setAttribute("aria-label", tr("inputName") + ": " + tr("input" + SLOT_INDEX[channel]));
      const renameStatus = document.createElement("span");
      renameStatus.id = inputId + "-feedback";
      renameStatus.className = "channel-name-status";
      renameStatus.setAttribute("role", "status");
      // The existing live status doubles as the input's spoken description.
      // Mark only the currently invalid text as invalid, not a reverted value.
      nameInput.setAttribute("aria-describedby", renameStatus.id);
      const setNameInvalid = invalid => {
        nameInput.setAttribute("aria-invalid", String(invalid));
        renameStatus.dataset.invalid = String(invalid);
      };
      setNameInvalid(false);
      // HTML maxlength counts UTF-16 units, while validName counts Unicode
      // characters. Allow up to 32 emoji (64 units), but warn and reject
      // any name that violates the actual 32-character validation rule.
      const hasInvalidName = () => {
        const name = validName(nameInput.value);
        return !name || CHANNELS.some(slot => slot !== channel &&
          displayName(slot).toLocaleLowerCase() === name.toLocaleLowerCase());
      };
      if (nameInput.dataset.editing === "true" && hasInvalidName()) {
        setNameInvalid(true);
        renameStatus.textContent = tr("invalidInputName");
      }
      nameInput.addEventListener("input", () => {
        nameInput.dataset.editing = "true";
        const invalid = hasInvalidName();
        setNameInvalid(invalid);
        renameStatus.textContent = invalid ? tr("invalidInputName") : "";
      });
      nameInput.addEventListener("change", () => {
        nameInput.dataset.editing = "false";
        const name = validName(nameInput.value);
        const fallback = tr("input" + SLOT_INDEX[channel]);
        if (hasInvalidName()) {
          nameInput.value = displayName(channel);
          setNameInvalid(false);
          renameStatus.textContent = tr("invalidInputName");
          return;
        }
        if (name === fallback) delete previewLabels[channel];
        else previewLabels[channel] = name;
        heading.textContent = displayName(channel);
        nameInput.value = displayName(channel);
        updateMute();
        updateChannelControlLabels(channel);
        // Browser display preference only. No authenticated device API exists.
        savePreviewLabels();
        setNameInvalid(false);
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
    restoreChannelEditState(editState);
  }
  function statusIsRecent() {
    // The API's own fresh flag is necessary but not sufficient: a hanging
    // poll must not leave the previous snapshot visibly "recent" forever.
    // Monotonic time is unaffected by manual browser clock adjustments.
    const elapsed = statusReceivedAt === null
      ? -1 : performance.now() - statusReceivedAt;
    return elapsed >= 0 && elapsed <= 15000;
  }
  function renderHardwareStatus() {
    const node = document.querySelector('[data-t="speakerState"]');
    if (!node) return;
    const validHealth = statusIsRecent() && deviceHealth &&
      deviceHealth.fresh === true &&
      typeof deviceHealth.usb_connected === "boolean";
    node.textContent = validHealth
      ? tr(deviceHealth.usb_connected ? "speakerConnected" : "speakerDisconnected")
      : tr(statusChecked ? "speakerStatusUnavailable" : "speakerState");
  }
  function safeRoutingHealth() {
    // Share one strictly validated projection between the screen and export.
    // Only whitelisted, bounded public fields are copied; never raw JSON.
    const health = deviceHealth;
    const bounds = [
      ["active_routes", 3],
      ["bluetooth_sources", 2],
      ["virtual_channel_count", 3]
    ];
    if (!statusIsRecent() || !health || health.fresh !== true ||
        typeof health.usb_connected !== "boolean" ||
        !bounds.every(([key, limit]) => Number.isInteger(health[key]) &&
          health[key] >= 0 && health[key] <= limit)) return null;
    return {
      usb_connected: health.usb_connected,
      active_routes: health.active_routes,
      bluetooth_sources: health.bluetooth_sources,
      virtual_channel_count: health.virtual_channel_count
    };
  }
  function captureRoutingHistory(summary) {
    if (!statusChecked) return;
    // Record only transitions. This is an in-memory browser note, not a
    // hardware log or proof of sound. Never copy raw /api/status objects.
    const signature = summary
      ? [summary.usb_connected, summary.active_routes,
        summary.bluetooth_sources, summary.virtual_channel_count].join("|")
      : "unavailable";
    if (signature === lastRoutingHistorySignature) return;
    lastRoutingHistorySignature = signature;
    const observedAt = new Date();
    routingHistory.push({
      at: observedAt.toLocaleTimeString(),
      // An explicit browser-provided UTC timestamp is exportable without
      // trusting locale-specific or other uncontrolled formatting.
      at_utc: observedAt.toISOString(),
      // safeRoutingHealth only returns fixed, bounded public fields.
      health: summary ? {...summary} : null
    });
    if (routingHistory.length > 8) routingHistory.shift();
  }
  function renderRoutingHistory() {
    const list = byId("routing-history-list");
    if (!list) return;
    list.replaceChildren();
    if (!routingHistory.length) {
      const empty = document.createElement("li");
      empty.textContent = tr("routingHistoryEmpty");
      list.append(empty);
      return;
    }
    for (const entry of routingHistory) {
      const item = document.createElement("li");
      const health = entry.health;
      item.textContent = entry.at + " · " + (health
        ? tr(health.usb_connected ? "speakerConnected" : "speakerDisconnected") +
          " · " + tr("routingRoutes") + ": " + health.active_routes +
          " · " + tr("routingBluetooth") + ": " + health.bluetooth_sources +
          " · " + tr("routingChannels") + ": " + health.virtual_channel_count
        : tr("routingUnavailable"));
      list.append(item);
    }
  }
  function clearRoutingHistory() {
    routingHistory.length = 0;
    // Leave the current snapshot signature unchanged: clearing the list
    // must not immediately recreate the same entry on a locale change.
    renderRoutingHistory();
    const feedback = byId("routing-history-status");
    if (feedback) feedback.textContent = tr("routingHistoryCleared");
  }
  function renderRoutingSummary() {
    const summary = safeRoutingHealth();
    captureRoutingHistory(summary);
    renderRoutingHistory();
    const usable = summary !== null;
    const ids = [
      ["active_routes", "routing-routes"],
      ["bluetooth_sources", "routing-bluetooth"],
      ["virtual_channel_count", "routing-channels"]
    ];
    for (const [key, id] of ids) {
      const node = byId(id);
      if (node) {
        const value = usable ? String(summary[key]) : "—";
        if (node.textContent !== value) node.textContent = value;
      }
    }
    const freshness = byId("routing-freshness");
    if (freshness) {
      const text = tr(usable ? "routingRecent" :
        (statusChecked ? "routingUnavailable" : "routingPending"));
      if (freshness.textContent !== text) freshness.textContent = text;
    }
    // Suggestions are based only on bounded, sanitized counters. They
    // never claim proof of sound, ownership, pairing or hardware fitness.
    let guidance = statusChecked ? "routingDiagUnavailable" : "routingDiagPending";
    if (usable) {
      if (!summary.usb_connected) guidance = "routingDiagUsbMissing";
      else if (summary.virtual_channel_count === 0) guidance = "routingDiagNoChannels";
      else if (summary.active_routes === 0) guidance = "routingDiagNoRoutes";
      else if (summary.bluetooth_sources === 0) guidance = "routingDiagNoBluetooth";
      else guidance = "routingDiagCountsAvailable";
    }
    const diagnostic = byId("routing-diagnostic");
    if (diagnostic) {
      const text = tr(guidance);
      if (diagnostic.textContent !== text) diagnostic.textContent = text;
    }
    renderRoutingComparison();
  }
  function safeImportedRoutingReport(report) {
    // A local file is untrusted input. Accept ONLY the v4 fixed scalar
    // status fields, not names, history, metadata or the human observations.
    if (!report || typeof report !== "object" || Array.isArray(report) ||
        report.format !== "audiohub.routing-diagnostics.v4" ||
        report.status !== "recent" ||
        typeof report.usb_connected !== "boolean") return null;
    const limits = [["active_routes", 3], ["bluetooth_sources", 2],
      ["virtual_channel_count", 3]];
    if (!limits.every(([key, max]) =>
      Number.isInteger(report[key]) && report[key] >= 0 && report[key] <= max))
      return null;
    return {
      usb_connected: report.usb_connected,
      active_routes: report.active_routes,
      bluetooth_sources: report.bluetooth_sources,
      virtual_channel_count: report.virtual_channel_count
    };
  }
  function renderRoutingComparison() {
    const table = byId("routing-compare-table");
    if (!table) return;
    table.hidden = !comparisonBaseline;
    if (!comparisonBaseline) return;
    const current = safeRoutingHealth();
    for (const key of ["usb", "active_routes", "bluetooth_sources",
      "virtual_channel_count"]) {
      const field = key === "usb" ? "usb_connected" : key;
      const previous = comparisonBaseline[field];
      const latest = current ? current[field] : null;
      const format = value => value === null ? tr("routingCompareUnknown") :
        key === "usb" ? tr(value ? "speakerConnected" : "speakerDisconnected") :
          String(value);
      byId("routing-compare-old-" + key).textContent = format(previous);
      byId("routing-compare-new-" + key).textContent = format(latest);
      byId("routing-compare-diff-" + key).textContent = latest === null
        ? tr("routingCompareUnknown") : key === "usb"
          ? tr(latest === previous ? "routingCompareUnchanged" : "routingCompareChanged")
          : latest === previous ? "0" : (latest > previous ? "+" : "") +
            String(latest - previous);
    }
    const status = byId("routing-compare-status");
    if (status) status.textContent = tr(current ?
      "routingCompareReady" : "routingCompareCurrentUnavailable");
  }
  async function loadRoutingComparison(event) {
    const requestId = ++comparisonLoadId;
    const input = event.target;
    const file = input && input.files && input.files[0];
    if (input) input.value = ""; // Permit reselecting the same local file.
    if (!file) return;
    comparisonBaseline = null;
    renderRoutingComparison();
    const feedback = byId("routing-compare-status");
    if (!Number.isSafeInteger(file.size) || file.size > 65536) {
      if (feedback) feedback.textContent = tr("routingCompareTooLarge");
      return;
    }
    try {
      if (typeof file.text !== "function") throw new Error("unsupported");
      const parsed = JSON.parse(await file.text());
      if (requestId !== comparisonLoadId) return; // Ignore an older file read.
      const projection = safeImportedRoutingReport(parsed);
      if (!projection) throw new Error("invalid report");
      comparisonBaseline = projection;
      renderRoutingComparison();
    } catch (_) {
      if (requestId !== comparisonLoadId) return;
      comparisonBaseline = null;
      renderRoutingComparison();
      if (feedback) feedback.textContent = tr("routingCompareInvalid");
    }
  }
  function clearRoutingComparison() {
    ++comparisonLoadId; // Also prevents pending older reads from taking over.
    comparisonBaseline = null;
    const fileInput = byId("routing-compare-file");
    if (fileInput) fileInput.value = "";
    renderRoutingComparison();
    const feedback = byId("routing-compare-status");
    if (feedback) feedback.textContent = tr("routingCompareCleared");
  }
  function manualSoundObservations() {
    // Explicit human observations, never sourced from device telemetry.
    // No free text, device IDs, usernames, or persistence outside this tab.
    const observation = id => {
      const node = byId("routing-observation-" + id);
      return node && ["heard", "not_heard"].includes(node.value)
        ? node.value : "not_tested";
    };
    return {
      usb_output_audio: observation("usb"),
      bluetooth_source_audio: observation("bluetooth"),
      three_inputs_simultaneously_audible: observation("three"),
      two_bluetooth_sources_simultaneously_audible: observation("dual-bt"),
      usb_audio_after_reconnect: observation("usb-reconnect")
    };
  }
  function resetManualSoundObservations() {
    // Reset only human-entered hearing notes. Never change live routing state.
    for (const id of ["usb", "bluetooth", "three", "dual-bt", "usb-reconnect"]) {
      const node = byId("routing-observation-" + id);
      if (node) node.value = "not_tested";
    }
    const feedback = byId("routing-observations-reset-status");
    if (feedback) feedback.textContent = tr("routingObservationsCleared");
    const exportStatus = byId("routing-export-status");
    if (exportStatus) exportStatus.textContent = "";
  }
  function safeRoutingHistoryReport() {
    // Each historical item is independently revalidated before local export.
    // Never serialize the stored UI objects or anything from the raw API.
    return routingHistory.slice(-8).map(entry => {
      const h = entry.health;
      const valid = h && typeof h.usb_connected === "boolean" &&
        Number.isInteger(h.active_routes) && h.active_routes >= 0 && h.active_routes <= 3 &&
        Number.isInteger(h.bluetooth_sources) && h.bluetooth_sources >= 0 &&
          h.bluetooth_sources <= 2 &&
        Number.isInteger(h.virtual_channel_count) && h.virtual_channel_count >= 0 &&
          h.virtual_channel_count <= 3;
      const timestamp = typeof entry.at_utc === "string" &&
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(entry.at_utc)
        ? entry.at_utc : null;
      return {
        observed_at_browser_utc: timestamp,
        status: valid ? "recent" : "unavailable",
        usb_connected: valid ? h.usb_connected : null,
        active_routes: valid ? h.active_routes : null,
        bluetooth_sources: valid ? h.bluetooth_sources : null,
        virtual_channel_count: valid ? h.virtual_channel_count : null
      };
    });
  }
  function safeRoutingReport() {
    const summary = safeRoutingHealth();
    // Fixed key list: no MACs, names, SSIDs, URLs, addresses, audio payloads
    // or raw diagnostics ever reach the downloaded local JSON.
    return {
      format: "audiohub.routing-diagnostics.v4",
      // Browser time is only a self-reported observation timestamp.
      recorded_at_browser_utc: new Date().toISOString(),
      status: summary ? "recent" : (statusChecked ? "unavailable" : "pending"),
      usb_connected: summary ? summary.usb_connected : null,
      active_routes: summary ? summary.active_routes : null,
      bluetooth_sources: summary ? summary.bluetooth_sources : null,
      virtual_channel_count: summary ? summary.virtual_channel_count : null,
      recent_routing_changes: safeRoutingHistoryReport(),
      operator_observations: manualSoundObservations(),
      hardware_verified: false,
      audible_playback_verified: false,
      release_approved: false
    };
  }
  function downloadRoutingDiagnostics() {
    let url = null;
    try {
      const body = JSON.stringify(safeRoutingReport(), null, 2) + "\n";
      const blob = new Blob([body], {type: "application/json;charset=utf-8"});
      url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "audiohub-routing-diagnostics.json";
      link.hidden = true;
      document.body.append(link);
      try { link.click(); }
      finally { link.remove(); }
      // Browser download activation is not evidence of successful saving.
      byId("routing-export-status").textContent = tr("routingExportRequested");
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (_) {
      if (url) URL.revokeObjectURL(url);
      byId("routing-export-status").textContent = tr("routingExportUnavailable");
    }
  }
  function requestRoutingRecheck() {
    // Human-triggered checks are independent of the five-second auto poll,
    // but throttle rapid clicks to avoid unnecessary local network traffic.
    const now = performance.now();
    if (now >= lastManualStatusRequestAt &&
        now - lastManualStatusRequestAt < 2000) return;
    lastManualStatusRequestAt = now;
    const feedback = byId("routing-recheck-status");
    if (feedback) feedback.textContent = tr("routingRecheckRequested");
    // Existing newest-response-wins protection also applies to this request.
    return readDeviceStatus();
  }
  async function readDeviceStatus() {
    // Only the most recent poll may update health or its visible state.
    const requestId = ++statusRequestId;
    // Re-check age at the start of every five-second poll, even if fetch
    // never settles. This also invalidates the user-exportable snapshot.
    renderHardwareStatus();
    renderRoutingSummary();
    try {
      const response = await fetch("./api/status", {cache: "no-store"});
      if (!response.ok) throw new Error("Status unavailable");
      const json = await response.json();
      if (requestId !== statusRequestId) return;
      deviceHealth = json && typeof json === "object" ? json : null;
      statusReceivedAt = performance.now();
    } catch (_) {
      if (requestId !== statusRequestId) return;
      deviceHealth = null;
      statusReceivedAt = null;
    }
    statusChecked = true;
    renderHardwareStatus();
    renderRoutingSummary();
  }
  function translate() {
    document.querySelectorAll("[data-t]").forEach(node => { node.textContent = tr(node.dataset.t); });
    byId("master").setAttribute("aria-label", tr("master"));
    drawChannels();
    renderHardwareStatus();
    renderRoutingSummary();
    byId("routing-export-status").textContent = "";
    byId("routing-observations-reset-status").textContent = "";
    byId("routing-recheck-status").textContent = "";
    byId("routing-history-status").textContent = "";
    if (!comparisonBaseline) byId("routing-compare-status").textContent =
      tr("routingCompareNoFile");
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
      // Use the shared commit path so failed English also updates locale metadata.
      data = { tagline: "All your audio. One place." };
    }
    if (requestId !== languageRequestId) return;
    words = data;
    document.documentElement.lang = language;
    byId("language").value = language;
    try { localStorage.setItem("audiohub.locale", language); } catch (_) {}
    translate();
  }
  byId("language").addEventListener("change", event => setLanguage(event.target.value));
  byId("routing-export").addEventListener("click", downloadRoutingDiagnostics);
  byId("routing-recheck").addEventListener("click", requestRoutingRecheck);
  byId("routing-history-clear").addEventListener("click", clearRoutingHistory);
  byId("routing-compare-file").addEventListener("change", loadRoutingComparison);
  byId("routing-compare-clear").addEventListener("click", clearRoutingComparison);
  byId("routing-observations-reset").addEventListener("click", resetManualSoundObservations);
  byId("master").addEventListener("input", event => {
    state.master = Number(event.target.value);
    byId("master-value").textContent = state.master + "%";
  });
  setLanguage(selectedLanguage());
  readDeviceStatus();
  setInterval(readDeviceStatus, 5000);
})();
