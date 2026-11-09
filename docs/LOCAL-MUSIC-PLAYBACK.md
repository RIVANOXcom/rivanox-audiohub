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
unchanged. It never opens a public playlist API, persists the queue or
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
