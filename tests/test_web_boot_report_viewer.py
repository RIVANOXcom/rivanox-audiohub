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
        self.assertIn('id="expected-sha"', source)
        self.assertIn('id="manifest-file"', source)
        self.assertIn('id="preflight-shutdown"', source)
        self.assertIn('id="identity-value"', source)
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
const observedSha = "a".repeat(40);
const report = {
  schema:"rivanox-audiohub-offline-boot-diagnostic/1",
  classification:"UNVERIFIED_ALPHA_OFFLINE_TEST_ONLY",
  owner_authenticated:false,hardware_accepted:false,
  phone_wifi_provisioned:false,network_configuration:"not_inspected",
  image_identity:{status:"embedded_unverified_alpha",source_sha:observedSha,
    pi_gen_sha:"b".repeat(40),ci_run_id:43764602858},
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
  assert.equal(el("usb-value").textContent, "USB found; route not checked");
  assert.match(el("advice").textContent,/cannot be verified/);
  assert.equal(el("controller-value").textContent, "Detected");
  assert.equal(el("snapshots-value").textContent, "2 · USB appeared after the first check");
  assert.equal(el("runtime-value").textContent, "Reported recently");
  assert.ok(el("identity-value").textContent.startsWith(observedSha));
  assert.match(el("identity-value").textContent,/Paste package SHA/);
  el("expected-sha").value=observedSha.toUpperCase();
  listeners["expected-sha:input"]();
  assert.match(el("identity-value").textContent,/MATCH/);
  el("expected-sha").value="c".repeat(40);
  listeners["expected-sha:input"]();
  assert.match(el("identity-value").textContent,/MISMATCH/);
  assert.match(el("advice").textContent,/STOP/);
  el("expected-sha").value="wrong";
  listeners["expected-sha:input"]();
  assert.match(el("identity-value").textContent,/40-character/);
  el("expected-sha").value="";
  listeners["expected-sha:input"]();
  // Real manifest picked from the SAME SHA-verified ZIP: auto-populate source
  // without retyping 40 hexadecimal characters; no network/persistence.
  const manifest = {
    schema:"rivanox-audiohub-preview-bundle/2",
    source_commit_sha:observedSha,pi_gen_commit_sha:"b".repeat(40),
    image_sha256:"d".repeat(64),github_actions_run_id:"43817391610",
    hardware_verified:false,release_approved:false,
    scope:"Temporary alpha test only, not a release",
    offline_viewer:{file:"AUDIOHUB-OFFLINE-REPORT-VIEWER.html",
      bytes:38648,sha256:"e".repeat(64)}
  };
  const manifestRaw = JSON.stringify(manifest);
  const manifestFile = raw => ({...file(raw),name:"PREVIEW-MANIFEST.json"});
  el("manifest-file").files=[manifestFile(manifestRaw)];
  await listeners["manifest-file:change"]();
  assert.equal(el("expected-sha").value,observedSha);
  assert.match(el("manifest-feedback").textContent,/loaded locally/);
  assert.match(el("identity-value").textContent,/MATCH/);
  // Fail closed on wrong filename, forged release, malformed schema or SHA.
  for(const [reason,badFile] of [
    ["wrong filename",{...manifestFile(manifestRaw),name:"other.json"}],
    ["release flag",manifestFile(JSON.stringify({...manifest,release_approved:true}))],
    ["wrong schema",manifestFile(JSON.stringify({...manifest,schema:"APPROVED"}))],
    ["invalid SHA",manifestFile(JSON.stringify({...manifest,source_commit_sha:"SECRET-WIFI"}))],
    ["missing viewer",manifestFile(JSON.stringify({...manifest,offline_viewer:null}))],
    ["oversized",manifestFile("a".repeat(9000))]
  ]) {
    el("manifest-file").files=[badFile];
    await listeners["manifest-file:change"]();
    assert.equal(el("expected-sha").value,"",reason);
    assert.match(el("manifest-feedback").textContent,/Invalid manifest/,reason);
  }
  // Manual input must win a concurrent pending asynchronous file read.
  let resolveManifest;
  el("manifest-file").files=[{name:"PREVIEW-MANIFEST.json",size:manifestRaw.length,
    text:()=>new Promise(resolve=>{resolveManifest=resolve;})}];
  const pendingManifest = listeners["manifest-file:change"]();
  el("expected-sha").value="f".repeat(40);
  listeners["expected-sha:input"]();
  resolveManifest(manifestRaw);
  await pendingManifest;
  assert.equal(el("expected-sha").value,"f".repeat(40));
  assert.match(el("manifest-feedback").textContent,/entered manually/);
  // Load a valid manifest once more; resetting clears its source status.
  el("manifest-file").files=[manifestFile(manifestRaw)];
  await listeners["manifest-file:change"]();
  assert.equal(el("expected-sha").value,observedSha);
  assert.match(el("advice").textContent,/Reconnect/);
  assert.equal(el("report-file").value,"");
  let seen = Object.values(nodes).map(e=>e.textContent).join("\n");
  for(const privateText of ["SECRET-PRIVATE-PHONE","SECRET-PRIVATE-WIFI","DO-NOT-DISPLAY","AA:BB:CC"])
    assert.equal(seen.includes(privateText),false);
  // Actual viewer detects a transient USB loss hidden by final-only display.
  const history = values => JSON.stringify({
    ...report,snapshots:values.map((v,i)=>({
      ...report.snapshots[1],usb_audio_detected:v,seconds_since_probe_start:i*30
    }))
  });
  for (const [checks,want] of [
    [[true],"1 · One USB check; no trend"],
    [[true,true],"2 · USB reported in every sampled check"],
    [[false,false],"2 · USB absent in all sampled checks"],
    [[false,true],"2 · USB appeared after the first check"],
    [[true,false],"2 · USB disappeared after detection"],
    [[false,true,false],"3 · USB appeared and disappeared"],
    [[true,false,true],"3 · USB appeared and disappeared"]
  ]) {
    el("report-file").files=[file(history(checks))];
    await listeners["report-file:change"]();
    assert.equal(el("snapshots-value").textContent,want);
    assert.ok(!el("advice").textContent.includes("SECRET-PRIVATE-PHONE"));
  }
  el("report-file").files=[file(good)];
  await listeners["report-file:change"]();
  // Real Pi4 report carries BOTH physical USB detection and direct link
  // status. A visible device alone must not be presented as a usable
  // route or audible speaker. No additional cards/buttons are needed.
  const withLast = changes => JSON.stringify({
    ...report,
    snapshots:[report.snapshots[0], {...report.snapshots[1],...changes}]
  });
  for(const [route,links,expected] of [
    [false,0,"USB found; route needs attention"],
    [true,0,"USB found; route needs attention"],
    [false,1,"USB found; route needs attention"],
    [true,1,"Direct link reported (not sound)"],
    [true,3,"Direct link reported (not sound)"]
  ]) {
    el("report-file").files = [file(withLast({
      usb_audio_route_ready:route,eq_usb_direct_links:links
    }))];
    await listeners["report-file:change"]();
    assert.equal(el("usb-value").textContent,expected);
    if(route && links)
      assert.match(el("advice").textContent,/NOT verified/);
    else
      assert.match(el("advice").textContent,/Do not assume sound/);
  }
  // Stale runtime cannot claim an active route even if old true flags
  // remain in a synthetic report.
  el("report-file").files = [file(withLast({
    runtime_status:"unavailable_or_stale",
    usb_audio_route_ready:true,eq_usb_direct_links:1
  }))];
  await listeners["report-file:change"]();
  assert.equal(el("usb-value").textContent,"USB found; route not checked");
  el("report-file").files = [file(withLast({
    usb_audio_detected:false,
    usb_audio_route_ready:true,eq_usb_direct_links:1
  }))];
  await listeners["report-file:change"]();
  assert.equal(el("usb-value").textContent,"USB device not reported");
  // Return to compatible old reports before cross-language checks.
  el("report-file").files = [file(good)];
  await listeners["report-file:change"]();
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
    assert.notEqual(el("usb-value").textContent, "undefined");
    assert.ok(el("snapshots-value").textContent.includes("2 · "));
    assert.ok(!el("snapshots-value").textContent.includes("undefined"));
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
    ["route not boolean",withLast({usb_audio_route_ready:"true",eq_usb_direct_links:1})],
    ["missing direct count",withLast({usb_audio_route_ready:true})],
    ["huge direct count",withLast({usb_audio_route_ready:true,eq_usb_direct_links:999})],
    ["negative direct count",withLast({usb_audio_route_ready:true,eq_usb_direct_links:-1})],
    ["false Wi-Fi status", JSON.stringify({...report,phone_wifi_provisioned:true})],
    ["forged identity", JSON.stringify({...report,image_identity:{status:"verified"}})],
    ["invalid image SHA", JSON.stringify({...report,image_identity:{...report.image_identity,source_sha:"SECRET"}})],
    ["extra identity data", JSON.stringify({...report,image_identity:{...report.image_identity,ssid:"SECRET-PRIVATE-WIFI"}})],
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
  delete older.image_identity;
  el("language").value = "en";
  listeners["language:change"]();
  el("report-file").files = [file(JSON.stringify(older))];
  await listeners["report-file:change"]();
  assert.equal(el("pairing-value").textContent,"Unavailable");
  assert.match(el("advice").textContent,/older report/);
  assert.equal(el("identity-value").textContent,"Image identity unavailable");
  // A manual reset revokes a pending async selection, no ghost results.
  let resolveRead;
  el("report-file").files=[{size:good.length,text:()=>new Promise(r=>resolveRead=r)}];
  const pending = listeners["report-file:change"]();
  listeners["clear:click"]();
  resolveRead(good);
  await pending;
  assert.equal(el("pairing-value").textContent,"—");
  assert.equal(el("feedback").textContent,"No file opened.");
  assert.equal(el("expected-sha").value,"");
  assert.equal(el("manifest-feedback").textContent,"No manifest selected; manual SHA entry is available.");
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
