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
