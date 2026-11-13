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
