# AudioHub ALPHA — offline Pi4 + Edifier manual hardware observation

**Status: developer testing only; not a public release, ownership proof, safety certification, or commercial license approval.** The current public code remains AGPL-3.0-only. The human observations below cannot override the release/Model C gates.

## Prerequisites

Use an isolated Raspberry Pi 4 developer bench, real Edifier R600USB USB speakers and the **UNVERIFIED** experimental image from GitHub Actions if independently assessed safe for your lab. Start at low volume. Ensure PipeWire, WirePlumber and the AudioHub user services run, and physically connect the speakers. Existing topology-only checks are NOT proof that sound is actually audible.

Do not expose the read-only alpha web UI or the unauthenticated experimental laptop PCM receiver to the Internet. Do not test unknown Bluetooth devices on a production network.

## Run from the Pi's local owner-controlled terminal

First inspect the read-only, redacted PipeWire topology:

```bash
sudo -u audiohub env XDG_RUNTIME_DIR="/run/user/$(id -u audiohub)" PYTHONPATH=/opt/audiohub/src /usr/bin/python3 -m audiohub.hardware_preflight
```

Only when topology prerequisites are detected, run the interactive observation checklist:

```bash
sudo -u audiohub env XDG_RUNTIME_DIR="/run/user/$(id -u audiohub)" PYTHONPATH=/opt/audiohub/src /usr/bin/python3 -m audiohub.manual_acceptance
```

This tool **never starts playback**, changes volume, pairs a Bluetooth device, opens a network socket or writes a report. The person at the bench must independently operate each applicable audio source and confirm what they physically heard. Answers: `yes`, `no`, or `skip`. Invalid strings are discarded, not stored. The tool prints fixed, privacy-bounded JSON to the local console. If topology is incomplete, it asks no audio questions and exits with code 2.

## Isolate one input safely during an already authorized bench session

A newly added **owner-local, unprivileged** mixer feature reduces the
multiple-command risk of checking individual channel isolation. On a
separately authorized *isolated* Pi4 bench, first inspect the private
anonymized source/mixer overview and confirm the current source slot:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --format text board
```

To test **Input 1** (technical slot `music`) without disturbing its
volume, EQ or existing mute state, request a **read-only** plan:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview isolate-input music
```

The JSON `before` / `after` and `would_change` fields show exactly
which of the **other two input mutes** would be turned on. Nothing is
changed by the preview; inspect it and copy the private `v1-...`
revision only after reviewing it. If an owner/operator separately
chooses to perform the planned change at that same local console,
they must explicitly enter **both** the approval flag and exact
preview revision:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-64-LOWERCASE-HEX isolate-input music
```

Without prior preview revision or explicit local confirmation the
operation refuses to write. A concurrent mixer edit, even a change
that restores the same values (ABA), makes the previous revision
invalid. One existing exclusive 0600 settings-file writer applies
the two **other** mutes in a single atomic replacement, avoiding
an intermediate mixed configuration. Master level, volume, EQ and
all source-routing settings remain unchanged.

**Crucially, isolation is NOT auto-unmute or solo.** If the selected
input was already muted, it **stays muted**. No sound is played,
gained, paired, connected, tested or claimed by the command.
An already-unmuted selected input may remain audible, so always
check physical speaker volume, source state and the proposed
`before/after` settings before confirming. No automatic
restoration occurs afterward: manually inspect any later unmute
or volume adjustments as separate actions. The running PipeWire
supervisor applies the requested mutes on a later poll, and a
successful file update cannot prove the effect or audible audio.

### Manually restore only the two originally changed mutes

The original read-only `--preview isolate-input music` response also
contains a bounded `comparison_baseline` starting with `b1-`.
**Keep this original baseline locally** if you wish to restore the two
other input mutes after a separately authorized isolation test. It
contains requested volume, EQ and mute settings; never paste it into
public logs, screenshots, telemetry or support messages. A baseline
is operator-supplied, **not an authenticated backup**.

After the controlled test, the operator can inspect a restore plan,
substituting the actual captured `b1-...` token:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview restore-isolation music b1-REPLACE-WITH-ORIGINAL-CAPTURED-BASELINE
```

The command **refuses** to propose restoring the previous mutes unless
the entire current mixer settings state (master, all three inputs'
volume/mute/EQ) still exactly matches the result expected after the
original isolation. Any independent change to any mixer control, even
if later reverted to the same values, invalidates the previous
revision. The new read-only plan lists precisely which two other
mutes would revert and shows a **fresh** `v1-...` revision. Review
`before`, `after`, `would_change` and the exact selected slot;
never infer real audio from the preview.

Only after **separate local consent** may the operator enter:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-FRESH-RESTORE-PREVIEW-REVISION restore-isolation music b1-REPLACE-WITH-ORIGINAL-CAPTURED-BASELINE
```

The existing private lock and revision-guarded atomic writer restore
**only the prior mute state of the two other inputs**, never the
selected input's mute, master volume, gain, EQ, Bluetooth connections
or source routing. Previously muted sources stay muted. If
the restore preview reports a mismatch, a fresh status inspection is
necessary; do not force a restore or automatically unmute channels.
The feature neither stores a rollback file nor schedules an automatic
write, and an accepted software command is still not evidence of
Edifier output.

The command does not attach to the web UI, enable the unsafe
Windows UDP receiver, modify BlueZ trust, open a port, or grant
release approval. Repeat tests individually only with separate
owner authorization, and retain the existing offline hardware
observation gates and independent 24-hour test.

## What the operator actually checks

1. Real Edifier speaker playback is **audible** at safe volume.
2. Bluetooth sources and the manually authorized laptop input can operate together on separate channels **only in a controlled lab**.
3. Per-channel mute and equalizer changes affect **only their intended input**.
4. Removing the USB audio device promptly disables routes, without HDMI or other unsafe fallback.
5. The mixed sound does not exhibit obvious clipping during the chosen low-volume test.
6. The separate **24-hour endurance test** has truly been performed. Answer `skip` if not yet completed.

A `yes` is an **operator's observation**, not measurement, calibrated audio testing, independent certification, cryptographic ownership, a right to distribute third-party software, or a completed legal review. The JSON **always** contains `hardware_accepted=false`, `ownership_authenticated=false`, `release_ready=false`, `legal_redistribution_approved=false`, and `model_c_license_effective=false` even when every human answer is affirmative. Exit code 0 only means the checklist produced a report.

For support/debugging, share only the redacted JSON after personally reviewing it. Do not send passwords, MAC addresses, unique serial numbers, screenshots with account details, raw `pw-dump` or private system logs.

## Blocking decisions after a manual session

Do not ship an SD card or flip license/rights flags. Hardware acceptance needs independently reviewed device results and secure owner claiming. Commercial release also requires the RIVANOX rightsholder's legal review and the nine remaining Raspberry Pi OS notice-path checks, including `raspberrypi-net-mods`. Owner-created PRIVATE future Model C repository is tracked in issue #37; source rights issue #32, OS rights #40 and actual Pi4/Edifier acceptance #2 remain open.

**Related:** [PAPA canonical recovery](PAPA_CANONICAL_RESUME_20261105.md), [Draft PR #48](https://github.com/RIVANOXcom/rivanox-audiohub/pull/48).
