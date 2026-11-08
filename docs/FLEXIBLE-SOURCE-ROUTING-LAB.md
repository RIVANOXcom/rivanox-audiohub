# Flexible source-to-input routing – offline alpha lab (Issue #27)

**State: implemented in a dedicated DRAFT branch; no hardware proof, no
phone UI, not a product-ready authorization system.** This work builds on
the earlier neutral Input 1–3 display labels. The stable PipeWire sink
IDs `audiohub.music`, `audiohub.laptop`, `audiohub.tablet` are merely
internal implementation names, **not fixed product categories**.

## What is now configurable

Two **eligible** BlueZ A2DP sources can be routed to any two of the
three EQ sinks. The remaining sink is **reserved** for the manual
isolated-LAN PCM receiver; changing that reservation does **not**
start a network service. Names (e.g. TV, Console, Office PC) are
independent of source transport and are managed by a separate
browser-only preview and local private console prototype.

The default source policy retains the previous test-image behavior:

| Stable sink | Default reserved input | Human-readable name |
| --- | --- | --- |
| `audiohub.music` | Bluetooth source 1 | Input 1 (rename freely) |
| `audiohub.laptop` | Manual LAN lab input, **off by default** | Input 2 |
| `audiohub.tablet` | Bluetooth source 2, if supported on Pi4 | Input 3 |

The operator can exchange the roles. Example: manual LAN to Input 1
(`music`), first BT to Input 2 (`laptop`), second BT to Input 3
(`tablet`).

## Local master volume and per-input mute (new alpha console control)

The existing supervisor already polls its user-private `settings.json` and
applies per-source `wpctl set-volume` and `set-mute` after conservatively
attenuating the selected USB master output. Previously there was no supported
operator-facing way to update these settings without editing JSON by hand.

An authorized operator at the **local console of an already-approved isolated
Pi4 test bench**, logged in as the **unprivileged `audiohub` user**, can now
inspect and explicitly adjust the running mixer settings. No HTTP endpoint,
network service, Bluetooth permission, EQ file rewrite or system configuration
change is introduced:

```sh
# Read only; does not create or change a file:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control show

# Read-only: requested levels vs recent, complete supervisor command acknowledgement:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control status

# Preview WITHOUT storing a change, creating a lock or applying any audio:
# JSON includes "revision" (guarded save) and "comparison_baseline" (value snapshot).
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview mute-all
# Compare a later preview to the ORIGINAL saved "comparison_baseline" b1-...;
# replace the placeholder with that exact token from the earlier JSON:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview --compare-baseline b1-REPLACE-WITH-ORIGINAL-BASELINE set-mix 20 35 25 0
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview unmute-selected music laptop
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview set-mix 20 35 25 0

# After inspecting the JSON preview, COPY its exact revision into the next
# explicitly confirmed command. If any settings changed meanwhile, this
# request FAILS CLOSED (no mixer settings are rewritten):
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-64-HEX-CHARS set-master 20

# Each mutation needs an explicit flag and a separate console invocation:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change set-master 20
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change set-volume music 35
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change mute tablet on
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change mute tablet off

# Request all three input mutes together, preserving previous levels and EQ:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change mute-all

# Restore only the specifically selected 1 or 2 inputs in ONE atomic step;
# the third input stays muted, with all previous levels and EQ untouched:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change unmute-selected music laptop

# One atomic update to master, then music, laptop and tablet levels:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change set-mix 20 35 25 0

# Compare one saved profile against the CURRENT requested (not audible) mixer levels:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control compare-profile-current cinema
# JSON: saved_volumes, current_volumes, changed fields with signed delta
# (current minus saved), profile_revision and mixer_revision. Read-only.

# Compare two existing saved profiles directly, no confirmation and NO writes:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control compare-profiles cinema cinema-alt
# JSON shows all four values side by side, plus only differences and signed
# delta (right minus left). No active mixer or profile file is modified.

# Clone an existing custom profile to a NEW name, never overwriting either:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview copy-profile cinema cinema-alt
# Review source, destination, stored levels and profile_revision from the output.
# Separately confirm the catalog revision from that exact preview:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-profile-save --if-profile-revision p1-REPLACE-WITH-64-HEX-CHARS copy-profile cinema cinema-alt

# Capture the CURRENT requested mixer levels as a new private named profile:
# 1) Preview the exact currently stored (not measured) four levels and REV:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview save-current-profile my-snapshot
# 2) Independently approve writing the profile; use the REV from step 1:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-profile-save --if-preview-revision v1-REPLACE-WITH-64-HEX-CHARS save-current-profile my-snapshot

# Overview all current profile choices in one read-only command:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control profile-choices
# Lists every saved profile alphabetically, master/music/laptop/tablet levels,
# their signed changes versus currently requested levels, whether a muted
# input would remain muted, and which volume changes are on muted inputs.
# No profile selection or mixer change occurs. To choose, first run:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview profile cinema
# Then independently approve via the preview's exact revision:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-64-HEX-CHARS profile cinema

# Local, user-defined volume profiles (up to eight, fixed safe names):
# First define a private profile; this does NOT modify the active mixer:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-profile-save save-profile cinema 25 30 50 15
# Read the stored names and requested levels; no writes or network use:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control list-profiles
# Preview the profile's effect against the CURRENT mixer (retains all mutes/EQ):
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview profile cinema
# The new profile_impact report highlights each requested volume delta,
# which inputs remain muted and which volume changes remain inaudible
# while muted, plus explicit no-unmute, no-EQ-change, no-hardware-proof flags.
# Separately confirm with the preview's own revision. A stale revision rejects:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-64-HEX-CHARS profile cinema

# Three conservative BUILT-IN volume presets; preview before any save:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview preset quiet
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview preset balanced
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview preset music-priority
# Use the preview's exact revision to avoid overwriting another local change:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --if-preview-revision v1-REPLACE-WITH-64-HEX-CHARS preset quiet

# Confirm and save, then wait at most ten seconds for a matching recent,
# COMPLETE PipeWire supervisor command acknowledgement (NOT measured audio):
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --wait-for-supervisor set-mix 20 35 25 0
```

For a convenient **read-only overview of all saved profiles** before
selecting one, run `profile-choices`. This lists up to eight private
profiles in alphabetical order; each entry contains its four requested
volume percentages, signed `deltas_from_current` versus the same
currently requested mixer snapshot, `would_change`, `already_matches`,
all `muted_sources_remaining_muted`, and
`volume_changes_while_muted` for muted inputs whose stored volume
would change. It reads one consistent generation of the private
catalog and mixer settings (verified against concurrent replacement of
either), and offers `mixer_revision` and `profile_revision` as
read-only context. An uninitialized configuration shows an empty
`profiles=[]` list, no files or locks are created, and no audio or
network operation occurs. These are **requested percentages**, not
measured physical output or hearing-safety assessments. The overview
cannot select, activate, unmute, or modify a profile or EQ, and does
not accept mutation or confirmation switches. To select one profile,
first inspect `--preview profile NAME`, then use a **separate**
`--confirm-local-mixer-change --if-preview-revision REV profile NAME`
if you explicitly want to request those levels, preserving mute and
stored EQ. No automatic selection or retry is introduced.

A saved profile now has a clearer **read-only selection preview**
through `--preview profile NAME`. Alongside the existing versioned
`before`/`after`, `planned_changes` and `revision` output,
`profile_impact` explicitly displays the named profile, master level
before/after/signed delta, fixed-order music/laptop/tablet volume
before/after/signed delta, each input's **preserved mute state**,
`muted_sources_remaining_muted`, and the
`volume_change_while_muted` flag. That flag is true only when
the profile changes a muted input's saved requested volume: it will
**remain muted**, so the level change is not audible while the mute
is enforced. A source can still become audible later if an operator
separately unmutes it; this is not a physical safety certificate.
`changed=false` clearly indicates no requested volume values differ;
it does not mean actual playback was measured. The impact is derived
from exactly the same one-time before/after preview snapshot, with
no second settings read, and also appears inside `fresh_preview`
when a guarded profile application is rejected as stale (exit 4).
`mute_states_preserved`, `stored_eq_preserved` and
`separate_confirmation_required` remain explicit. This extension
does **not** add any automatic application, restore, routing, physical
sound measurement or network API. Only a separate
`--confirm-local-mixer-change --if-preview-revision REV profile NAME`
may save the requested levels through the existing exclusive lock.
All percentages are requested levels, not loudness measurements.

To compare one stored profile with the **currently requested local
mixer settings** without activating or rewriting anything, run
`compare-profile-current NAME`. The command reports the saved and
current requested master/music/laptop/tablet percentages and a
fixed-order `differences` list for changed fields only. Each entry
has `control`, `saved`, `current` and signed `delta` equal to
current minus saved; `same_levels=true` with an empty list means
the two requested four-value configurations match. Both
`profile_revision=p1-...` and `mixer_revision=v1-...` indicate
which source generations were read, **not** a physical speaker or
PipeWire measurement. The command checks both files before and after
reading the validated catalogs/settings and refuses a concurrent
replacement of either one, including same-content (ABA) replacements.
A missing mixer settings file is compared against the documented
default requested values, never interpreted as live audio.
This operation neither creates files or locks, nor saves settings,
unmutes an input, adjusts stored EQ, applies a profile or changes a
profile. No confirmation flags, `--preview` or version-guard
mutation flags are accepted for this read-only comparison.
Use the existing separate `--preview profile NAME` and confirmed
guarded `profile NAME` commands only if you intentionally want
to activate the stored requested volume levels.

To compare two existing saved profiles without changing anything, run
`compare-profiles FIRST SECOND`. This read-only command validates and
reads a single stable generation of the private catalog and produces
`mode=profile-compare-only`, `left_volumes` and `right_volumes` for
master/music/laptop/tablet, a fixed-order `differences` list and
`same_levels`. Each changed level includes `control`, `left`,
`right` and a signed `delta` representing **right minus left**:
positive means the second saved requested percentage is greater;
negative means it is lower. A completely identical four-level
configuration reports `same_levels=true` and `differences=[]`
even if the profile names differ. These are saved **requested**
percentages, not speaker loudness or measured gain, and no EQ or
mute change is implied. `profile_revision=p1-...` identifies the
compared private catalog generation and cannot infer live audio
status. No file, directory, lock, mixer setting, profile or PipeWire
command is created/written. The command requires two distinct,
existing safe names and refuses unsafe/corrupt/symlinked catalog state
or a simultaneous catalog replacement. Confirmation flags, mutation
revision tokens and `--preview` are deliberately not accepted:
comparison itself is always read-only. Keep the returned private
profile values local, not in public logs.

To duplicate an existing private volume profile safely, use
`--preview copy-profile SOURCE NEW-NAME`. It reads the validated
private profile catalog and emits a **read-only** plan with source,
destination, four volume values and a `profile_revision` starting
with `p1-`; the preview neither writes a catalog nor touches the
active mixer. After reviewing, independently invoke
`--confirm-local-profile-save --if-profile-revision PROFILE_REV
copy-profile SOURCE NEW-NAME`. This is an atomic, exclusive-locked,
single **private profile catalog** update, never an active mixer
settings update. It refuses unknown sources, invalid or identical
names, existing destination names, the eight-profile limit, unsafe
catalogs and stale catalog generations. A separate local profile
writer makes the preview revision stale even if it restored identical
values: copying then exits **4**, with a fresh read-only plan where
safe, never automatically retrying or overwriting any profile. The
source remains immutable, the destination has exactly the same
four bounded requested volume percentages, and no mute, EQ, routing,
network or physical sound is affected. `--if-profile-revision` is
**different from** mixer `--if-preview-revision`; it is accepted
only for a separately confirmed `copy-profile`, not an unguarded
change. The profile snapshot and revision are local private
operator details, not credentials; keep them out of public logs.
No delete, overwrite, rename or automatic activation is introduced.

For an exact snapshot of the **currently requested** private mixer
master/music/laptop/tablet levels without retyping them, use
`--preview save-current-profile NAME`. It prints a no-write
`mode=profile-capture-preview` report with four bounded `volumes`
and the same mixer generation `revision` used by guarded setting
changes. No profile file, settings file, lock or directory is created
by the preview when absent. To create the profile, issue a **separate**
`--confirm-local-profile-save --if-preview-revision REV
save-current-profile NAME` command with the exact revision you
just reviewed. Profile catalog creation and the mixer generation check
occur under the **same exclusive local writer lock**: if any later
mixer write changed master, a source volume, a mute, or even stored EQ,
the profile is NOT saved (exit 4) and a new read-only capture preview
is offered for renewed approval. A missing, malformed, unsafe or
already-named catalog is never overwritten. Successful capture saves
only the four volumes; it does not copy mutes or EQ, and it does not
change the active mixer or claim real speaker sound. The operator
must still separately preview and approve any later application with
`--preview profile NAME` and a confirmed `profile NAME` command.
The 8-profile immutable name limit and 0600/0700 safety rules also
apply to captured profiles.

Local user-defined `save-profile NAME MASTER MUSIC LAPTOP TABLET`
stores a **volume-only** profile under the unprivileged account in
`~/.config/audiohub/volume-profiles.json`. This is an operator-initiated
private **0600** atomic JSON write beneath a user-owned **0700**
directory and uses the same exclusive local mixer writer lock. A separate
`--confirm-local-profile-save` is required to CREATE a profile, but
saving does not change the active mixer or run PipeWire commands.
`list-profiles` reads the bounded catalog without creating files or
locks; `--preview profile NAME` shows exactly the would-be requested
values; and `--confirm-local-mixer-change --if-preview-revision REV
profile NAME` applies it via the existing guarded atomic mixer save.
All 3 input `mute` states and stored `bass/mid/treble` values remain
unchanged. Profile names are strictly 1–24 ASCII lower-case letters,
numbers and hyphens beginning with a letter; paths, shell syntax,
arbitrary fields, routes and unknown profile names are rejected.
Master/input volume values must all be integers 0–100 (not booleans).
Only **eight** custom profiles can be created. Existing names cannot
be overwritten and no profile-removal or automatic-activation command
is introduced in this increment; new profiles require unique names.
Malformed, symlinked, insecure or non-canonical existing profile data
fails closed rather than being discarded. A custom profile is only a
stored preference, not a calibrated sound level, guaranteed
three-source hardware mix or hearing-safe setting.

Built-in local `preset NAME` offers three convenient **volume-only**
starting points. All requests are one schema-validated, locked, 0600
atomic settings save, not independent partial changes.

| Preset | Master | Music | Laptop | Tablet |
| --- | ---: | ---: | ---: | ---: |
| `quiet` | 15 | 25 | 25 | 25 |
| `balanced` | 30 | 40 | 40 | 40 |
| `music-priority` | 30 | 55 | 20 | 20 |

These are **requested percentage levels**, not calibrated loudness,
physical speaker dB, measured SPL, proof of clipping protection or
certified hearing-safe settings. Importantly, presets do **not** unmute
any input, change stored EQ bands or alter source routing; existing
mute and EQ values are preserved exactly. Confirm any preset using
`--confirm-local-mixer-change` (and preferably the exact
`--if-preview-revision` from a separate read-only preview).
`--wait-for-supervisor` remains optional and checks only software
acknowledgement, not measured sound. Presets do not automatically
restore a prior configuration; inspect the preview and keep the
physical output low. The names are a fixed allowlist, with no user
provided arbitrary volume numbers, paths or commands.

The optional `--preview` applies to all change commands:
`set-master`, `set-volume`, `mute`, `mute-all`, `unmute-selected`,
`preset` and `set-mix`. It outputs only validated requested master/input
volume and mute values (`before` and `after`) and a deterministic
`would_change` list, plus readable `planned_changes` entries with
`control`, `previous` and `current` values. It also emits a
compact `comparison_baseline` beginning `b1-`, representing ONLY
the fixed, bounded local master/input volume/mute and stored EQ values.
Unlike `revision`, this baseline stores actual control values and can
be passed to a later `--preview --compare-baseline BASELINE` command.
The result's `changed_since_baseline` pinpoints individual input
volume/mute and stored `bass`, `mid`, `treble` changes: e.g.
`laptop.volume` 50→17 and `laptop.mid` 0→−4. A `null` comparison
means no earlier snapshot was supplied; an empty list `[]` means no
compared **value** differences. It does not infer changes merely from
a stale revision hash, nor prove runtime EQ is currently applied.
The baseline does not include device identifiers, addresses, network
configuration or secrets. It is not a permission credential; however,
it encodes operator mixer preferences and should stay in the local
private console workflow. It is never stored by the preview command.
On a guarded `--confirm-local-mixer-change --if-preview-revision REV`,
an optional **validated** `--compare-baseline BASELINE` may also be
included, so a stale exit 4 response can show the exact changes from
the earlier preview inside its fresh read-only plan. Invalid or unsafe
baseline input is rejected **before** any write. It cannot be combined
with a plain, unguarded change or read-only `show`/`status`. The response explicitly states
`settings_written=false`, `supervisor_applied=false` and
`audible_playback_verified=false`. No config directory or lock is
created when settings do not yet exist. Corrupt, unsafe or symlinked
existing settings refuse the preview instead of silently replacing
them. `--preview` refuses an accompanying change-confirmation flag,
and it is invalid for read-only `show` and `status` commands.
A preview now also returns an opaque version token `revision` prefixed
`v1-`, derived from the entire validated settings snapshot **including
EQ** and its private file generation. The operator may copy that token
into the next confirmed command using `--if-preview-revision REV`.
Only an exact matching revision is accepted under the existing exclusive
writer lock: any intervening settings change (including EQ alone or
A→B→A return to the same values) rejects the entire write rather than
silently overwriting someone else's settings. Two competing conditional
writers cannot both commit from the same snapshot. Missing settings may
be previewed without creating any directory or lock; its revision also
works for the first confirmed update. A preview is NOT a reservation;
the token is a one-use generation comparison, not an authentication
credential. Never combine `--if-preview-revision` with `--preview`,
`show` or `status`, and explicit `--confirm-local-mixer-change` remains
mandatory. If the guarded change is refused **because its version is
stale**, the CLI now exits with status **4** and prints a structured
`status=preview-stale` response. It includes
`settings_written=false` and a brand-new, **read-only**
`fresh_preview` for the same requested action, with updated
`before`, `after`, `would_change` and `revision`. It does
**not** save, merge, replay or automatically approve the desired
change. Read the new plan first; only then copy its latest revision to
a **separate** confirmed invocation. If the current private settings
became unsafe or the refresh cannot be read, only a sanitized error is
shown; no settings or arbitrary filesystem details are exposed.
Invalid confirmation, arguments or malformed version tokens retain the
existing generic exit status **2**, with no automatic refresh. The
new preview is itself a snapshot, so a further intervening writer is
still rejected by the guarded save. No network API or actual hardware
verification is added.

The three names `music`, `laptop` and `tablet` are internal stable input
slots, **not** fixed categories of physical device. All levels are
integers from 0 to 100; mute accepts only `on` or `off`. Each explicit
change updates a private, user-owned, **0600** JSON file in a **0700**
directory with an atomic replacement and exclusive local writer lock.
Missing state starts at the known AudioHub defaults; corrupt, unsafe,
symlinked or unreadable existing state is **refused rather than reset**.
Concurrent operator changes cannot lose one another. The local
`mute-all` command requests all three input mutes in **one** private
atomic write, preserving requested master volume, input volumes and EQ.
It never automatically unmutes: a deliberate `mute SLOT off` or the new
`unmute-selected SLOT [SLOT]` is required to re-enable exactly the chosen
one or two inputs. `unmute-selected` refuses duplicate slots and all three
slots, so it can never implicitly act as `unmute-all`. It keeps all
unselected inputs muted as before, preserves master/source levels and EQ and
writes once under the existing lock; there is no partial intermediate
restore. It requires the existing
explicit confirmation and non-root account, rejects unsafe existing state
and creates no network API. Its request takes effect only on a later
successful supervisor poll; it is **not an emergency physical cutoff**
and cannot guarantee immediate or audible silence. For emergencies,
disconnect or turn down the physical speaker amplifier.

The `set-mix`
command accepts exactly four 0–100 integers in the order master, music,
laptop, tablet and saves all four volumes **in one atomic snapshot** rather
than exposing intermediate levels across four separate console calls.
It deliberately preserves all prior per-input mute and EQ settings. Any
invalid number or unsafe existing state rejects the entire request;
it never resets settings as a fallback. The existing supervisor observes
the new settings on a later poll (normally every five seconds) and
retains its existing fail-closed gain controls.

The optional `--wait-for-supervisor` can be added only to an explicitly
confirmed **change** command (not `show`, `status` or `--preview`).
The CLI first saves the validated settings atomically, then reads the
already private local supervisor acceptance status up to eleven times
over **at most ten one-second waits**. A matching software acceptance
is valid for this particular write **only if the timestamp of that same
complete supervisor snapshot is strictly later than the save**. A
still-fresh but pre-write acknowledgement, even with identical volumes
and mute settings, remains unconfirmed until another supervisor poll;
the check may therefore wait for the next five-second cycle. A missing,
invalid or boolean snapshot timestamp never proves acceptance. Its JSON report distinguishes
`settings_written=true` from `delivery_state=accepted`,
`pending`, `unavailable` or `superseded`. It also includes bounded
`saved_request` controls, `pending_controls`, and always
`audible_playback_verified=false`. A different later request from
another local writer returns `superseded`: acceptance of that later
request must never be attributed to the first invocation. A completed
command with no fresh, complete acknowledgement exits with status **3**
while clearly saying the settings **were saved**; it does **not** retry
the write or assert that hardware sound changed. A matching successful
supervisor software acknowledgement exits with status 0. Existing
`status` remains available for later read-only checks. This does not
make the audio process, PipeWire, speakers or real sound synchronous and
is not an emergency mute. Keep physical volume low.

The read-only `status` command compares private saved master/input
level/mute settings against the last **successful set of PipeWire control
commands**, provided the supervisor reported a unique USB output, all three
EQ sinks and a complete recent poll (15 seconds or less). It reports
`accepted`, `pending` or `unavailable`, never equates status with
measured volume or audible sound. On a fresh complete acknowledgement,
`pending_controls` identifies exactly which requested fields differ:
`master`, `music.volume`, `music.mute`, `laptop.volume`,
`laptop.mute`, `tablet.volume` or `tablet.mute`. For example, after
changing only Input 2 mute and Input 3 volume, the output identifies
`["laptop.mute", "tablet.volume"]`, so the local operator knows which
controls remain unacknowledged. A matching acknowledgement returns `[]`.
A missing/stale/unsafe/legacy supervisor snapshot is **unavailable** and
returns `null`, **not an empty list or a claim of success**. The comparison stays entirely on
the unprivileged local console, writes nothing, returns no MAC/SSID/device
identity and adds no public web API; `audible_playback_verified` remains
false regardless of command outcome.

These controls change **requested software volume and mute**, not the
physical speaker amplifier or measured sound pressure. Keep physical
volume low before testing. They do not expose the per-band EQ editor:
changing EQ gains would also require safe runtime filter application and
is **not implemented** here. No automatic claim of audible playback,
clipping protection, 3-way mixing acceptance or production release
approval is produced. Never run as root, on a production unit, or without
separate authorization for the affected physical hardware.

## Local console-only engineering commands

Run as the **unprivileged audiohub Linux user** in an isolated development
test setup, not via HTTP, from an already-authorized local console.
A consumer-ready headless way to configure this does **not** exist.

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes show

# New: LOCAL runtime evidence per mixer input, no identity, no writes:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes status

# Human-readable one-screen offline troubleshooting: JSON remains default.
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --format text status

# Explicitly opt in to BlueZ property inspection, still no pairing/connect:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --format text --probe-bluetooth status

# Optional read-only BlueZ connection-property check of manual Bluetooth slots:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --probe-bluetooth status

# New: read-only reservation map. Shows free inputs, not connected devices:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes slots

# New: what-if routing preview. NO policy file or lock is created:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --preview set-lan music
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --preview bind-bt AA:BB:CC:DD:EE:FF laptop
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --preview mode manual

# Safe LAN/Bluetooth slot EXCHANGE: only manual mode with a BT-occupied slot.
# Example: LAN currently laptop, assigned BT currently music. Does not
# connect/pair a device, and does not change either source's trust status.
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --preview swap-lan music
# Inspect private old/new plan and revision, then separately run:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --confirm-local-route-change --if-preview-revision r1-REPLACE-WITH-64-HEX-CHARS swap-lan music

# Exchange TWO MANUALLY assigned Bluetooth input slots in one policy update:
# Example: music and tablet are both occupied by different BT peers.
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --preview swap-bt music tablet
# After privately reviewing the exact route revision and both mappings:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --confirm-local-route-change --if-preview-revision r1-REPLACE-WITH-64-HEX-CHARS swap-bt music tablet

# Inspect the output revision r1-... and its impact: old/new occupied slots,
# Bluetooth sources removed/added and potential auto-discovery disablement.
# After REVIEW, independently approve EXACTLY that preview generation:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes --confirm-local-route-change --if-preview-revision r1-REPLACE-WITH-64-HEX-CHARS set-lan music

# Existing direct local engineering commands are also retained for compatibility.
# Prefer the guarded preview + separate confirmation above to avoid stale writes.
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes mode manual
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes set-lan music
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes bind-bt AA:BB:CC:DD:EE:FF laptop
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes bind-bt 11:22:33:44:55:66 tablet
```

For console operators who do not want to interpret nested JSON,
`--format text status` prints one short read-only overview of all
three fixed inputs, with a safe role label, USB status, Bluetooth
PipeWire source node, managed loopback, direct EQ-to-USB graph
observation, optional BlueZ `Connected` property and a human-readable
next-check suggestion. A question mark means unqueried, unavailable
or unverified; it never implies a disconnected device. The view
uses **only fixed English labels and validated boolean values**, never
private addresses, names, node IDs or raw command output. Default
`status` continues to emit the exact existing machine-readable JSON
format for scripts. The `--format text` option is rejected on all
other commands and cannot be combined with policy modification,
`--preview` or mutation approval. The BlueZ probe remains explicit
and opt-in. Neither rendering format proves audible sound or repairs
a device.

For a more practical, truthful source **runtime status** on the authorized
local console, run `python3 -m audiohub.source_routes status`. The
supervisor now stores **only** six booleans per stable input (music,
laptop, tablet) from one PipeWire poll: LAN reservation, permitted
Bluetooth assignment, eligible discovered Bluetooth PipeWire *source
node*, whether the supervisor's managed `pw-loopback` subprocess is
still running, whether the virtual sink was observed, and whether the
USB default-routing command succeeded. These are **observations**,
not verified connections or playback. The local read-only status
report adds `configured_role`, `configured`,
`bluetooth_source_node_seen`, `managed_loopback_process_running`,
`virtual_sink_observed`, `usb_route_ready` and explicit
`bluetooth_connected=unverified`,
`audio_stream_available=unverified`,
`audible_playback=unverified`. A visible `bluez_input` does not
prove pairing or A2DP connection; a running routing subprocess does
not prove audio packets arrived or a USB speaker is audible.

Local `source_routes status` now also exposes per-slot
`eq_to_usb_direct_link_observed=true/false/null` and
`pipewire_graph_inspection_available=true/false/null`.
These values come from the supervisor's **same** bounded `pw-dump`
snapshot that supplied the other source observations. `true` means
the PipeWire graph contained an explicit link between the given EQ
output node and selected USB output node. `false` means a valid graph
was inspected but that **direct** edge was not observed; legitimate
adapter or intermediary nodes may be involved, so this does **not**
mean disconnected or silent. `null` means no trustworthy recent
graph evidence (including an older runtime format, corrupt fields,
invalid routing policy or unavailable graph). The parser accepts
only the fixed music/laptop/tablet slot names with no duplicates or
device IDs. Neither Bluetooth A2DP, PCM samples, clipping, nor audible
speaker playback is proved; all remain explicitly unverified.
No scan, subprocess, audio change, private identifier, file write,
new network API or elevated privilege is introduced by this display.

To avoid interpreting raw booleans by hand, each local `status` input
also receives a fixed, privacy-safe `next_local_check` hint. The
diagnostic decision order starts with stale/private-status recovery,
then USB default-output selection, absent EQ virtual sink, unassigned
input, opt-in LAN receiver, Bluetooth source-node visibility, managed
loopback process, and direct/intermediary PipeWire links. A fully
observed path recommends `verify_actual_speaker_audio`, which is a
**manual test instruction**, never a claim that sound was heard.
Example values include `inspect_usb_default_output`,
`inspect_bluetooth_pipewire_source`, `inspect_managed_loopback`,
`inspect_pipewire_graph`, and `inspect_possible_intermediary_links`.
These are inert guidance strings: there is no automatic repair,
scan, pairing, reconnect, route activation, file write or new service.
When explicitly using `--probe-bluetooth status`, a known
`Connected: no` value can prioritize
`inspect_bluetooth_device_connection` after basic USB/EQ prerequisites.
Unknown and stale evidence never become a false disconnected claim.

Source evidence comes from one **unmodified** owner-private
`runtime-status.json` snapshot, never a fresh Bluetooth scan.
`fresh` requires a trusted supervisor timestamp within 30 seconds;
missing, stale, unsafe, invalid-schema or inconsistent snapshots
report `observations_available=false` with `unknown` fields rather
than calling a device disconnected or suppressing errors as success.
If routing policy validation fails, source evidence is unavailable
until a subsequent valid poll. The output never includes MAC/IP,
node IDs, SSID, peer names, passwords or raw PipeWire records. It is
**not** added to the anonymous HTTP status API, and it creates no
files, locks, processes, Bluetooth pairing or network connections.
`source_routes status` rejects all change/approval/preview flags.
For additional **actual BlueZ link-state evidence**, an operator may
explicitly run `python3 -m audiohub.source_routes --probe-bluetooth status`
on the authorized local machine. Unlike the default status command,
this uses an **on-demand**, bounded `bluetoothctl info ADDRESS` call
(maximum two manually assigned devices, 3 seconds each, 4096 bytes
output, argv-only subprocess, discarded stderr, no shell), strictly
extracting one matching BlueZ Device header and exactly one
`Connected: yes/no` property. Input addresses come only from
the existing private validated manual routing policy; **they are
never included in the JSON output, journal logs or HTTP API**.
Each manually assigned slot receives
`bluez_connected_property=true/false/null`; null means missing
or ambiguous connection evidence. Even `true` means only
BlueZ's local device Connected property was yes at query time,
**not** that A2DP audio was streaming, PipeWire delivered PCM,
the speaker was audible, or the device is owner-trusted. Accordingly
`bluetooth_connected`, `audio_stream_available`, and
`audible_playback` remain explicitly `unverified`.

This optional query is **not** run by the supervisor or default
`status`, and cannot pair, scan, connect, trust, change policy,
unmute or save anything. The flag is refused for all commands except
`status`; no query runs if the last runtime snapshot is stale,
unavailable or inconsistent, the policy uses auto discovery, or
manual assignments differ from the runtime snapshot. Private policy
replacement during the probe invalidates all readings (including
same-content ABA replacements). It is deliberately opt-in so
unavailable BlueZ devices do not delay normal source routing.
Owner enrollment, actual A2DP playback and acoustic/USB hardware
acceptance remain separate release gates.

A free slot in `source_routes slots` is still only a
reservation-policy fact. Actual Bluetooth connection and PCM delivery
need separate device-specific hardware evidence before release.

Read-only `slots` explains which stable inputs are reserved by LAN or
explicit manual Bluetooth assignments, which remain available for
manual assignment, and the current private policy revision. A free
input is **not** proof that a Bluetooth device is actually present,
paired, connected or audible. `--preview set-lan`, `--preview bind-bt`,
`--preview unbind-bt` and `--preview mode` display an exact, validated
old/new local route plan, including slot occupancy, removed/added
assignments, and whether the proposal would disable automatic
Bluetooth discovery. Invalid three-way/duplicate source reservations
fail immediately without touching files, locks or devices. The
`r1-...` revision identifies a PRIVATE local policy file generation
(including atomic ABA replacements), not a device identity.

After reviewing the preview, the operator can separately run
`--confirm-local-route-change --if-preview-revision REV ACTION ...`.
The original route generation is checked **inside the exclusive
local route-policy writer lock** before updating one private policy
file. A concurrent change is rejected with exit code 4 and at most a
new read-only `fresh_preview`, never automatically retried. Both
confirmation and revision must be present for this guarded path;
`--preview` can never be combined with a write flag. Existing
ungarded direct console commands are retained for compatibility
but do **not** give protection against stale preview revisions;
operators should prefer the guarded sequence for manual changes.
No new network service, Bluetooth pairing, trust, external device
control or physical-audio verification is introduced. Keep local
Bluetooth addresses and policy previews out of public logs.

The MAC addresses above are **fictional test examples**. Pairing or
authenticating a real device is **not** performed by these commands.
Manual mode has **no automatic fallback** for unknown BlueZ sources.
A rejected duplicate, third BT source, malformed MAC, occupied LAN
slot, unknown field, corrupt JSON, unsafe file permissions or symlink
prevents a policy update. The old valid plan remains intact. On a
corrupt plan, the live supervisor **denies all Bluetooth routes** and
stops existing managed loopbacks instead of silently returning to
automatic pairing. A repaired plan is reloaded on the next poll.

When the target LAN slot is **already occupied by a manually
assigned Bluetooth source**, use `--preview swap-lan SLOT` instead of
temporarily unbinding the Bluetooth source. The preview describes a
single valid new route plan: LAN moves to that occupied slot and the
exact manual Bluetooth assignment moves to the old LAN slot. A
separate `--confirm-local-route-change --if-preview-revision REV
swap-lan SLOT` commits that single private policy generation under
the existing writer lock. This operation is rejected in automatic
mode, for an empty target, for the same LAN slot, with no explicit
confirmation, or after any concurrent replacement of the policy
(including identical-content ABA updates). No implicit retry occurs,
and a stale attempt only presents a fresh read-only proposal. All
other Bluetooth bindings and the manual allowlist are preserved.
The routing supervisor may briefly restart affected audio streams
on its next polling pass; do not assume seamless or audible playback.
This local operation is **not** device authentication or a consumer
phone UI, and cannot pair, trust, connect, open Scream UDP, or
independently validate delivered PCM. Keep the local preview with
Bluetooth addresses out of public logs.

If two Bluetooth input slots are both manually occupied,
`--preview swap-bt FIRST SECOND` safely proposes exchanging the two
existing **source-to-EQ-slot bindings** in a single policy generation.
The LAN reservation is never moved. A later
`--confirm-local-route-change --if-preview-revision REV swap-bt FIRST
SECOND` applies exactly that reviewed preview. Unlike multiple
unbind/rebind commands, no intermediate missing or duplicated source
assignment is persisted. This requires manual routing mode, distinct
non-LAN input slots with exactly one manually assigned Bluetooth source
each, and a valid unchanged policy revision under the exclusive
writer lock; unconfirmed, empty/invalid and stale/ABA proposals are
rejected without automatically retrying. Bluetooth source addresses
are displayed ONLY in the authorized private preview, not the
anonymous HTTP API. Active streams may restart when the supervisor
polls the changed policy; this is not a zero-dropout switch or proof
of owner trust, Bluetooth connection, PCM or audible playback.

To move an existing route into an **empty** slot, use the existing
guarded `--preview set-lan SLOT` process; to choose an occupied
Bluetooth slot use `swap-lan`. The switch is an atomic, local
**0600 file in a 0700 directory**, with a per-directory
exclusive lock. No write API exists on the anonymous status page.
No private addresses or route tables are sent to an unauthenticated
browser. Local plan file:
`~audiohub/.config/audiohub/source-routes.json`.

Example manual LAN launch **on an isolated lab network only**, after
setting `set-lan music` above:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.network_laptop \
  --sender-ip 192.168.55.10 --bind-ip 192.168.55.20 \
  --port 4010 --unsafe-lan-test --prefill-packets 3
```

The receiver reads the configured LAN target, requires the matching
real EQ virtual sink and a successfully selected USB audio output
**before** opening the UDP socket. It pins the target at process start
and **stops** if the local routing policy changes. It never switches
to HDMI or a random default sink. The CLI still requires deliberate
`--unsafe-lan-test`, and the image includes **no systemd service**
to auto-start this unsafe receiver.

## Tests and boundaries

- 3 logical EQ sinks; exactly one reserved LAN target; zero to two
  manually assigned distinct Bluetooth MACs to the other two slots.
- Auto mode preserves legacy pairing behavior among the two non-LAN
  slots. Manual mode routes only explicitly listed source MACs.
- `source-routes.json` uses bounded JSON/strict schema, owner-only
  0600 file and 0700 directory, no-follow, atomic replace, locks;
  corruption fails closed, never auto-recovers into broad trust.
- Physical sound, real dual-A2DP feasibility, latency, clipping,
  Windows Scream transport, 24h soak and recovery are **still open**.
  A MAC mapping by itself is not a cryptographic proof of device
  identity. A pairing/owner enrollment step must precede assigning
  trusted sources on real consumer devices.
- Browser names are still **browser-only preview**; local name
  storage is independent of this source plan. This is not a full
  phone-first management interface or authorization mechanism.
- No network role is automatically enabled. Scream is plaintext,
  unauthenticated and spoofable; production use needs an entirely
  authenticated transport reviewed for consumer LAN use.

Next acceptance work: integrate owner-proven identity, paired-device
registry, authenticated local API/CSRF/session, safe three-slot source
selector, and real Pi4/Edifier tests. See
[PROJECT-HANDOFF.md](PROJECT-HANDOFF.md),
[ENGINEERING-BACKLOG.md](ENGINEERING-BACKLOG.md),
[GitHub Issue #27](https://github.com/RIVANOXcom/rivanox-audiohub/issues/27).
