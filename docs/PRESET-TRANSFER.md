# Offline private audio preset transfer between Pi4 SD cards

**UNVERIFIED_ALPHA_TEST_ONLY.** This utility transfers only three saved
three-band EQ curves and up to eight **inactive** user-created volume
profiles. It never copies mixer master/current levels or mutes, any source
routes, Bluetooth identities, pairing trust, owner keys, credentials,
phone Wi-Fi, certificates, device IDs, OS configuration, or user music.

## Prerequisites and safety boundary

Use only an **already-authorized local Pi4 terminal** as the unprivileged
`audiohub` account. This command is not a headless owner claim solution.
Use separate operator-approved media, with an existing absolute private
directory owned by this UID (0700, or 0500 for read-only source).
No directory component may be a symbolic link. **No automatic mount,
privilege escalation, network service or SD flashing** is performed.

The output is a single private, mode 0600 file named
`audiohub-presets.json`. Export is exclusively created, never
overwritten, after exact uppercase `SAVE` confirmation. A SHA256 of
this archive is printed. Keep original SD and other backups untouched.

### From an existing image that includes this command

    audiohub-presets-transfer --help
    audiohub-presets-transfer export /absolute/external/private-folder

### First migration from an old SD that has no transfer command

After **separately approved** flashing and startup of a NEW test SD,
connect the original SD using an operator-authorized reader. Mount the
OLD file system **read-only**, without changing ownership, permissions
or credentials. Confirm the actual absolute path to its old
`home/audiohub/.config/audiohub` folder and that its owner UID maps
to the unprivileged audiohub UID. Run from the NEW image:

    audiohub-presets-transfer export-old /absolute/old-SD/home/audiohub/.config/audiohub /absolute/external/private-folder

Only the old `settings.json` and `volume-profiles.json` are read as
input, strictly validated with the existing AudioHub mixer schema. An
absent or unsafe old config, different UID, symbolic link, invalid
value or missing private external folder fails closed. The original
SD is never changed. Never remount it writable to bypass a refusal.

On the new test SD, with the private archive retained separately:

    audiohub-presets-transfer inspect /absolute/external/private-folder
    audiohub-presets-transfer restore-profiles /absolute/external/private-folder
    audiohub-presets-transfer restore-eq /absolute/external/private-folder
    audiohub-presets-transfer verify /absolute/external/private-folder

`inspect` validates the archive and reports only three source EQ
slots, saved profile counts and EQ difference counts; it never prints
profile names or file paths. `restore-profiles` requires exact
`RESTORE` confirmation and creates a new protected profile catalog
**only if one does not exist**. These profiles are not applied to
master/input volumes, mutes or playback. An existing catalog is never
replaced, even if empty; inspect any conflict using the normal local
profile commands rather than manually bypassing protections.

`restore-eq` requires exact `APPLY-EQ` confirmation for any
differences. It only writes saved bass/mid/treble values through the
existing locked revision-guarded mixer writer; all requested
master/individual volumes and mutes remain unchanged. **Non-neutral
existing EQ is never overwritten.** Equal saved EQ makes no write.
The utility does **not** update running PipeWire EQ filters. If the
operator decides to stage a stored EQ for a later controlled session,
use the existing separate `python3 -m audiohub.eq_setup --preview-saved`
and explicit `--stage-saved --if-preview-revision REV
--confirm-local-eq-stage` workflow. Stage is not a live EQ update;
restart and actual sound testing remain separately authorized.

`verify` is read-only: it checks saved three-band EQ plus the exact
inactive profile catalog match the private archive. A successful
verification does **not** prove audible sound, hardware connectivity,
headroom, clipping/limiting or unchanged active PipeWire graph.
Any missing archive, unsafe file, conflicting profile catalog or
concurrently edited mixer settings refuses verification. No file
is silently deleted or overwritten. A power failure can leave a
new private temporary file; manual operator inspection is required.

**Update/rollback:** preserve the old SD and the private archive.
If migration or hardware playback fails, stop the user session and
restore the old SD only through the authorized manual operator
procedure. A new image must not overwrite old media or automatically
transfer authentication, pairing or secrets. Production release
remains NO-GO pending physical Pi4/Edifier stereo, 2 BT + LAN and
24-hour tests, secure ownership, legal review, durable source/image
storage and explicit owner/CEO acceptance.

## Preserve profiles already configured on the replacement SD

The original `restore-profiles` remains **strict**: it refuses any
existing local profile catalog. This protects a freshly configured
replacement SD, but can block a migration when it already contains
user-created profiles. Use the separately reviewed **merge** path:

    audiohub-presets-transfer plan-profiles /absolute/external/private-folder
    audiohub-presets-transfer merge-profiles /absolute/external/private-folder

`plan-profiles` is **read-only** and displays counts (never personal
profile names): current profiles, archived profiles, identical names
with equal values, missing profiles, conflicting names with **different**
values, and the resulting count versus the existing eight-profile
maximum. If any name conflicts with a different value or the union
exceeds the limit, the plan refuses; do not delete or rename files
automatically to bypass it. Keep both source and destination intact
and resolve the naming/capacity decision separately with the owner.

`merge-profiles` refuses the same conflicts before asking anything.
It skips matching profiles, then requires exact uppercase **MERGE**
to add only missing inactive profiles in an atomic private catalog
update under the existing mixer writer lock. All pre-existing
profile names and values remain unchanged. No current mixer level,
mute, EQ, source route, access credential, device binding or music
is applied, exported or overwritten. Running the operation again
when all saved profiles match creates **no new catalog generation**.
If the archive or catalog changes during confirmation, the operation
refuses safely rather than applying an old preview.

After separately restoring saved EQ from neutral state with the
existing `restore-eq` consent, compare the merged state:

    audiohub-presets-transfer verify-merged /absolute/external/private-folder

`verify-merged` is read-only. It requires **every archived** profile
to match its local name and values, plus all nine saved EQ bands;
**extra locally created profiles are allowed and retained**. The
older `verify` is intentionally stricter and requires exact equality
of the whole catalog, so `verify` can refuse a successful non-destructive
merge without implying data loss. Neither check measures audible sound.

Retain the archive and original SD until all separately authorized
hardware tests and operator acceptance are complete. These are
unverified, operator-only alpha commands; not an in-place OS update.

## One-command read-only SD transfer readiness (both WAV and presets)

The individual WAV and preset commands remain separately confirmed and
do not mount, flash, format or update either SD. An additional offline
**read-only** checklist closes the gap between these independent steps:

    audiohub-presets-transfer check-backup /absolute/private/archive /absolute/old-SD/home/audiohub/PrivateMusic /absolute/old-SD/home/audiohub/.config/audiohub

Run this on a new image **only after** the old SD is already mounted
read-only through a separately authorized operator procedure, and
the archive has been populated by both music backup and preset export.
`check-backup` reads the old SD's supported WAV files, saved EQ bands
and inactive volume profiles and compares them with the archive. It
refuses missing WAVs, file content differences, unsafe paths or a
changed EQ/profile snapshot. It does not modify the old SD or backup.
An old SD without the new CLI cannot perform this check itself.

To review a **replacement/new SD** before restoration:

    audiohub-presets-transfer plan-new /absolute/private/archive

`plan-new` reads and hashes existing WAV destinations to distinguish
identical copied files from missing files. It reports how many WAVs
still need copying, archived inactive profiles missing/identical/
conflicting, and differences between stored three-band EQ values.
It never lists user track names, profile names, device IDs or paths,
and it never copies files or writes settings. Different same-name
WAV bytes, unsupported WAVs, unsafe private paths, bad archive
schema, conflicting profiles or an existing non-neutral EQ are
flagged or refused, **never silently overwritten**.

Following the plan, independently run only the relevant already
available, *separately consented* actions (the destination must exist
as an operator-private 0700 directory):

    audiohub-music-transfer restore /absolute/private/archive --resume
    audiohub-presets-transfer merge-profiles /absolute/private/archive
    audiohub-presets-transfer restore-eq /absolute/private/archive

These require distinct exact `COPY`, `MERGE` and `APPLY-EQ`
confirmations where changes are needed. Do not treat the plan as
consent or execute the actions if its corresponding section is
blocked. An extra local profile is preserved, and `restore-eq`
still refuses a destination with non-neutral EQ.

After copying and confirming the separately reviewed saves:

    audiohub-presets-transfer check-new /absolute/private/archive

`check-new` verifies **both** the source-set SHA256 identity of
every supported archived WAV and the archived saved EQ/inactive
profiles on the replacement SD. Extra local volume profiles
remain allowed; the check does not require that the SD image be an
exact filesystem mirror. It is read-only, fail-closed if no WAV
set exists, and prints a clear pass only when **both** groups match.
If there is no WAV content, the operator cannot claim the combined
check passed; use the standalone preset verification instead.

All of these are operator-only checks in an already authorized
local terminal, with no root or network access. They do **not**
prove physical sound, persistent hardware state, a completed OS
update, owner trust or any of the separate production GO criteria.
Keep original SD and archive intact for rollback.

## First WAV backup from an older SD without installed transfer software

The previous `audiohub-music-transfer backup ARCHIVE` command reads the
**current running** `/home/audiohub/PrivateMusic` only. This is not
the old SD if the operator has already booted the replacement SD.
To avoid accidentally backing up an empty NEW music folder, the new
image supports a two-directory *offline, explicit* first migration:

    audiohub-music-transfer backup-old /absolute/old-SD/home/audiohub/PrivateMusic /absolute/external/private-folder

Use the new test SD's installed command as the unprivileged `audiohub`
user. The operator must have separately mounted the OLD SD **read-only**
via an authorized reader and confirmed the old folder's UID matches
the current audiohub account. No file on the old SD is executed,
mounted, chmod'ed or edited. The destination is a separately created
owner-only private archive directory (0700). The operator sees track
count, byte total and new-file count, then explicitly enters exact
`COPY` before exclusively creating verified mode-0600 WAV copies.
The new command shares the established bounded 40-track/512-MiB,
SHA256, no-symlink/no-hardlink, non-overwrite transfer engine.

If a copy was interrupted, inspect both folders and use:

    audiohub-music-transfer backup-old /absolute/old-SD/home/audiohub/PrivateMusic /absolute/external/private-folder --resume

`--resume` hashes every pre-existing same-name destination WAV and
accepts only byte-for-byte matching safe files. It never silently
replaces existing WAV content. Differences or unsafe entries cause
a refusal before any additional copy. Copying may leave verified
new destination files if a later unrelated error occurs; repeat
only after review and keep the old SD untouched.

To check the WAV transfer **without any writes or COPY prompt**:

    audiohub-music-transfer verify-backup-old /absolute/old-SD/home/audiohub/PrivateMusic /absolute/external/private-folder

Then separately export saved EQ and inactive profiles from that
same already-read-only old SD:

    audiohub-presets-transfer export-old /absolute/old-SD/home/audiohub/.config/audiohub /absolute/external/private-folder

After both source datasets exist, the existing combined
`audiohub-presets-transfer check-backup PRIVATE_ARCHIVE OLD_MUSIC OLD_CONFIG`
compares their WAV bytes plus the EQ/profile data before replacement.
Do not continue to the new SD `plan-new`, separately confirmed
`restore --resume` / `merge-profiles` / `restore-eq`, or final
`check-new` until old-source data are verified. Keep old SD and
private archive for rollback; none of these commands transfers
owner identities, wireless trust or system configuration.
Current alpha remains unverified for actual Pi4 audio hardware.

## One guided restore on the replacement SD: COPY / MERGE / APPLY-EQ

To reduce mistakes when switching SD cards, the new test image includes a
single **operator-initiated local terminal** entrypoint that reuses the
existing guarded operations (NOT a new installer or new writer):

    audiohub-presets-transfer restore-guided /absolute/private/archive

Run it **only after** the original SD has been retained, separately
authorized WAV + preset backups have been made and checked using
`check-backup`, and the replacement SD has been manually flashed and
booted according to the operator's independent process. The archived
private directory is pre-existing, same-UID, no symlinks. Neither this
command nor any transfer command mounts or flashes cards.

The guide first performs the combined **READ-ONLY** `plan-new`
comparison of WAV-bytes, existing inactive volume profiles and EQ bands.
If any same-name WAV differs, a saved profile name conflicts with a
different value, the 8-profile maximum would be exceeded, or the local
saved EQ is already non-neutral and different from the archive, the
ENTIRE guide refuses **before writing a WAV or profile**. The operator
must resolve such differences without overwriting old data.

If the reviewed plan is safe, the guide performs up to three *separate*
operator-confirmed steps:

1. **COPY**: only missing supported WAVs, via the existing non-overwriting
   `restore --resume` algorithm; pre-existing equal WAVs are SHA256
   verified and skipped. All archived WAVs are hashed again afterward.
2. **MERGE**: only missing INACTIVE custom volume profiles via the
   existing locked, atomic, conflict-free merge. Existing values,
   current levels and mutes remain unchanged.
3. **APPLY-EQ**: only nine archived saved EQ bands, and only if local
   saved EQ is neutral; it never stages/restarts PipeWire or changes
   current audible sound. This has its own confirmation.

A stage that needs no changes skips its consent prompt and performs no
write. Any refused or cancelled confirmation **stops** the guide; it
does not proceed to subsequent steps or silently undo already verified
WAV copies. On a later explicit invocation, previously matching WAVs
and profiles are skipped. After the last step, the guide invokes
`check-new` for a complete read-only WAV SHA256 and saved EQ/profile
comparison; no "finished" claim is printed unless both groups match.
A source preset archive changed mid-operation is refused rather than
silently accepted.

The guide does not automatically import device ID, owner credentials,
Bluetooth trust, Wi-Fi, source assignments, audio routes, active volume
or OS configuration. It also does not verify live PipeWire sound,
speaker hardware, SD durability, 2-BT-plus-LAN or production readiness.
A failed step leaves the original SD untouched; retain it and the
external backup for physical rollback. Never use this as authorization
to flash an existing SD or modify machine permissions.

## Guided first backup FROM an old SD without transfer software

For a manually initiated test update, the new Pi4 image can **first**
save both supported data sets from an already operator-mounted,
**read-only** old SD in a single verified sequence. On the *new*
Pi4 SD, as its existing unprivileged audiohub user, run:

    audiohub-presets-transfer backup-guided /absolute/private/archive /absolute/old-SD/home/audiohub/PrivateMusic /absolute/old-SD/home/audiohub/.config/audiohub

Order matters: **private archive first**, old SD music directory second,
old SD private AudioHub config directory third. All must already exist;
the archive needs private mode 0700, the old SD source folders must be
owned by the same audiohub UID with mode 0700 or read-only mode 0500.
No command mounts, flashes, formats, changes permissions, or executes
files from the old SD. Keep the original card untouched.

The guide performs a **combined read-only preflight before any write**:
it detects supported old-SD WAVs, verifies any same-name files already
inside the private archive by SHA256, and validates the saved EQ
plus inactive volume-profile catalog. If a colliding WAV differs or
an existing private preset JSON snapshot no longer matches the old
SD, the guide refuses **before copying anything**. It never replaces
a prior archive file, even if the operator entered COPY.

After a safe review, it performs two individually approved stages:

1. **COPY**: copies only missing, supported WAV files into the archive,
   with the existing bounded, exclusive 0600 write and SHA256-verified
   resume algorithm. Byte-identical existing files are skipped.
2. **SAVE**: exclusively creates audiohub-presets.json containing only
   validated three-band EQ and inactive custom volume profiles.
   Existing identical archives are skipped, without regenerating them.

A blank/neutral old-SD EQ and **zero custom profiles** are a legitimate
state: the guided command can still save a nonsecret neutral snapshot,
so the final dual-data check can finish. The original standalone
`export-old` intentionally continues to require actual customized
presets, to avoid changing its previous behavior.

On cancel, the guide stops immediately. WAV files already verified in
the private archive remain there; a later intentional invocation
compares them again and resumes **without overwrite**. No auto-rollback,
no file delete, no overwrite and no pretending an incomplete archive
is complete. Before claiming completion it runs existing
`check-backup` to compare the original WAV set and both saved preset
data sets to the external archive **read-only**. You may repeat the
same guide to recheck an already fully matching backup without new
files or confirmation prompts.

The operation does **not** transfer authentication, BT/Wi-Fi pairing,
owner credentials, certificates, device IDs, source routing, active
volumes or mutes, or any OS settings. It does not prove actual Pi4
audio hardware, SD media reliability or legal/public release readiness.

For an old SD with **no supported WAV files**, the combined guide
refuses a misleading "complete" result; the separate existing
`export-old` path still covers personalized EQ/profile data.
Once the complete source archive is verified, continue with the
already documented new-SD `restore-guided ARCHIVE` under its separate
COPY / MERGE / APPLY-EQ confirmations, and retain the original SD for
physical rollback. Do not run either guide on a production SD without
explicit separate operator authorization.
