# Audio path integration – Pi4 experimental acceptance (AH-002 / AH-007)

**State:** development-only implementation. Not a validated Bluetooth receiver,
not a 3-source mixer acceptance, not proof of audible Edifier R600USB sound.

## The connected signal path

```text
Android / phone A2DP (Bluetooth, BlueZ / PipeWire bluez_input.*)
                   |
   WirePlumber: media-source-role=input (NOT auto-playback to HDMI/USB)
                   |
    AudioHub supervisor: validate BlueZ node, device ID, paired mapping
                   |
  pw-loopback --capture bluez_input.* --playback audiohub.music
                   |
  PipeWire parametric EQ virtual sink audiohub.music
                   |
  selected default USB output (Edifier or sole generic USB speaker)
                   |
                    USB R600USB
```

A second distinguishable Bluetooth source can be assigned to
`audiohub.tablet` and has a separate EQ/volume/mute. This is **only a
software-routing design**, not a claim that Pi4 Bluetooth reliably
supports two simultaneous A2DP senders. The third channel
`audiohub.laptop` remains reserved for a separately reviewed Windows
LAN audio receiver from the **unmerged** AH-002 PR #11/#12/#19 chain.
The alpha image does not automatically enable unauthenticated Scream.

## Engineering changes

- Explicit WirePlumber BlueZ `bluez5.media-source-role=input` on
  `bluez_input.*` nodes. WirePlumber's documented default `playback`
  can auto-route a paired phone around per-source EQ; that would make
  AudioHub's separate controls meaningless.
- Supervisor now chooses only a PipeWire USB audio output; HDMI is
  never a fallback. It reasserts that USB as the default every poll,
  **and refuses to create new Bluetooth routes until `wpctl
  set-default` succeeds**. On USB unplug/failure it closes all managed
  capture loopbacks; on re-plug the next poll may reopen them.
  This reduces, but does not cryptographically prove, correct physical
  PipeWire graph linkage. The exact Edifier-to-EQ link still requires
  inspection on the Pi.
- All Bluetooth source names and addresses must match bounded,
  structured PipeWire data. Invalid PipeWire dumps, arbitrary node
  metadata, duplicate MACs and ambiguous output hardware fail closed.
  A single generic USB sink is allowed (some USB audio equipment
  reports "USB Audio Device" instead of a consumer brand).
- Two independent managed capture routes maximum. A disconnected
  source does not silently overwrite a previously assigned mapping.
- Dead PipeWire loopback processes back off at 5/10/20/40/60 seconds.
  This avoids repeated five-second crash restarts exhausting a Pi4.
  Healthy processes are retained. A changed source or sink resets the
  route identity, and actual disconnects terminate the managed stream.
- A purely local runtime-status summary now has
  `usb_route_ready`, `route_start_failures` and
  `output_switch_failures`, with bounded counters. The SD boot
  `AUDIOHUB-TEST-REPORT.json` includes those fields **without**
  addresses, serial numbers, SSIDs, names or private credentials.

## Existing known limitations

1. The per-source EQ graph is defined at image installation. Changing
   EQ values from an unauthenticated web interface is **not implemented**
   and must not be enabled before secure owner control exists.
2. No inter-sample true-peak limiter or measured master-mix clipping
   safeguard is implemented. Keep physical test volume low; validate
   simultaneous full-level playback before approving sound quality.
3. No supported authenticated Windows/laptop sender is enabled in this
   branch, and Pi hardware cannot be assumed to support dual Bluetooth.
4. This code cannot prove USB audio is actually audible, whether
   WirePlumber applied the new BlueZ rule on real Pi OS, or whether
   `pw-loopback` connected the expected PipeWire ports. Hardware
   `pw-dump` and link observations are required. No PipeWire
   graph/link capture on device has yet been made.
5. Secure physical ownership, phone-only WLAN setup, signed updates,
   permission/credential handling and release licensing remain gates.
6. A real ARM64 CI image build is **packaging verification only**; it
   does not execute a live Bluetooth session or R600USB playback.

## First isolated Pi test (once a new artifact is verified)

Use a **spare** microSD; do not connect a trusted LAN or enter Wi-Fi
passwords. Flash only the explicitly identified latest image from
Actions. Pi4 + Edifier USB + stable 5V power. Turn phone Bluetooth on,
search for `AudioHub` during the initial pairing period, play quiet
test music. Check actual Edifier output. After roughly ten minutes
power off safely; open `AUDIOHUB-TEST-REPORT.json` on the SD boot
partition from a PC and share its non-identifying JSON contents.

Interpretation:
- `usb_audio_detected=true`, `usb_audio_route_ready=false`: a
  PipeWire USB sink was found but `wpctl set-default` was not confirmed.
- `usb_audio_route_ready=true` and `active_audio_routes=0`:
  either no eligible Bluetooth source/EQ sink, or the capture process
  was unavailable/failed; consult the bounded failure counters.
- `active_audio_routes=1` **does not prove audible sound**; listen to
  the speaker and record what you observe. Keep redaction boundaries.
- Missing report does **not** prove the OS failed to boot. The FAT
  partition or diagnostic service may be unavailable.

Do **not** classify alpha tests as accepted until actual device
video/technician observation and verified sound are attached to
GitHub hardware Issue #2.

Documentation basis: PipeWire pw-loopback(1), PipeWire filter-chain
virtual sink design and WirePlumber 0.5 bluetooth media-source-role
documentation; verify against Pi image package versions before
production. No modifications to closed/in-progress external branches.

PAPA `PJ2611-0001:R001`; AH-002 #3268, AH-007 #3273,
AH-009 #3275; G2/G3/G4/G5/G6/G7/G8/G10 remain pending.
