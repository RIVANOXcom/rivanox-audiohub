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

# Local, user-defined volume profiles (up to eight, fixed safe names):
# First define a private profile; this does NOT modify the active mixer:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-profile-save save-profile cinema 25 30 50 15
# Read the stored names and requested levels; no writes or network use:
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control list-profiles
# Preview the profile's effect against the CURRENT mixer (retains all mutes/EQ):
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview profile cinema
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
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes mode manual
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes set-lan music
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes bind-bt AA:BB:CC:DD:EE:FF laptop
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.source_routes bind-bt 11:22:33:44:55:66 tablet
```

The MAC addresses above are **fictional test examples**. Pairing or
authenticating a real device is **not** performed by these commands.
Manual mode has **no automatic fallback** for unknown BlueZ sources.
A rejected duplicate, third BT source, malformed MAC, occupied LAN
slot, unknown field, corrupt JSON, unsafe file permissions or symlink
prevents a policy update. The old valid plan remains intact. On a
corrupt plan, the live supervisor **denies all Bluetooth routes** and
stops existing managed loopbacks instead of silently returning to
automatic pairing. A repaired plan is reloaded on the next poll.

To move an existing route, first unbind the conflicting source or
move the LAN slot into a free slot. The switch is an atomic, local
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
