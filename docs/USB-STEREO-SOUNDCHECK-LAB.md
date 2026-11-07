# AudioHub – local USB stereo soundcheck (experimental)

**UNVERIFIED ALPHA. NOT a product release, hardware certification, or
permission to flash an image or perform a hardware experiment.**

This opt-in console command helps an *already authorized* isolated
Raspberry Pi 4 + USB speaker bench distinguish a basic USB output problem
from Bluetooth pairing, source routing, EQ and mixing problems. It does
**not** exercise or validate Bluetooth capture, dual A2DP, the three
AudioHub virtual channels, volume controls, secure owner onboarding or
actual audible playback.

## Preconditions

1. Obtain operator approval **separately** before any destructive SD flash,
   real equipment operation, or image installation. Use only an already
   authorized and physically isolated lab Pi4 with a non-production SD card.
2. Do **not** connect the experimental alpha to a household/workplace LAN,
   real credentials, or production networks. The command does not require
   Wi-Fi or Bluetooth and never opens a listening socket.
3. Attach the permitted USB Edifier R600USB or an unambiguous USB audio sink.
   Turn **physical speaker volume low**, starting muted if unsure; have an
   operator present. The generated PCM has ~2% peak (about -34 dBFS),
   but this does not guarantee safe sound pressure or a muted USB device.
4. Run as the **unprivileged `audiohub` Linux account** at a local console
   with its existing PipeWire user session. The command **does not** run
   automatically as part of startup, systemd, the status webserver or CI.

Only after the above conditions are met and the operator **explicitly
decides to run this test**:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.usb_soundcheck --confirm-isolated-usb-test
```

When logged into a different account, the operator must deliberately enter
a supported local user session as `audiohub` first. Do not execute as root,
expose this command via HTTP, add it to first boot or install a privileged
service for it.

## Exactly what it does

- Executes one bounded, local `pw-dump` inspection and accepts only a
  single unambiguous real USB audio sink. HDMI is never substituted.
- Uses the explicitly identified USB sink's validated PipeWire node name
  as `pw-cat --target=...`; no default-sink fallback, shell expansion,
  setting changes, pairing or network request.
- Generates a short low-amplitude stereo S16LE 48 kHz waveform in memory:
  **180 ms left**, **80 ms silence**, **180 ms right**. No music, stored
  audio, microphone, credentials or received device data.
- Limits the test player to 5 seconds. A missing tool, invalid graph,
  failed player or timeout yields a generic error; command stdout/stderr
  from PipeWire are not logged.
- Does **not** save a local report, attest speakers, change a route,
  configure the mixer, confirm volume, or mark `hardware_verified`.

A completed command only confirms that the local process returned success;
it does **not** prove that the operator heard both channels. On an authorized
bench, separately record **heard left / heard right / not heard / unknown**
without private device identifiers and continue the normal isolated
Bluetooth, USB recovery and three-source acceptance procedure. A result is
not an operator release/installation decision.

This optional CLI is source-only until an exact-head native alpha package
and real bench observations are separately documented. It cannot remove
the nine outstanding rootfs copyright findings or production security gate.
