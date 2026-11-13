# Development status

**Status:** Alpha / pre-release. No verified ready-to-flash Pi 4 image has been published. Native ARM64 test-only SD images have been built and uploaded to GitHub Actions (latest prior-to-renaming run 42057278883; 159 tests, 48 rootfs checks). **No real Pi4/Edifier playback, ownership security or product-ready Release has been verified.**

## Manually controlled offline local music source

A new unprivileged Pi4 command plays validated user-provided PCM WAV
through the existing private `audiohub.music` PipeWire sink with
bounded duration and 20% initial stream gain. Preview is default; only
an explicit terminal `--play` triggers playback, Ctrl+C stops; no
network, pairing, permission or mixer changes. A local album picker now lists numbered tracks from one bounded private directory,
permits explicit ordered selection and hides names by default. Source tests and native
Pi4 package checks still do **not** prove actual audible playback.
See [local WAV source playback](LOCAL-MUSIC-PLAYBACK.md).

## Local music playback interactive session

The optional `--play --interactive` flag supports an explicitly
selected local WAV queue with reversible child-only pause/resume,
anonymous overview, previous/replay,
direct numbered jumping, status, next-track and stop commands at
a trusted Pi4 operator terminal. No remote API, permissions,
persistent data or mixer changes. Existing default preview and
direct `--play` remain backward compatible. A fix to the original
player wait also handles long tracks within the configured 30-minute
session instead of failing after a fixed 10-second wait. Actual Pi4
speaker audio and production approval remain unverified.

## Goals

- USB speaker playback using Edifier R600USB where recognized as a USB-audio device
- Phone Bluetooth A2DP input with simple initial pairing and reconnection
- Laptop network audio input
- Third tablet audio input, including a two-Bluetooth-source test and supported alternatives
- Independent gain, mute and three-band EQ per input, plus master volume
- Local-first web UI localized in en/de/es/fr/it
- Self-configuring headless first boot and recoverable network provisioning
- GitHub-hosted reproducible image builds and verified release assets

## Local Bluetooth first-use feedback (still unverified)

A new Pi4 local-console command `python3 -m audiohub.pairing_readiness`
reads the BlueZ system bus without changing the controller or trusting
devices. It explains whether initial experimental pairing appears open,
closed, expired, full, or unexpectedly open. The existing offline first-boot
FAT report now includes an anonymous last pairing-state summary, readable
after shutdown without a connected screen or network. These records do
not authenticate the owner, configure Wi-Fi, or verify Bluetooth audio.
See [read-only Pi4 pairing guide](PI4-BLUETOOTH-FIRST-USE.md).

## New no-network first-boot report viewer

An independent five-language offline HTML viewer allows the operator
to inspect a bounded anonymous Pi4 SD `AUDIOHUB-TEST-REPORT.json` in
a browser on a trusted computer without Python, LAN pairing or
uploading the report. Bundled in the existing Windows portable ALPHA
test workflow. This is not authenticated ownership or hardware GO.

## Status definitions

**Designed** means the architecture has been drafted. **Implemented** means code exists. **CI validated** means automated code-level tests have passed. **Hardware verified** means logs and a repeatable Pi 4 procedure demonstrate it works. **Released** means an image and checksum are available from GitHub Releases.

None of the planned audio feature paths has been marked hardware verified in this repository.

## Release blockers

1. First-boot authentication must not rely on a shared published secret.
2. A bootable image must be built from pinned inputs and pass offline/first-boot checks.
3. Bluetooth A2DP with a real phone must be tested.
4. Simultaneous audio paths, per-source EQ, USB speaker output and recovery must be tested.
5. Legal notices, attribution and applicable EU requirements must be assessed for the distributed artifact.

No release should claim Bluetooth parallelism, zero-setup provisioning or hardware compatibility without evidence.

### Local music guided terminal picker

The optional Pi4 `--guided --library ABSOLUTE_FOLDER` workflow
shows anonymous numbered WAV tracks, accepts an explicitly chosen
bounded sequence and asks for exact uppercase `PLAY` before starting
the existing interactive music session. Local TTY and non-root user
are mandatory; invalid input, cancellation or failed confirmation do
not start playback. This changes no mixer, Bluetooth, owner or service
settings. Real hardware audio and public distribution remain NO-GO.

### Guided WAV album selection shortcuts

The Pi4 offline terminal wizard now offers `ALL` for at most eight
listed WAVs or `SHUFFLE` for a locally random, bounded selection that
fits the existing maximum session duration. It displays the chosen
*anonymous library numbers* before sound. The operator can type
`CHANGE` twice to correct the queue; only exact uppercase `PLAY`
activates the already validated interactive music player. No new
network service, audio route, ownership binding, keys, media files
or persistent playlists were introduced. Real Edifier playback and
public-release gates remain unverified.

### Native Pi4 operator launcher for guided music

A new **unverified test image** installs `/usr/local/bin/audiohub-music`
plus an initially empty `/home/audiohub/PrivateMusic` (0700,
operator-owned). A trusted locally logged-in unprivileged Pi4 operator
can type `audiohub-music` instead of a PYTHONPATH-based Python CLI.
The launcher shows `--help`, allows one optional absolute private
folder, and delegates to the existing guided WAV player with an exact
PLAY confirmation. Native ARM64 installation executes a nonplaying
command smoke and rootfs checks for the installed entrypoint. This
does not add a network controller or guarantee headless phone setup.
No in-place updater or automatic data migration is introduced; spare
SD and separately retained operator music are required for rollback.
Real hardware audio, rights and public release gates remain NO-GO.

### Volatile interactive repeat controls for Pi4 music

The unverified local music wizard now supports the `m` keyboard
command during explicitly started playback. It cycles OFF → TRACK →
ALL → OFF (repeat selected track, repeat reviewed queue or stop
repeating), reflects the mode in anonymous status and queue output,
and honors manual next/previous/quit. The original wall-clock deadline
never resets, including during pause or repeat. Mode is private
in-memory session state; nothing is saved and no new service or audio
route is introduced. Native Pi4/Edifier audible hardware validation,
rootfs copyright compliance and official release GO remain outstanding.

### Manual operator WAV backup/restore for spare-SD testing

The unverified Pi4 alpha now stages an `audiohub-music-transfer` CLI
with explicit `backup` and `restore` to an independently retained,
already mounted and owner-only external directory. A separate uppercase
`COPY` confirmation guards bounded media copying. The source is
preserved, existing files are never replaced, destination WAVs are
owner-only mode 0600 and each copy is checksummed before publication.
No network, OS update, mount, privilege, deletion of user WAVs,
credentials or automatic music migration occurs. Failed operations
may leave completed new copies; manual inspection/rollback is required.
The operator retains the prior SD and independent external storage.
Physical Pi4/Edifier audio and official release gates remain NO-GO.

### Resumable offline WAV migration and read-only confirmation

An unverified operator alpha adds explicit --resume on the existing
manual WAV backup/restore commands. It hashes existing same-name WAVs
and skips only identical single-link private copies. Missing WAVs require
human COPY; unsafe/conflicting WAVs refuse without overwriting or
automatically removing data. New verify-backup and verify-restore
commands check every supported source WAV against its destination
without any writes. This makes an interrupted multi-file migration
retryable, but it is not a full SD, owner, credential, configuration
or OS updater. Real Pi4 audio and public release remain NO-GO.
