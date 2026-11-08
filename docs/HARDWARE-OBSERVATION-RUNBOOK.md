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

## Three-band per-source EQ tuning for a separately authorized Pi bench

The 3-band PipeWire equalizer previously had a defined configuration
model and a demonstration UI, but no ordinary guarded operator-local
way to choose individual band gains and generate matching PipeWire
filter configuration. This unmerged alpha implementation now
supports explicit **offline staging** for the next independently
authorized PipeWire configuration reload. No automatic restart,
Bluetooth reconnection, source routing or sound action occurs.

After checking the current mixer, an authorized unprivileged Pi
operator may preview one **bounded integer** band adjustment
(`bass`, `mid`, `treble` at `-12..12` dB) on one fixed internal
input (`music`, `laptop`, `tablet`). For example:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview set-eq music bass -3
```

The preview lists `eq_changes`, keeps requested gain/mute and routing
untouched, and explicitly says `eq_live_applied=false`. An operator
can independently save only the reviewed band setting with the
exact fresh mixer revision; missing consent or stale/ABA generations
are refused:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-REVIEWED-REVISION set-eq music bass -3
```

**Saving EQ is not yet hearing it.** The running PipeWire filter
chain is never reconfigured by this command. Next, separately
preview the actual sanitized three-source filter setup derived from
the newly stored private mixer state:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.eq_setup --preview-saved
```

This returns the exact mixer revision, fixed three-band settings and
SHA256 of the prospective PipeWire config. It creates no file.
Only after reviewing it can the operator **separately** stage the
configuration under the existing private EQ pathname, using the
same revision. Staging is under the existing exclusive mixer writer
lock and rejects intervening settings updates:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.eq_setup --stage-saved --confirm-local-eq-stage --if-preview-revision v1-REPLACE-WITH-EQ-PREVIEW-REVISION
```

The stage uses the existing atomic `0600` EQ file replacement and
symlink/hardlink/private-directory protections. The default image
builder invocation of `audiohub.eq_setup` without flags still
generates the original neutral EQ; new settings are never selected
implicitly. The stage output explicitly marks
`configuration_staged=true` but `pipewire_restarted=false`,
`live_eq_applied=false`, and `hardware_audio_verified=false`.
Only a **separately operator-controlled, explicitly approved**
PipeWire restart/reload on an isolated lab could use the new filters,
and this may interrupt audio. Do not perform such a restart on
production equipment or interpret staging as measured equalization.
Physical playback, clipping, multi-source isolation and USB recovery
must still be independently observed. Even attenuating an EQ band
is not a guarantee of safe output gain or no clipping.

### Check whether saved EQ and staged PipeWire EQ still agree

After changing any saved EQ band, operators need to know if their **existing**
private PipeWire stage file still matches the current requested EQ. Without
changing, staging or restarting anything, run:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.eq_setup --compare-staged
```

This owner-local **read-only** command compares the SHA256 of the exact
configuration generated from one stable private mixer snapshot to the
SHA256 of the existing private stage file. It reports one of four
`staging_status` values:

- `matches_saved`: the safe stage file bytes exactly match currently
  saved EQ. **Not evidence that PipeWire has loaded it**.
- `differs_from_saved`: the safe stage file is present, but saved EQ and
  its bytes differ (e.g., a newly tuned curve awaits staging).
- `missing`: no stage directory/file was present; this command creates
  neither.
- `unavailable`: the stage path/file is unsafe, oversized, racing or
  cannot be safely inspected. It is **never** treated as a match.

The output shows only fixed technical slots, bounded saved EQ values,
the two digests where safe, and the private mixer generation; no device
identifiers or untrusted file text is displayed. The staged file must be
private, owned by the current non-root user, regular, singly linked and
within the configuration size limit. Symlinked directories/files, public
or hardlinked targets are refused, and a mixer generation changing during
the comparison invalidates the report. No files, permissions, settings,
running filters or audio devices are modified. Even `matches_saved`
explicitly reports `live_eq_applied=false`,
`pipewire_restarted=false` and `hardware_audio_verified=false`.

If staging is different or missing, review `--preview-saved` first.
Stage only with the separate deliberate revision-guarded
`--stage-saved --confirm-local-eq-stage` command from the section above.
Any actual PipeWire reload remains a separate operator-authorized lab
step and cannot be inferred from this read-only comparison.

### Tune all three bands of one input in one reviewed change

The older `set-eq SLOT BAND DB` command edits one band at a time. To
set a complete bass/mid/treble curve for one input without three
separately saved intermediate configurations, use the new owner-local
`set-eq-curve` command. Example: technical input `music`, bass -3 dB,
mid +2 dB and treble +1 dB:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview set-eq-curve music -3 2 1
```

This reads the current **private** settings without writing; `eq_changes`
shows each actual band difference, `before`/`after` show unchanged
requested volumes and mute bits, and `revision` is a private exact-generation
token. Values must be integers between -12 and +12 dB. The slot is one
of `music`, `laptop` or `tablet`, **not** a device identifier.
After an independent review of the exact preview, separately approve:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-REVIEWED-REVISION set-eq-curve music -3 2 1
```

The existing exclusive-locked, private 0600 atomic mixer writer rejects
stale or ABA revisions and saves all three settings in one generation.
No master/input volume, mute, third-source EQ, source route or Bluetooth
trust is changed. A source change between preview and confirmation is
**never** silently accepted: review a new preview. Saved EQ remains
**not staged and not live**; use the separate `audiohub.eq_setup`
preview/approval process described earlier before an independently authorized
PipeWire reload in an isolated lab. A requested EQ boost can clip;
keep levels conservative and do not interpret the save as measured sound.

### Copy and neutralize a tuned three-band EQ without three manual edits

Once the owner has saved one input's bass/mid/treble on the private Pi
console, the previous per-band editor required three separately reviewed
changes to give another input the **same requested EQ curve**. This
experimental operator shortcut copies all three values in **one**
revision-guarded mixer settings replacement:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview copy-eq music tablet
```

The read-only `eq_changes` array identifies the exact target bands,
before/after values, unchanged requested gains/mutes, and a private
`v1-...` mixer revision. The source and destination must be
**different** existing fixed input slots; no device or Bluetooth
address is accepted. Only after independent local review may the
operator enter the **fresh** revision and consent:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-REVIEWED-REVISION copy-eq music tablet
```

The selected source's three EQ bands are copied to the destination in
one existing exclusive-locked private 0600 settings update. The source
EQ stays intact; the target's volume/mute, other inputs, master level,
physical routing and Bluetooth trust are unchanged. Concurrent or
even ABA mixer changes invalidate the earlier revision, and all three
copied values must come from the same source generation.

To return just one input's saved EQ to a neutral 0 dB baseline without
raising/lowering volume or changing mute, use the same explicit
two-step review:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview reset-eq music
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-REVIEWED-REVISION reset-eq music
```

These operations change only the **requested, saved EQ**. Neither
command applies the EQ dynamically to the running PipeWire filter.
The operator must separately inspect `audiohub.eq_setup --preview-saved`
and, only with separate approval, stage the exact saved configuration
as documented above. No PipeWire restart, audible sound, device
connection, test evidence or release approval is implied by copying
or neutralizing a curve.

### Exchange two saved EQ curves without six separate edits

On an isolated owner-controlled Pi console, two already-tuned inputs can
exchange their saved bass/mid/treble requests **in one atomic settings
generation**. This is safer than first copying one curve over the other,
which would otherwise lose the original values, or manually editing
six individual bands. For instance, after moving physical sources into
different fixed technical mixer slots, swap just the two saved curves:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview swap-eq music tablet
```

Review the local JSON `swap_inputs`, every bounded `eq_changes` before/after
band, unchanged master/input levels and mute states, and the fresh private
`revision`. A read-only preview never creates or alters a settings file.
Only if the owner explicitly approves the **same** proposed change:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-REVIEWED-REVISION swap-eq music tablet
```

Both sources' EQ values come from the **same** protected snapshot, and the
exclusive locked private 0600 writer refuses any stale generation, including
an ABA change back to identical values. An invalid or identical slot, missing
consent or inconsistent preview does not write settings; a stale attempt
returns only a newly captured **read-only** proposed swap for review.
The other input, all master and per-source volumes/mutes, Bluetooth/LAN
route assignments and device trust remain untouched. If both curves are
equal, the preview may report no EQ changes.

**Important:** A successful save is not staged or live audio EQ. As with
`copy-eq` and `reset-eq`, separately review
`audiohub.eq_setup --preview-saved` and explicitly authorize
`--stage-saved` before any operator-controlled PipeWire reload on an
isolated bench. This command does not restart audio, pair a device,
authenticate a phone or certify audible output.

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
