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
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview mute-all
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview unmute-selected music laptop
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --preview set-mix 20 35 25 0

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

# Confirm and save, then wait at most ten seconds for a matching recent,
# COMPLETE PipeWire supervisor command acknowledgement (NOT measured audio):
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.mixer_control --confirm-local-mixer-change --wait-for-supervisor set-mix 20 35 25 0
```

The optional `--preview` applies to all change commands:
`set-master`, `set-volume`, `mute`, `mute-all`, `unmute-selected`
and `set-mix`. It outputs only validated requested master/input
volume and mute values (`before` and `after`) and a deterministic
`would_change` list. The response explicitly states
`settings_written=false`, `supervisor_applied=false` and
`audible_playback_verified=false`. No config directory or lock is
created when settings do not yet exist. Corrupt, unsafe or symlinked
existing settings refuse the preview instead of silently replacing
them. `--preview` refuses an accompanying change-confirmation flag,
and it is invalid for read-only `show` and `status` commands.
A preview is NOT reserved: another local writer may change the
settings before the operator separately runs a confirmed command.
Always inspect current controls again before deciding. No network
API or actual hardware verification is added.

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
