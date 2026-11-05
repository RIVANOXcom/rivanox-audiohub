# AudioHub Pi4 audio graph observability – hardware-acceptance aid

**Status:** Experimental, privacy-safe topology observation, not sound or
security verification. PAPA `PJ2611-0001:R001`, AH-009 #3275.
Built on the previously verified [three-input flexible-route PR #29](https://github.com/RIVANOXcom/rivanox-audiohub/pull/29).
The separately reviewed [hardware topology PR #13](https://github.com/RIVANOXcom/rivanox-audiohub/pull/13)
is ported into a new isolated stacked branch; existing PR heads remain unchanged.

## What this specifically adds

A working audio graph requires more than three named virtual sinks:
a device can advertise `audiohub.music`, `audiohub.laptop`,
`audiohub.tablet` and USB hardware while **no active PipeWire Link**
actually connects an EQ playback output to a USB sink.

The new read-only `audiohub.audio_graph.summarize_links` inspects
PipeWire `PipeWire:Interface:Link` records using numeric
`info.output-node-id` / `info.input-node-id`. It matches
`audiohub.<slot>.output` to the **single selected USB output** using
the same USB-selection policy as the live runtime. It does **not**
print or store node names, node IDs, port IDs, MACs, addresses, SSIDs,
serial numbers or audio payloads.

The Pi runtime now adds **only**:
- `pipewire_links_inspected`: bounded number of distinct valid links.
- `eq_output_usb_direct_links`: a runtime-local allowlisted list of
  internal slots where a *direct* EQ output → selected USB link exists.

The existing FAT boot `AUDIOHUB-TEST-REPORT.json` writes only the
**numeric** `pipewire_links_inspected` (0–8192) and
`eq_usb_direct_links` (0–3) alongside existing anonymous audio
metrics. A separate local read-only command
`python3 -m audiohub.hardware_preflight` returns a detailed
**non-identifying** JSON topology report, including yes/no direct
link evidence per slot. Run locally as the `audiohub` Linux user on
an isolated test Pi; it does not touch Bluetooth trust or networking.

## How to read a real Pi report

| Observed status | Strict interpretation |
| --- | --- |
| `usb_audio_detected=true` | A recognized USB output was advertised, **not** proof sound is audible |
| `usb_audio_route_ready=true` | `wpctl set-default` to recognized USB succeeded, **not** proof ports linked |
| `pipewire_links_inspected>0` | At least one valid PipeWire Link was observed, not proof of the intended sink |
| `eq_usb_direct_links=1..3` | One or more EQ output nodes have *observed direct* links to selected USB sink |
| `eq_usb_direct_links=0` | No directly matching link observed. Can be due to PipeWire intermediate adapters, inactive links, missing routes or boot timing. **Do not automatically diagnose silent output.** |
| All three direct links seen | Still only a topology prerequisite; no proof of three independent audible sources or clipping safety |
| Report absent | No readable diagnostic evidence; not necessarily failure to boot |

PipeWire may insert internal adapter/loopback nodes. This first
iteration checks **direct** EQ-output-to-USB links only and purposely
does not infer connections from mere presence, free-text link metadata,
or a Bluetooth source being paired. Future work should inspect actual
port-level and intermediate-node paths after collecting a redacted
`pw-dump` graph from a *real* Pi4 test, validating against deployed
WirePlumber versions. Do **not** upload unredacted `pw-dump`, log
MACs or serials, audio samples or Wi-Fi secrets into public issues.

## Hardware acceptance still required

1. Operator verifies experimental image SHA256/XZ and flashes a spare
   microSD. Pi4 + Edifier R600USB physically connected; no trusted LAN
   or Wi-Fi credentials before authenticated owner setup exists.
2. Play low-volume Bluetooth audio, listen to real USB speaker,
   verify mute/individual EQ and route stability. Power cycle and
   USB unplug/replug. For a possible dual-A2DP setup, separately
   determine controller support.
3. After 10 minutes, remove SD after power-off and read
   `AUDIOHUB-TEST-REPORT.json`. Record privacy-safe metrics and
   operator auditory yes/no separately in [Issue #2](https://github.com/RIVANOXcom/rivanox-audiohub/issues/2).
4. No actual Pi4+Edifier acoustic test, full 3-source Windows input
   or 24h endurance test has yet been passed. The Scream UDP source
   is unauthenticated and remains disabled until manually started
   only on an isolated test LAN.
5. Owner claim, authenticated phone management, Pi provisioning,
   rootfs licensing and official public GitHub Releases remain gates.

## Security and CI contract

- Read-only PipeWire `pw-dump` via argv-only subprocess and 5-second
  timeout, no shell, network commands, source enrollment or mutations.
- Invalid node IDs and duplicate EQ output names fail closed.
  Malformed links and duplicate output→input pairs never count as
  positive evidence. Graph input bounded to 8192 objects.
- Hardware readiness and release readiness are **always FALSE** in
  this module; only human-verified real playback can advance gates.
- ARM64 rootfs export requires the graph inspection source plus
  runtime integration and the anonymized FAT report; negative tests
  ensure these cannot be accidentally removed before publishing a
  temporary alpha ZIP.

**Canonical continuation:** [PROJECT-HANDOFF.md](PROJECT-HANDOFF.md),
[ENGINEERING-BACKLOG.md](ENGINEERING-BACKLOG.md), [#27 input routing](https://github.com/RIVANOXcom/rivanox-audiohub/issues/27),
[#28 main protection](https://github.com/RIVANOXcom/rivanox-audiohub/issues/28).

No GitHub ruleset, permissions, release, main merge, SD installation or
device deployment is performed by this development change.
