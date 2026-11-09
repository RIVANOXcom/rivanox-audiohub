# SPDX-License-Identifier: AGPL-3.0-only
"""The shipped HTML boot-report viewer: standalone browser and asset tests."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audiohub.webserver import ALLOWED

VIEWER = ROOT / "web/boot-report-viewer.html"


class OfflineBootViewerTests(unittest.TestCase):
    def test_viewer_is_local_self_contained_and_served_as_static_read_only_asset(self):
        source = VIEWER.read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", source)
        self.assertIn("connect-src 'none'", source)
        self.assertIn("default-src 'none'", source)
        self.assertIn('type="file"', source)
        self.assertIn('id="report-file"', source)
        self.assertIn('role="status"', source)
        self.assertIn('id="language"', source)
        self.assertIn('href="./boot-report-viewer.html"',
                      (ROOT / "web/index.html").read_text(encoding="utf-8"))
        self.assertEqual(ALLOWED["/boot-report-viewer.html"],
                         ("boot-report-viewer.html", "text/html; charset=utf-8"))
        self.assertNotIn("<script src=", source)
        self.assertNotIn("http://", source)
        self.assertNotIn("https://", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("XMLHttpRequest", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("navigator.sendBeacon", source)
        self.assertLess(len(source.encode("utf-8")), 512 * 1024)

    def test_locales_have_five_language_entry_parity(self):
        dictionaries = {
            language: json.loads((ROOT / ("web/locales/" + language + ".json")).read_text(encoding="utf-8"))
            for language in ("en", "de", "es", "fr", "it")
        }
        self.assertTrue(all(set(d) == set(dictionaries["en"]) for d in dictionaries.values()))
        for language, dictionary in dictionaries.items():
            for key in ("bootViewerTitle", "bootViewerNotice", "bootViewerOpen"):
                self.assertIn(key, dictionary)
                self.assertGreater(len(dictionary[key]), 12)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_real_browser_script_sanitizes_and_localizes_offline_without_io(self):
        # Execute the real inline JS, not a rewritten Python reimplementation.
        # No browser networking, DOM insertion of user strings or persistence
        # functions are available in this isolated environment.
        harness = r'''
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const found = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(found, "Viewer must have exactly one self-contained inline script");
const listeners = Object.create(null);
const nodes = Object.create(null);
const document = {
  documentElement: {lang: "en"},
  getElementById(id) {
    if (!nodes[id]) {
      nodes[id] = {
        value: id === "language" ? "en" : "",
        textContent: "", files: null,
        addEventListener(event, fn) { listeners[id + ":" + event] = fn; }
      };
    }
    return nodes[id];
  }
};
const ctx = vm.createContext({document});
vm.runInContext(found[1], ctx, {timeout: 3000});
const el = id => document.getElementById(id);
const report = {
  schema:"rivanox-audiohub-offline-boot-diagnostic/1",
  classification:"UNVERIFIED_ALPHA_OFFLINE_TEST_ONLY",
  owner_authenticated:false,hardware_accepted:false,
  phone_wifi_provisioned:false,network_configuration:"not_inspected",
  bluetooth_pairing_state:"known_devices",bluetooth_paired_devices:1,
  device_name:"SECRET-PRIVATE-PHONE",
  ssid:"SECRET-PRIVATE-WIFI",
  snapshots:[
    {seconds_since_probe_start:0,usb_audio_detected:false,
     bluetooth_controller_present:false,runtime_status:"unavailable_or_stale",
     private_mac:"AA:BB:CC:DD:EE:FF"},
    {seconds_since_probe_start:600,usb_audio_detected:true,
     bluetooth_controller_present:true,runtime_status:"recent",
     device_password:"DO-NOT-DISPLAY"}
  ]
};
const good = JSON.stringify(report);
const source = found[1];
assert.ok(source.includes("function summarizeReport("));
assert.ok(source.includes("Object.freeze("));
const file = raw => ({size:Buffer.byteLength(raw,"utf8"),text:async()=>raw});
(async () => {
  el("report-file").files = [file(good)];
  await listeners["report-file:change"]();
  assert.equal(el("pairing-value").textContent, "Known device(s)");
  assert.equal(el("paired-value").textContent, "1");
  assert.equal(el("usb-value").textContent, "Detected");
  assert.equal(el("controller-value").textContent, "Detected");
  assert.equal(el("snapshots-value").textContent, "2");
  assert.equal(el("runtime-value").textContent, "Reported recently");
  assert.match(el("advice").textContent,/Reconnect/);
  assert.equal(el("report-file").value,"");
  let seen = Object.values(nodes).map(e=>e.textContent).join("\n");
  for(const privateText of ["SECRET-PRIVATE-PHONE","SECRET-PRIVATE-WIFI","DO-NOT-DISPLAY","AA:BB:CC"])
    assert.equal(seen.includes(privateText),false);
  // Changing browser locale re-renders a previously sanitized snapshot.
  el("language").value = "de";
  listeners["language:change"]();
  assert.equal(document.documentElement.lang,"de");
  assert.equal(el("pairing-value").textContent,"Bekannte Geräte");
  assert.match(el("advice").textContent,/verbinden/);
  for(const language of ["es","fr","it"]){
    el("language").value = language;
    listeners["language:change"]();
    assert.equal(document.documentElement.lang,language);
    assert.notEqual(el("pairing-value").textContent,"—");
  }
  // Malicious or unsupported files must clear stale rendered result.
  for(const [reason,bad] of [
    ["owner status", JSON.stringify({...report, owner_authenticated:true})],
    ["release claims", JSON.stringify({...report, classification:"APPROVED"})],
    ["unknown Bluetooth state", JSON.stringify({...report, bluetooth_pairing_state:"SECRET-USER-NAME"})],
    ["invalid paired count", JSON.stringify({...report, bluetooth_paired_devices:999})],
    ["broken JSON", "{oops"],
    ["missing snapshots", JSON.stringify({...report,snapshots:[]})],
    ["invalid observation time", JSON.stringify({...report,snapshots:[{...report.snapshots[1],
      seconds_since_probe_start:-1}]})],
    ["false Wi-Fi status", JSON.stringify({...report,phone_wifi_provisioned:true})],
    ["oversized", "x".repeat(5000)]
  ]){
    el("report-file").files = [file(bad)];
    await listeners["report-file:change"]();
    assert.equal(el("pairing-value").textContent,"—",reason);
    assert.equal(el("paired-value").textContent,"—",reason);
    assert.notEqual(el("feedback").textContent,"",reason);
  }
  // An older valid source report is allowed but cannot invent new pairing fields.
  const older = {...report};
  delete older.bluetooth_pairing_state;
  delete older.bluetooth_paired_devices;
  el("language").value = "en";
  listeners["language:change"]();
  el("report-file").files = [file(JSON.stringify(older))];
  await listeners["report-file:change"]();
  assert.equal(el("pairing-value").textContent,"Unavailable");
  assert.match(el("advice").textContent,/older report/);
  // A manual reset revokes a pending async selection, no ghost results.
  let resolveRead;
  el("report-file").files=[{size:good.length,text:()=>new Promise(r=>resolveRead=r)}];
  const pending = listeners["report-file:change"]();
  listeners["clear:click"]();
  resolveRead(good);
  await pending;
  assert.equal(el("pairing-value").textContent,"—");
  assert.equal(el("feedback").textContent,"No file opened.");
  console.log("offline SD viewer browser integration PASS");
})().catch(error => { console.error(error); process.exitCode=1; });
'''
        proc = subprocess.run(
            ["node", "-e", harness, str(VIEWER)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("browser integration PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
