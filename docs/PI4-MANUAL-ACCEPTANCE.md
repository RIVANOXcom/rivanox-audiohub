# Pi 4 + Edifier R600USB acceptance protocol (AH-009)

**Status: NOT TESTED / NOT ACCEPTED.** This is a procedure and record template;
it is not a hardware test result or a release approval.

## Safe preflight — diagnostic only

An authorized technician may use the already available Raspberry Pi 4, Edifier
R600USB and an isolated experimental SD card; preserve an intact recovery card
first. Do not flash an unverified preview image to a production system. When
the source checkout and per-user PipeWire runtime have been independently set
up, the *read-only* command is:

```bash
PYTHONPATH=src python3 -m audiohub.hardware_preflight
```

The utility makes one bounded `pw-dump` query (5-second timeout). It checks for
a **unique Edifier USB sink** and exactly one virtual sink for each
`audiohub.music`, `audiohub.laptop` and `audiohub.tablet`. It returns only
boolean topology checks and the aggregate number of advertised Bluetooth
source nodes. It never changes audio, network or pairing state and never saves
a file. It does not disclose Bluetooth MAC addresses, device names, serial
numbers, source IP addresses or audio contents.

Exit code **0** means the *topology prerequisite* was detected; code **2**
means the prerequisite is missing or inspection failed. Both outputs
explicitly contain `"release_ready": false`; neither proves physical
playback or justifies merging or flashing a production image. No Pi-connected
result has been collected in this task.

## Manual test record (separate human-attested evidence)

Before every test, note the exact source commit, image SHA256, source image
provenance, OS and kernel versions, Pi 4 revision, anonymized USB device model,
PipeWire/BlueZ/WirePlumber versions, and tester/date. Do **not** publish a
Wi-Fi password, sender IP, key, Bluetooth address, customer audio recording or
unredacted diagnostic log. Raw acoustic measurements belong in access-controlled
evidence storage with owner consent and appropriate retention.

All observations start as **not tested**. The technician must record
pass/fail, test setup, redacted artifacts and measured outcomes; a test with
no evidence stays open.

| Case | Setup / action | What must be demonstrated |
| --- | --- | --- |
| P01 | Cold-boot separate test SD with USB Edifier and Pi power only | AudioHub first boot without keyboard/SSH/monitor; owner onboarding verified separately |
| P02 | Run the read-only topology preflight | One actual Edifier USB PipeWire sink and one sink per logical channel; snapshot is not an audio success |
| P03 | Pair approved Android phone, run audio, restart the Pi | Audible sound on Edifier; pairing/reconnect do not open unauthorized pairing |
| P04 | In an *isolated lab only*, manually configure the approved Windows Scream driver for unicast 48 kHz/16-bit/stereo, then run the guarded prototype | Audible `audiohub.laptop`; observe packet drops and latency; stop after test. The UDP sender is not authenticated |
| P05 | Introduce the tablet via a separately confirmed independent input path | Audible tablet input without stealing phone/laptop routing; **do not presume two parallel A2DP senders work** |
| P06 | Play phone, laptop and tablet simultaneously | Independently identify three sounds, solo/mute and change volume/EQ without disrupting other channels |
| P07 | Capture only consented loopback/audio test signals, perform full-scale sum | Check clipping/peak behavior before, during and after EQ boosts; source-only gain budget is not a proven limiter |
| P08 | Unplug/replug Edifier during playback and interrupt laptop LAN | Recovery without routing to an unrelated output or replaying stale audio; log restart and drop counters |
| P09 | Close browser, interrupt Internet, power-cycle unexpectedly | Bluetooth playback remains independent of UI/Internet, with safe recovery after restart |
| P10 | Operate continuously for 24 hours | Record underruns, audio stop events, memory/CPU, power consumption and recovery; no 24h pass assumed |
| P11 | Exercise owner-claim and unwanted-sender attacks | Owner revocation, LAN spoof resistance and authenticated sender admission proven; **legacy Scream IP filtering does not pass** |
| P12 | Verify source provenance, third-party licenses, accessibility and installer | All mandatory release gates G1–G10 independently evidenced with owner approval |

### Evidence expectations

For P06, make an independent channel matrix recording *which source maps to
which virtual sink*, test mute/volume/EQ for all three, and note whether a
channel remained audible while the others changed. For P07, state peak
measurement method, full-scale source signals, quantifiable peak levels, and
whether output clipped; do not infer measured audio quality from `wpctl`
volume requests. For P08/P10, include event timestamps and before/after
state, with personal identifiers redacted. Test duration, packet counts,
clock drift and latency **must be observed**, not estimated from the
16-packet buffer capacity.

## Release hold

Physical observation is required for P01–P12 and mandatory G1–G10 gates.
Hardware topology `ready_for_manual_test` is not a gate approval. The
software does **not** produce an installable image, touch a live Pi, accept
owner credentials, or authorize a release. Merge, deployment and public
distribution require independent review and explicit owner decision.
