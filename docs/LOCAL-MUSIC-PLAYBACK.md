# Local music playback: WAV queue for the AudioHub music input

**Unverified operator ALPHA.** A practical offline playback source for
own or licensed local music. No streaming, cloud accounts, Wi-Fi, new
Bluetooth permissions, remote control, media uploads or persistent
daemon. This is NOT the completed phone-owner setup (AH-005 is separately
assigned), nor an independently proven speaker test.

The new native Pi4 image supplies \`audiohub.local_music\` on the
existing unprivileged \`audiohub\` account. It uses PipeWire's documented
raw stdin playback, explicitly targeted to the existing
\`audiohub.music\` virtual stereo mixer input. It does NOT automatically
select the default sound card or bypass the private mixer/EQ routing.

## Start with a file preview (no sound)

On an **operator-authorized isolated Pi4** with its existing per-user
PipeWire graph running, place **your own** valid WAV tracks in a readable
operator-approved local folder (for example mounted read-only media).
Supported tracks: uncompressed 16-bit PCM, mono or stereo, sample rate
8–96 kHz, individually at most 64 MiB. A manual queue supports up to
8 files, max 30 minutes, 15-minute default. No outside URLs or
filenames are shipped in the image.

Run as the **unprivileged \`audiohub\` user** (not root; never invoke
\`sudo\` just to make a rejected audio path work):

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      /absolute/private/path/one.wav /absolute/private/path/two.wav

The default command only displays bounded format/duration counts.
It never opens PipeWire, plays a sound, changes EQ/routing/mutes,
uploads names, or writes a playlist. Every file is validated as an
absolute regular unlinked path, not world writable, with a bounded
file size and strict sample format. Invalid, linked, nonexistent,
unsafe, oversized or unsupported inputs fail closed without printing
private path/device names.

## Explicit user-requested playback

After selecting a modest physical speaker volume and confirming the
existing Pi mixer output is appropriate, the operator can start
the exact reviewed queue with explicit \`--play\`:

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --minutes 10 --play /absolute/private/path/one.wav

Only this command inspects the PipeWire graph and opens a local
\`pw-cat\` process, targeted to **\`audiohub.music\`** (never default
fallback) at a fixed conservative initial stream gain of 0.20.
WAV sample bytes are read from the already opened validated file
descriptor and streamed in bounded chunks to \`pw-cat -\`. The
selected source files are not copied to disk, exposed to a browser
or passed on the process command line; the player receives only raw
PCM on standard input. Nothing auto-starts after reboot.

**Stop / rollback:** press **Ctrl+C** at the controlling Pi terminal.
The owned player process is stopped and its pipe closed. If the
music virtual sink is missing or ambiguous, playback refuses to
start rather than sending private audio to the USB/default output.
No state or configuration changes require rollback: original input
volumes/mutes/EQ and Bluetooth trust are untouched. For normal
recovery, stop the manual playback, inspect existing PipeWire routing
as the unprivileged operator, and use a known-good older Pi test
image only through the operator's manual SD-card procedure.

## Limits of this feature and acceptance

This adds **a working local source route**, not proof that your
specific Edifier R600USB is connected, audible, balanced left/right
or that a two-Bluetooth-plus-LAN stream is compatible. PipeWire sink
existence alone does not prove playback. Test at safe volume with
a locally approved WAV, and record what you actually heard privately.
No audio files, telemetry, owner data or licensed third-party music
are bundled. Use only media that you have rights to play.

Production release still requires Pi4/Edifier bench acceptance,
source-rights and nine rootfs copyright notice reviews, secure
phone ownership onboarding, long-term package archival, and
explicit operator/CEO release authorization.

## Guided music-folder browser and track selection

You no longer need to type every individual WAV filename. On the
already-authorized **local** Pi4 terminal, open a small, private folder
of owned/licensed WAV tracks. The folder must be an absolute real
directory and must not be group/world writable. Subfolders, symbolic
links, hidden files and unsupported formats are not traversed. At most
256 immediate folder entries are inspected, and the tool displays at
most 40 valid tracks. This avoids unbounded scans and never silently
plays an arbitrary whole directory.

**1. Browse without sound or network calls:**

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --library /home/audiohub/PrivateMusic

Track numbers, durations, mono/stereo and sample rates are shown.
**Private filenames are hidden by default.** An operator who is
physically alone at a trusted local Pi console can explicitly add
`--show-titles` to show sanitized short local titles. That option
may reveal personal titles in a terminal history or transcript and
should not be used while recording/sharing the terminal.

**2. Preview selected tracks in a chosen order** (e.g. second then first):

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --library /home/audiohub/PrivateMusic --tracks 2,1

Preview validates the selected tracks' total duration and file format.
It never opens PipeWire, plays audio or saves a playlist. At most eight
distinct numbered tracks can be selected per session.

**3. Start only after the operator verifies a safe speaker volume:**

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --library /home/audiohub/PrivateMusic --tracks 2,1 \
      --minutes 10 --play

Both `--tracks` and `--play` are mandatory when browsing a folder.
The queue follows the explicitly selected order. The existing
unprivileged `audiohub.music` sink, safe initial stream level,
audio-format validation, timeout and **Ctrl+C** cancellation are
unchanged. The PipeWire process explicitly receives `--raw --format=s16`
so streamed PCM bytes from stdin are decoded as samples rather than
mistaken for a WAV/container header. It never opens a public playlist API, persists the queue or
modifies Wi-Fi, Bluetooth pairing, mixer EQ or access controls.

If an album has more than 40 playable WAVs or 256 directory entries,
split it into smaller, separately operator-controlled folders. An
invalid/linked WAV is skipped without revealing its filename; if all
tracks are invalid, the browse action fails safely. The numbered
selection is local and must be repeated for each subsequent session.
Previously supported explicit individual-WAV commands continue to
work unchanged.

**Rollback:** press Ctrl+C or close the local terminal session; any
player started by this command is stopped. No playlist files, service
settings or source permissions have been written. Physical Pi4/Edifier
audio remains unverified until an operator hears it on the speakers.

## Manual live track controls (new Pi4 local-terminal ALPHA)

To control the **current explicitly selected local playlist** without
restarting AudioHub, add BOTH `--play` AND `--interactive`. Neither
option alone allows interactive playback:

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --library /home/audiohub/PrivateMusic --tracks 2,1 \
      --minutes 10 --play --interactive

The command needs a real operator-controlled **stdin AND stdout TTY**
and must run as the unprivileged audiohub PipeWire user. Do not open a
network-exposed shell or use an automation to start it. The selected
library files are previewed and strictly validated as before; the
session only starts after the operator explicitly includes `--play`.

During playback, type a command and press **Enter**:

| Command | Action |
|---|---|
| `u` + Enter | Pause or resume only this music session's owned player; session time limit keeps running |
| `s` + Enter | Show current track number, elapsed session time and remaining session limit; no filenames or user identifiers |
| `l` + Enter | Show anonymous selected queue order and planned WAV lengths (not live playback progress) |
| `n` + Enter | Stop just the current owned player, then start the next selected track in order |
| `p` + Enter | Stop the current player and go to the previous selected track; on track 1, restart track 1 |
| `r` + Enter | Restart the current selected track from its beginning |
| `1`–`8` + Enter | Jump directly to an existing numbered track in the selected queue (invalid positions do not interrupt playback) |
| `q` + Enter | Stop the current owned player and exit the session |
| `h` + Enter | Repeat the short help text |
| Ctrl+C | Emergency local interruption; owned child stopped in cleanup |

The track is displayed only as `track X/Y`, with no private title or
file path. The status is **session elapsed time** rather than exact PCM
playback position or proof of audible sound. Files stay on the Pi4;
there is no playlist file, public HTTP/IPC control endpoint, cloud,
Bluetooth adjustment or change to PipeWire's existing music sink.
Each child is only owned by this local invocation. If the audio tool
blocks, stop signals also terminate only its owned child, never the
global PipeWire service, another user session or another input.

An older direct-files invocation works as well:

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --minutes 5 --play --interactive /absolute/private/one.wav \
      /absolute/private/two.wav

**Stop and rollback:** type `q` + Enter, press Ctrl+C or close the
local controlling terminal. The interactive mode exits when the input
terminal disconnects or its session duration is exceeded. No saved
settings or permissions exist to revert. The session refuses to run
non-interactively (no stdin/stdout TTY), as root, or without an actual
`audiohub.music` target. A native Pi4 test image containing this
increment is required; the older image with just folder browsing does
not contain these controls. No physical Edifier volume, stereo or
multi-source mixing has yet been certified.

### Private navigation and repeat behavior

The queue is limited to eight files that the operator selected explicitly
before playing. During an active session, `l` shows only ordered numbers
and WAV-header-derived planned durations (e.g. `2*=03:15` marks the
selected queue position); these are NOT hardware playback timestamps.
Private local file paths and titles remain hidden even while navigating.
The `p` and `r` commands stop only the owned current player and
start a fresh validated copy of the requested track, respecting the
same original session deadline. They never bypass the configured
maximum session runtime or create an automatic repeat loop.
Direct numeric jumps are constrained to the selected queue's size.
A failed or out-of-range request does not move the playback position.
As before, `q` or Ctrl+C safely stops playback; no settings, files,
network endpoints, keys or device permissions are changed. This needs
a native Pi4 test image that actually includes the new module version.

### Pause and resume an explicitly started local WAV track

After intentionally starting a Pi4 terminal session with
`--play --interactive`, press **`u` + Enter** to request a pause
and **`u` + Enter** again to continue. Only the `pw-cat` child
that this exact local terminal session launched receives SIGSTOP or
SIGCONT. PipeWire's system services, other user sessions, USB/BT
audio inputs and global routing are never paused or reconfigured.
Use `s` to show the anonymous **PAUSED** status.

This is not a certified instant speaker mute: PCM frames already
buffered downstream may be heard briefly. The original absolute
session limit continues during pauses. Pressing `q`, skipping,
replaying, jumping, Ctrl+C or reaching the time limit resumes an
otherwise stopped subprocess **before** terminating that owned
process. Neither a music player daemon nor a file-based state is
left running, and there are no settings to roll back. If a pause
signal cannot be applied, the operator sees a generic message
without a file path or command error details.

Real Pi4/Edifier audio pause, stop, source isolation and safe output
level require a low-volume physical bench test. The controls are
unverified operator alpha software, not a speaker acceptance or
owner-authenticated phone controller.

## One-command guided local album selection (Pi4 operator alpha)

You can now choose a local album **without remembering several flags**.
At the already-authorized **physical Pi4 terminal**, run as the
unprivileged audiohub user:

    PYTHONPATH=/opt/audiohub/src python3 -m audiohub.local_music \
      --guided --library /home/audiohub/PrivateMusic --minutes 10

The command first lists at most 40 valid WAV tracks by **number,
duration and audio format**. Private filenames are hidden by default.
The music folder must be a real, non-symlinked, absolute, privately
controlled directory as in the existing library command.

The tool then asks for **up to 8 distinct track numbers** in playback
order (for example `2,1,4`). Alternatively enter **`ALL`** to include
every track in a small folder containing at most eight valid WAVs, or
**`SHUFFLE`** to select up to eight randomly ordered tracks from the
listed folder that fit the selected session duration. SHUFFLE runs only
in memory, never creates a playlist file, and leaves the chosen library
numbers visible for review (not private filenames). Files that would
exceed the remaining session budget are excluded; a shuffle that fits
nothing is refused. Pressing Enter without a selection
cancels without sound. Invalid selections can be corrected twice; three
invalid attempts cancel. No file, playlist or operator responses are
stored or sent over a network.

After a valid selection the tool shows the *chosen library numbers*
and total planned duration. At the same confirmation prompt,
**`CHANGE`** returns to the numbered selection (at most twice) so the
operator can correct a mistaken or unwanted shuffle before any sound.
Only **exact uppercase `PLAY`** starts the existing interactive player. Any different
answer, EOF or a missing terminal cancels without starting the player.
Only after `PLAY` does the existing local interactive controller start,
with `u` pause/resume, `s` status, `n` next, `p` previous, `r` replay,
`l` queue overview, `1`–`8` direct jump and `q` stop. Press Ctrl+C
for local interruption. Session duration continues to be limited even
while paused; low physical speaker volume is required on first test.

Use `--show-titles` only if you explicitly want sanitized filenames
visible at a trusted private terminal; terminal transcripts may reveal
them. The guided command is deliberately incompatible with `--play`,
`--interactive`, `--tracks` or direct WAV arguments, because it owns
the entire preview→selection→human confirmation→play sequence. The
existing direct-file and `--library --tracks --play` commands continue
to behave as before.

**Operator test and rollback:** The new UI exists in the unverified
Pi4 ARM64 alpha built from its exact source commit, not older images.
After separate permission, flash a spare SD (keep the previous
working SD). Test preview and cancel first, then controlled PLAY at
low speaker volume, test pause and quit, and return to old SD if
necessary. No settings are written by this wizard and neither real
Edifier sound nor owner authentication is inferred from software tests.

## Installed on-device music command (Pi4 operator alpha)

After separately approving and flashing the **unverified** ARM64 test
image to a spare SD card, sign in at a physically trusted Pi4 terminal
as the existing **unprivileged `audiohub` user**. The new image ships an
empty, private 0700 folder at `/home/audiohub/PrivateMusic` for the
operator's own legally playable PCM16 WAV files. Import files into this
folder through an already-authorized local/manual process. No Wi-Fi,
SSH, phone owner-claim or media synchronization is enabled by this feature.

The short command is now:

```sh
audiohub-music
```

For on-device instructions use `audiohub-music --help`. To select an
alternative *absolute* operator-controlled folder use
`audiohub-music /absolute/private/music`. Paths are passed to the
existing bounded local WAV library validation, never evaluated by a
shell or written to a playlist. Relative paths and additional flags are
rejected. The original advanced Python CLI and custom `--minutes`
option remain available for operators needing a nondefault session
limit; the short launcher uses a **15-minute** limit.

The guided wizard lists a bounded, anonymous set of tracks and accepts
numbers, `ALL`, or a short random `SHUFFLE`. It lets the operator
`CHANGE` the numbered order before the exact-uppercase **`PLAY`**
confirmation. No sound begins just by launching the command. During
an explicitly started session use `u` to pause/resume, `n` next,
`p` previous, `r` replay, `l` view queue, `q` quit and Ctrl+C stop.
The original time limit, fixed private PipeWire music sink and low
initial stream gain remain unchanged.

**Operator installation and update boundary:** This is a built-in
command inside a new image, **not** an in-place system updater. For a
manual operator test, check the outer artifact and inner image SHA256,
flash a *separate* SD card after explicit authorization, and boot an
isolated Pi4 with low physical Edifier speaker volume. Your old working
SD card must be kept intact as rollback. Keep separately provided WAV
files on media you control and do not assume that switching SD cards
preserves files stored on the previous card: copy/back up any operator
media separately before an image update. Never overwrite the working
SD card or change Bluetooth, Wi-Fi, keys or permissions automatically.

The build itself executes `audiohub-music --help` in the actual ARM64
chroot under the unprivileged user; the rootfs gate checks the command
and the private folder in the staged image. Neither check proves actual
Pi4 boot, audible Edifier stereo, owner onboarding or a production GO.

## Live repeat controls for an active local music session

After a private WAV selection is reviewed and the operator enters the
**exact uppercase `PLAY`** confirmation, press `m` plus Enter to cycle:

- **OFF** — normal one-pass album playback (default for every new run).
- **TRACK** — repeat only the currently selected track on natural completion.
- **ALL** — play the selected queue again from track one after the last track.

Press `m` repeatedly to return to OFF. `s` (status) and `l` (queue)
show the active repeat mode without private titles or file paths.
Manual `n` advances to the next track even in TRACK mode; `p`,
`r`, numbered jump, `u` pause/resume and `q` or Ctrl+C stop remain.
**Repeat never resets or extends the original session time limit**;
repeating stops automatically when that deadline is reached, including
when a track is paused. The operator need not change any mixer, network
or credentials. This is volatile terminal-only state: no new service,
local file write, playlist persistence or automatic playback at boot.

For a safe physical test: first use `audiohub-music --help`, select
licensed owner WAV files and verify that cancellation before `PLAY`
is silent. At low Edifier speaker volume confirm `PLAY`, then `m`
to select TRACK and ALL, observe actual transitions, use `s` and `l`,
and stop with `q`. Actual audible behavior and device support remain
unverified until the operator records them on real Pi4 hardware.

## Manual WAV backup and restoration before a Pi4 SD swap

**This is a specific, opt-in media copy tool, not a system update or
an automatic or full-device backup.** The operator must already have a
legitimate unprivileged terminal login. The Pi4 test image installs
`audiohub-music-transfer`. It does not mount USB storage, create
users, grant access, change credentials, expose files over Wi-Fi or
synchronize anything in the background.

Before flashing any new SD, retain the known-good old SD and prepare
a *different, operator-controlled* storage device, mounted through your
normal authorized procedure. Create an **already existing private
directory** on that device, **owned by the same unprivileged operator**
and restricted to **0700**. Directory components cannot be symlinks.
Both the on-device `/home/audiohub/PrivateMusic` and backup location
must be private. Run at the Pi terminal:

```sh
audiohub-music-transfer --help
audiohub-music-transfer backup /absolute/private/external-folder
```

The CLI previews a count and total size without filenames and writes
nothing until you type **exactly `COPY`** on its separate prompt.
It handles up to 40 valid PCM16 WAV files and at most 512 MiB. It
refuses unsafe/unsupported WAVs, symbolic links, hardlinked source
files, permission problems, insufficient space, collisions and files
changed during copying. The tool does **not** copy non-WAV items,
settings, access credentials, Bluetooth pairing data or any other
files; do not confuse a successful WAV copy with a complete backup.

Successful file copies are published with the original name only
after contents are checked; each new file is mode 0600. Existing files
are never replaced, moved, renamed, reset or deleted. Source files
are left untouched. A power interruption or storage failure may leave
**some previously completed new destination WAVs** or private temporary
partials; no multi-file all-or-nothing guarantee is made. Check the
count, retain the old SD and remove any orphaned operator-owned
temporary file only through a separately authorized manual process.

After verifying the new image's outer artifact ZIP and compressed SD
image hashes, separately approving the swap, and successfully booting
the spare SD, remount the *same* independent music backup and run:

```sh
audiohub-music-transfer restore /absolute/private/external-folder
```

Review count and size and type `COPY` to import into the existing
**empty** `/home/audiohub/PrivateMusic` directory; if names already
exist the utility refuses to overwrite. Compare the reported private
order/content fingerprint between backup and restore, verify original
WAVs still exist on external media, and run `audiohub-music` to test
actual playback at low physical Edifier volume. If anything fails,
stop; keep both the original SD and external media for rollback.
This tool does not replace the secure owner-claim process and cannot
prove Pi4 speaker sound or grant a production release.

### First migration from PR #258 or older (no transfer CLI on old SD)

The **old** SD image does not contain `audiohub-music-transfer`; the
`backup` example above works only once a newer image with this
command is already running. For the first replacement, there is a
safer source-preserving alternative: keep the previous SD unmodified,
flash the new *separate* test SD only after approval, boot it, and
attach the original SD using a separately authorized USB SD reader.
The operator mounts the old filesystem **read-only** without changing
credentials, ownership or access modes. Identify the actual absolute
mount path for the previous `home/audiohub/PrivateMusic` directory.
If that folder is owner-private and maps to the same unprivileged UID,
use the **new** image's terminal command:

```sh
audiohub-music-transfer restore /absolute/old-SD/home/audiohub/PrivateMusic
```

Review the WAV count and bytes; enter exact uppercase `COPY` only
when the new private destination contains no same-name WAVs. The
source filesystem may be read-only (the tool only reads it). The
import is non-overwriting and will stop on unsafe paths, mismatched
owner UIDs or unsupported files. It does not mount a disk itself or
write into the previous SD. If the source cannot be made available
read-only and privately with ordinary authorized operator access,
stop; do not automatically remount it writable, change permissions,
reset credentials or attempt a privileged workaround. Retain both
SD cards as rollback until real Edifier playback is verified.

### Interrupted transfer recovery and read-only verification (PR #260)

Normal backup and restore still refuse any existing destination filename.
After an interrupted copy, use an explicit **resume** on the same
trusted, unprivileged local terminal and previously mounted private media:

    audiohub-music-transfer backup /absolute/private/external-folder --resume
    audiohub-music-transfer restore /absolute/private/external-folder --resume

Resume hashes **both** sides of every existing same-name WAV before any
new copy. Existing copies must be regular, same-owner, single-link,
private (0600) and identical byte-for-byte. Any unsafe, changed or
differing file refuses the entire operation **before any new copy**.
Identical WAVs are skipped, missing WAVs still need the exact uppercase
COPY confirmation. When all WAVs match, no copy or confirmation is needed.
This resumes a multi-file operation, not a partially written individual file.

Verify source WAVs against the destination without writing anything:

    audiohub-music-transfer verify-backup /absolute/private/external-folder
    audiohub-music-transfer verify-restore /absolute/private/external-folder

verify-backup reads local music as source; verify-restore reads external
storage as source. Both require a local non-root TTY and owner-private
folders, but neither asks for COPY. Every supported source WAV must
exist unchanged at the destination with matching SHA256 and safe metadata.
An empty source set or a missing, unsafe or different WAV refuses success.
Extra destination files are NOT examined as a mirror guarantee; nothing
is deleted, renamed or overwritten. Private names are not printed.

These actions do **not** migrate Wi-Fi, owner identity, Bluetooth trust,
EQ settings, other personal files, operating system or device permissions.
Keep the old SD and independent media intact; a failed copy can retain
earlier completed new files. Operator SD swap and physical Edifier
hardware acceptance are separately approved, not performed by the tool.

## Save music when the original SD has no transfer command

When upgrading from an old Pi4 SD that predates the WAV transfer
utility, start the separately approved **new test SD** and attach
the **original SD read-only**. After the operator independently
mounts the old SD and confirms same UID/private directories, the
new image's existing installed WAV launcher supports:

    audiohub-music-transfer backup-old /absolute/old-SD/home/audiohub/PrivateMusic /absolute/private/archive
    audiohub-music-transfer verify-backup-old /absolute/old-SD/home/audiohub/PrivateMusic /absolute/private/archive

The former requires `COPY` before exclusive new verified files; the
latter is read-only. Interrupted copies use `backup-old OLD_MUSIC
ARCHIVE --resume` with SHA256 comparison and no overwrite. The
unprivileged command does not need any code or executable on the
old SD and never mounts, alters or formats either card. Transfer
excludes identities, Bluetooth, Wi-Fi, music license grants and EQ.
For combined sound preset + WAV verification before and after an
SD change, see [the private SD update guide](PRESET-TRANSFER.md).

## Easier Pi4 operator music launcher: list, time limit and quieter playback

The **existing installed** Pi4 command now supports optional bounded
parameters without changing the underlying private music player or
starting any new service:

    audiohub-music --list
    audiohub-music /home/audiohub/PrivateMusic --list
    audiohub-music --minutes 10 --level quiet
    audiohub-music /home/audiohub/PrivateMusic --minutes 5 --level soft
    audiohub-music --show-titles --list

**Read-only library check:** `--list` displays the same bounded anonymous
local track numbers, WAV duration, channels and sample rate as the
existing picker, but **never** opens PipeWire, plays sound, writes
playlists or requires an interactive prompt. This helps the operator
confirm that WAVs are readable on a freshly installed test SD before
physical audio testing. It refuses an empty or unsafe library, rather
than giving a misleading green result. Filenames stay hidden unless
`--show-titles` is separately specified; this explicit choice displays
sanitized titles on the local screen and should not be used in a shared
terminal transcript.

**Bounded session:** `--minutes N` selects an integer from 1 through
30 (default remains 15). It controls both the allowed library selection
duration and the original wall-clock session deadline. It does not
allow infinite autoplay, increase the maximum 8-track selection or
bypass the existing exact **PLAY** terminal confirmation.

**Private stream level:** `--level quiet|soft|normal` chooses an
allowlisted per-owned-player `pw-cat --volume` gain: quiet=0.05,
soft=0.10, normal=0.20 (default unchanged). Lower-than-normal levels
can be selected **before** the separate PLAY confirmation; the
operator reviews the choice with the selected track count and session
time, and the same choice persists on skip, replay and repeat for
this single terminal session only. No arbitrary numeric values above
normal are accepted. These are relative digital stream gains, **NOT
calibrated physical sound pressure**, so keep the amplifier/speaker
hardware at a safe low volume for first testing. They never modify
the global PipeWire gain, other mixer inputs, EQ, mute, owner pairing,
Bluetooth/Wi-Fi, default output, device ACLs or persisted settings.

The launcher accepts at most one private absolute WAV folder,
one `--minutes` and one `--level`, with no `--play` shortcut,
automatic scheduled music, network listener or elevated rights. The
same unprivileged Pi console and explicit **PLAY** requirement remain.
Stop with `q` + Enter or Ctrl+C; no changes to undo. Test status
remains UNVERIFIED_ALPHA_TEST_ONLY until actual Pi4 speaker/hardware
acceptance.

## Non-playing Pi4 music readiness before the first speaker test

On an already authorized spare Pi4 SD, run as the unprivileged local audiohub user:

    audiohub-music --check
    audiohub-music /home/audiohub/PrivateMusic --check

This **read-only** check independently reports three prerequisites,
without streaming sound or changing the device.

- WAV library: uses the same bounded private-folder inspection as
  `--list`; shows only supported WAV counts and redacted corrective
  guidance if the folder is empty, inaccessible or unsuitable
- Private music input: a bounded PipeWire graph query checks the exact
  `audiohub.music` sink; missing input does not trigger any fallback to
  default hardware, nor a service restart
- Local playback tool: checks that the ordinary `pw-cat` program exists
  in the current user's command search path, without executing it

If all three prerequisites appear present, exit status is 0 and the
message reads **READY FOR MANUAL PLAY TEST**. Missing prerequisites
cause exit status 2; all three are assessed independently. No private
WAV titles, paths, device IDs or raw errors are printed. The command
never plays sound, writes a playlist, opens an HTTP API, changes EQ,
routes, levels, ownership, Bluetooth/Wi-Fi, or performs SD operations.
For clarity, `--check` cannot be combined with `--list`,
`--show-titles`, `--minutes`, `--level` or playback flags.

A passing result is **not** evidence of actual audible USB/Edifier
sound, speaker SPL, left/right balance, two Bluetooth-plus-LAN mixing,
24-hour stability or authenticated first-owner setup. It is only a
point-in-time prerequisite check. The audio graph can change after
the inspection. After separate operator authorization, keep speaker
hardware volume low, use `audiohub-music --minutes 5 --level quiet`,
then explicitly type **PLAY** on the local terminal. Stop with
`q` + Enter or Ctrl+C. Preserve the original SD and private backups
for separately operator-approved physical rollback.

## Local left/right stereo isolation in the existing Pi4 music player

On an authorized *spare* Pi4 test SD, with the physical speaker
volume kept low, the operator can choose:

    audiohub-music --minutes 5 --level quiet --channel left
    audiohub-music --minutes 5 --level quiet --channel right
    audiohub-music --minutes 5 --level quiet --channel both

Default is both. LEFT mutes only the RIGHT side of the stereo WAV in
bounded decoded PCM16 chunks in memory; RIGHT mutes only LEFT.
The requested sample bytes are preserved exactly, both stream channels
remain stereo, the original WAV on disk is untouched and there is no
amplification or PipeWire output rerouting. The selection applies only
to this local music session, persists through track skip/replay/repeat
and is never saved. Mono content cannot be played in one-sided mode;
the picker refuses such selection before PLAY. --check and --list
remain strictly non-playing and do not accept --channel.

Before any playback, the trusted local Pi4 terminal shows the chosen
channel and selected tracks, and requires a separate exact uppercase
PLAY. This does not alter other mixer inputs, global PipeWire levels,
EQ, mute, wireless/phone owner pairing, device permissions, or services.
No action mounts/formats/flashes either SD card.

To investigate actual speaker stereo, use an operator-supplied,
licensed stereo WAV with known left/right content. Separately listen
at a very low physical amplifier volume for LEFT, RIGHT and BOTH
after explicit operator authorization; stop using q + Enter or
Ctrl+C each time. Record what speakers truly produce. No automatic
hardware PASS is inferred: source-channel isolation is NOT proof of
the physical Edifier USB output, correct wiring, SPL, multi-source
Bluetooth/LAN mixing, 24-hour stability or production readiness.
Keep the original SD and external WAV/setting archive for a separate
manual physical rollback after operator decision.

## First sound without importing any WAV: original built-in stereo sample

The installed Pi4 operator can run the following command **without**
first copying, downloading or restoring any private music files:

    audiohub-music --speaker-test

This produces a new original, deterministic **2.1-second** sound
sample entirely in bounded RAM chunks: 0.5 seconds at 440 Hz in LEFT,
0.2 seconds silence; then RIGHT and BOTH, each followed by the same
silence. The signal is PCM16 stereo 48 kHz with a short fade-in/out.
The peak is capped at 655/32767 (about 2% digital PCM full-scale), and
the existing privately owned playback subprocess is forced to the
already-supported quiet stream gain of **0.05** and the exact
audiohub.music PipeWire target. This is intentionally a short, modest
digital diagnostic, NOT calibrated sound pressure or a guarantee of
hearing-safe analog loudness. Set the **physical** speaker/amplifier
volume low before considering a test.

The command is **exclusive**: no directory, WAV, --minutes, --level,
--channel, --check, --list, --play, service or network option can be
combined with it. It requires the existing non-root local Pi4 terminal
on both input and output, then prints the fixed pattern and safety
warning. Nothing is sent to PipeWire until a human separately types
the exact uppercase `PLAY` and Enter. Any other input, lost TTY,
missing private sink, blocked child or reached 8-second deadline
refuses or stops safely. It never starts a background service or
changes the global mixer, EQ, mutes, other source gains, Bluetooth,
Wi-Fi, owner credentials, output routing or files.

This feature removes the need to supply a licensed WAV merely to
attempt the **first physical speaker test**. Unlike the WAV library
preflight, the built-in test can work with an empty PrivateMusic folder.
It does not bypass hardware setup. With operator authorization, boot a
separate spare Pi4 SD, keep the original SD untouched, confirm that
the output amplifier is low, and listen to the 3 ordered segments.
If the first segment is inaudible, do not assume a software or hardware
PASS. Record whether LEFT, RIGHT and BOTH actually emerge from the
expected physical speakers and stop immediately if unexpected. Only
the operator can validate stereo/Edifier output, SPL, USB routing,
2BT+LAN mixing or 24-hour stability. Rollback is manual reinsertion
of the original SD after operator decision. This is an
UNVERIFIED_ALPHA_TEST_ONLY feature, not a production release.

## Repeat a single original speaker side without importing a WAV

If the first 2.1-second pattern is too brief to identify a speaker,
use the existing local diagnostic with a strictly predefined channel:

    audiohub-music --speaker-test left
    audiohub-music --speaker-test right
    audiohub-music --speaker-test both

The old no-argument command still plays LEFT, RIGHT, BOTH in order.
A selected mode plays three separate 0.5-second pulses of that one
channel, each followed by 0.2 seconds of silence. Each invocation
lasts 2.1 seconds, is generated only in bounded RAM (no private
music files), and uses the same original PCM16 peak <=655/32767
and fixed quiet PipeWire stream gain 0.05. The opposite channel
is silent; there is no boost, output reassignment or EQ change.

Every single invocation, including repeating the same side, needs
a new exact uppercase PLAY confirmation on the trusted unprivileged
local Pi4 terminal. No folders, --play, --level, --minutes, --check,
--list or other flags can be combined with this command. Invalid
channel names fail closed without playing sound.

Keep the physical Edifier amplifier volume LOW. If a channel is
inaudible, do not assume a hardware PASS or blindly raise speaker
SPL. Record actual LEFT/RIGHT/BOTH physical speaker observations
using a separately approved spare SD. No successful software test
certifies the analog output, two-Bluetooth-plus-LAN mixing,
24-hour stability, Wi-Fi owner pairing or production. The original
SD is retained for separate manual rollback; no SD operation or
persistent test result is triggered by this command.

## Guided first stereo observations, without any WAV file

On a separately authorized **spare Pi4 test SD**, use the existing
unprivileged local console (not root) and keep the physical Edifier
amplifier volume low:

    audiohub-music --speaker-guide

The guide now **automatically performs the same read-only first-sound
preflight as** `audiohub-music --speaker-check`, before even asking for
the first PLAY. It checks the exact private PipeWire `audiohub.music`
input and the local `pw-cat` tool. If either prerequisite is missing,
the guide explains which one needs attention and **ends without
prompting for PLAY or starting any sound**, never falling back to the
system-wide default output. This happens for the full guide and
targeted channel rechecks alike. No WAV files are inspected, even
on an empty new SD; successful preflight only means READY FOR MANUAL
TRY, **not** that real speaker sound was independently verified.
The standalone `--speaker-check` remains useful when the operator
wants a completely non-playing check outside a trusted TTY.

If an initial test shows a damaged/right-channel cable and you correct
it, you can **recheck just that physical side** without repeating the
other sound tests:

    audiohub-music --speaker-guide right
    audiohub-music --speaker-guide left
    audiohub-music --speaker-guide both

These are three **independent examples**, not a script to run all of
them in a row. The optional lowercase selector means **only** that
particular physical speaker, or **both physical speakers together**;
it does NOT authorize any playback automatically. Each targeted
attempt separately prompts for an exact uppercase PLAY then a physical
CORRECT/WRONG/SILENT/UNSURE observation; after a fault RETRY is still
limited to one new fresh-PLAY attempt, otherwise STOP safely exits.
Only the selected channel is reported and all other channels remain
UNTESTED. An affirmative targeted self-report does **not** assert
that full LEFT/RIGHT/BOTH stereo routing or physical hardware works.
Unknown sides, extra args, non-local TTY, root or cancellation fail
without sound.

The default guide runs the existing deterministic 2.1-second original 440 Hz
sample in three **separate** steps: LEFT-only, RIGHT-only, BOTH.
Each step explains exactly what physical speaker(s) should be heard
and requires a **new exact uppercase PLAY and Enter** on the trusted
local terminal. The previous command's consent never carries forward.
After each stream, enter **CORRECT**, **WRONG**, **SILENT** or **UNSURE**
in uppercase plus Enter based only on what was actually heard.
Only **CORRECT** advances to the next channel. Any WRONG, SILENT or
UNSURE stops automatic progression and suggests inspecting the physical
USB/Edifier connections at a safely low amplifier volume. You can
enter exact **RETRY** to test that same side **once more**; even then
the playback demands another separate uppercase **PLAY**. Or enter
exact **STOP** to end the guide without playing further channels.
After two attempts at an unresolved side, the guide stops automatically.
Unknown retry responses, end-of-input, Ctrl+C or cancelled PLAY also
stop; neither feedback nor retries grant automatic playback.

The guide summarizes **only the operator's reported observations**.
If playback or feedback is cancelled with STOP, EOF, Ctrl+C or an
unknown answer, the local terminal **still prints the observations
already supplied**, marks a reached-but-unanswered channel
**NO REPORT**, and marks remaining channels **NOT TESTED**. Do not
confuse these statuses. When a WRONG/SILENT/UNSURE answer is followed
by an explicit RETRY and later CORRECT, the summary retains the full
sequence (e.g. `RIGHT reported attempts: SILENT -> CORRECT`).
Such a recovery is not presented as a clean first-attempt hardware
success. No audio is replayed merely to generate the summary.

All feedback remains temporary and terminal-local, never saved to
SD, uploaded, exposed to any remote interface, or treated as
independent hardware certification. Never
raise physical speaker volume or change other source routing
automatically to diagnose a silent or reversed side.

There is **no automatic hardware PASS** even if every step is reported
CORRECT. Output routing, safe analog loudness/SPL, Edifier hardware,
simultaneous two-Bluetooth-plus-LAN mixing, owner pairing and 24-hour
stability remain unverified. The guide only uses the existing private
`audiohub.music` sink, fixed low PCM peak and 0.05 quiet per-player
gain, no default-sound fallback, and the existing bounded process
cleanup; it writes no WAV, configuration, logs, pairing, network state
or other source settings. No music library, internet or licensed
media file is needed.

The command is exclusive: extra flags, folders or WAVs are rejected.
To cancel, do not enter PLAY; existing manual rollback is reinserting
the untouched original SD **only after separate operator approval**.

## Check whether the first built-in sound can be tried (no WAV)

A **new independent read-only** preflight is available on the native
Pi4 operator TEST image **without adding any personal WAV files**:

    audiohub-music --speaker-check

Unlike the older `audiohub-music --check`, which checks whether a
private WAV library is ready for music playback, `--speaker-check`
intentionally does **not inspect the library at all**. An empty
`/home/audiohub/PrivateMusic` does not count as a first-sound failure.

The check reads two bounded local prerequisites independently:
the exact private `audiohub.music` PipeWire sink and whether the
unprivileged operator can locate `pw-cat`. Each missing prerequisite
receives an actionable, non-identifying explanation. A green
**READY FOR MANUAL TRY** means only that these two prerequisites appear
present: it does NOT play a sound or prove the USB output, left/right
routing, physical SPL, speaker wiring, multi-source mixing, first-owner
security or production suitability. The graph may change after the
check. Failure returns exit status 2; readiness returns 0.

Only after explicit permission for an isolated spare-SD hardware test
and with the physical Edifier volume set LOW, the human operator
can run:

    audiohub-music --speaker-guide

Each audible step still requires an independent uppercase **PLAY** and
physical observation. Unexpected output stops automatic progression
with bounded same-channel RETRY or STOP. The check neither prompts PLAY
nor invokes the player, opens WAV files, writes a log, changes the
global mixer/EQ/routing/owner/BT/Wi-Fi/services, or uses default-output
fallback. It refuses extra options and root. No files or settings need
rollback; use the old untouched SD if the operator separately approves
a hardware rollback.
