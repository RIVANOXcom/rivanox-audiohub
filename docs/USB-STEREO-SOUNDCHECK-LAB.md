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

## Optional EQ-input isolation test (still manual)

After an authorized operator has checked the **direct USB** left/right
signal, they can ask whether the same quiet pattern passes through exactly
one of the three virtual AudioHub EQ inputs. This adds no pairing or UDP
receiver requirement and does not change any PipeWire setting.

Choose exactly **one** internal slot per invocation (these technical names
are not fixed consumer device categories):

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.usb_soundcheck --confirm-isolated-usb-test --through-input music
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.usb_soundcheck --confirm-isolated-usb-test --through-input laptop
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.usb_soundcheck --confirm-isolated-usb-test --through-input tablet
```

Each command requires its own explicit operator action. The code checks
the live bounded PipeWire graph, insists on the selected `audiohub.<slot>`
virtual sink and its unique filter playback node, and **requires an
observed direct Link from that filter output to the same USB speaker**.
If a direct link cannot be observed, or a second destination such as
HDMI appears, it **refuses to send PCM**. Actual PipeWire installations
may use intermediate adapter nodes instead of such a direct link, so a
rejection is **inconclusive**, not proof that the real output is broken.
No privileged `wpctl` changes or default-sink fallback are attempted.

The tests are **one input at a time**; they do NOT demonstrate
simultaneous three-way mixing, correct EQ response, safe clipping,
Bluetooth capture or human-audible sound. Record actual L/R observations
and any rejected step separately; never treat the process exit status as
an automatic hardware acceptance or release permission.

## Three simultaneous virtual input probe (separate, experimental mode)

A newly available **explicit** local console option can open three
`pw-cat` playback streams to the three separate AudioHub EQ sinks at once,
with one original, low-amplitude marker tone per input. This is an **operator
tool for an isolated and already authorized test bench**, not normal audio
playback, a Bluetooth emulation, secure network input, or evidence of actual
three-source audio mixing.

After the same operator approval, low physical speaker-volume precondition,
unprivileged `audiohub` account and local Pi4 USB-only bench isolation
described above:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.usb_soundcheck --confirm-isolated-usb-test --three-input-mix-probe
```

The two flags are deliberate: the CLI refuses to play if confirmation is
omitted and does not run this mode at boot, through HTTP or through any
other user action. `--three-input-mix-probe` is mutually exclusive with
`--through-input`.

The program takes **one bounded read-only PipeWire graph snapshot**, then
checks all three virtual sinks and their unique EQ-output nodes, verifies
explicit direct links to the same unambiguous USB speaker, and refuses
the entire experiment if **any** direct EQ-output link targets another
device (including HDMI). Some legitimate PipeWire graphs use intermediate
adapter nodes, so inability to prove these direct edges produces an
**inconclusive refusal**, not an audio defect diagnosis.

Only after all checks pass are three ordinary, non-privileged `pw-cat`
processes created. Three threads feed them simultaneously, with original
stereo sine wave markers at 440/554/659 Hz for approximately two seconds.
Each stream is amplitude-limited to 2/3 percent of full-scale; even the
worst-case three-way in-phase signal sum remains at most 2 percent of S16
full-scale **before** unknown device amplification and EQ processing. A
10 ms fade at both ends avoids a hard waveform click. The program
uses no music, input files, microphone, Bluetooth pairing, network,
volume settings or PipeWire route creation. All playback subprocesses
are terminated/reaped on success and failure. An unsuccessful player
returns a generic failure, never a claim about speaker sound.

**Interpretation is limited.** A process-level pass confirms only three
short player invocations completed after a snapshot of expected routing
topology. It does **not** prove synchronized audible playback,
real-world three-source mixing, Bluetooth A2DP capture, correct EQ curves,
stable volumes, clipping protection, USB recoverability, safety at the
speakers, or a hardware/release GO. An authorized human should separately
report what was audible on the physical bench, whether each marker was
heard concurrently and whether the system clipped or dropped audio,
without recording private identifiers.

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
