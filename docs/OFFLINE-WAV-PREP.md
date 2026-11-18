# AudioHub: offline MP3/FLAC preparation for the private Pi4 WAV player

**Optional operator-only ALPHA utility; not a release or audio hardware approval.**

The current Pi4 AudioHub music input accepts bounded uncompressed PCM16/PCM24
WAV. This small, separately started PC utility makes a NEW compatible
**PCM16 stereo 48 kHz WAV** from one owned/licensed **.flac or .mp3** source.
It does NOT add an MP3/FLAC decoder to the Pi, claim bit-perfect output, or
convert existing music without explicit manual approval.

## Before starting (trusted PC, offline)

- Use the current **source-SHA-matched** AudioHub Windows portable ALPHA ZIP.
  It already requires separately installed Python 3.11+.
- On the **trusted PC only**, have a separately installed `ffmpeg` on PATH.
  FFmpeg is a third-party application NOT included, purchased, downloaded,
  installed or licensed for you by AudioHub. Review its terms independently.
  No codec executable is present in this ZIP or installed on Raspberry Pi.
- Use **your own or licensed** MP3/FLAC, an **absolute local** source path
  (no UNC/network shares or directory links), and a DIFFERENT, unused
  absolute `.wav` destination path in an **existing local folder**.
  Files on the original SD are not automatically copied, scanned, or changed.

## One-click Windows start — no installer or command typing

After independently verifying both Windows ZIP checksums and extracting the
**inner** portable package onto a trusted **local drive**, double-click
`OPEN-AUDIOHUB-MUSIC-PREP.cmd`. It starts the same local graphical file
picker with an existing Python 3.11+; no external application is installed,
no audio is decoded and no network access or Pi action occurs merely on
launch. This source-transparent `.cmd` file is NOT a signed Windows EXE.
Do not execute untrusted downloads, scripts or unexpected prompts.

To examine PC readiness **without writing a WAV**, in a terminal inside
the extracted folder use:

```powershell
.\OPEN-AUDIOHUB-MUSIC-PREP.cmd --check
```

The check reports only whether Python 3.11+, Tk and a separately installed
FFmpeg are detected, not their paths or your filenames. It does not run
FFmpeg or access music. If FFmpeg is missing, source/destination Preview
still works in the GUI but conversion is disabled until FFmpeg is installed
independently on that PC and the launcher restarted. The command below
remains an equally supported alternative for operators preferring Python.
If a corporate PC blocks local scripts, follow its security policy; there
is no approved signed installer to override those restrictions.

## Multiple Python installations: safe startup fallback

If both the Windows Python launcher `py.exe` and a separate
`python.exe` are on PATH, this portable launcher no longer assumes
that `py.exe -3` points to a usable Python. It first performs a
**no-music** Python 3.11+/Tk import probe; if `py.exe -3` is old,
broken or lacks Tk, it tests `python.exe` separately and uses the
first compatible interpreter for **all** later steps (dependency
report, package self-check, WAV demo and GUI). The active choice is
shown as `compatible py.exe -3 runtime` or
`compatible python.exe fallback runtime`, without displaying your
private PATH. No executable is downloaded or installed.

The standalone `--package-check` only needs Python 3.11+, **not Tk
or a desktop**. `--check`, `--smoke`, and GUI launch still require
Tk; external FFmpeg remains optional except for a separately approved
conversion. If neither installed Python works, the launcher refuses
with exit 2 and instructions to use a trusted independently installed
Python; it never falls back to an unsupported Python.

## New one-click startup gate and single-command first-run smoke

The existing Windows `OPEN-AUDIOHUB-MUSIC-PREP.cmd` now checks
**Python 3.11+ and Tk readiness** and the **entire extracted portable
source file inventory** before opening its GUI on double-click.
An incomplete or accidentally changed package, unsupported Python,
missing Tk or unsafe local extraction causes a clear **START REFUSED**
message. It never downloads, installs, overwrites or converts anything
while starting. External FFmpeg remains optional for this check; it
is needed only for a separate explicitly confirmed MP3/FLAC conversion.

To test the **whole** operator first-run path before opening the GUI,
use this ONE command in the extracted INNER ZIP folder:

```powershell
.\OPEN-AUDIOHUB-MUSIC-PREP.cmd --smoke
```

It first checks Python/Tk (no writes), then the extracted package
manifest (read-only), and finally creates and cleans its own short
**synthetic WAV demonstration** in the ordinary local OS temporary
folder. Successful output includes `AudioHub FIRST-RUN SMOKE PASS`
and exit code 0. A failed prerequisite, package self-check or demo
returns exit 2 and does **not** open the GUI or read personal music.
The previous `--check` (dependencies only) and
`--package-check` (file inventory only) remain available.

**Security limit:** The package self-check is not an origin proof,
signature or substitute for verifying OUTER and INNER GitHub ZIP
SHA256 **before** executing this launcher. Never point it at a
private music directory; extract the verified portable ZIP to a NEW
empty local directory and preserve your previous version and Pi SD
for rollback. The smoke uses no Pi, Edifier, actual music, Scream
driver or FFmpeg and does not certify them.

## Identify the installed portable source SHA and check its files

The Windows GUI shows the self-reported 12-character source label in its
title. Click **7. Show version and check package files (read-only)** to
display the **full source Git commit SHA** and check all 18 packaged
source files against `SOURCE-MANIFEST.json`. In PowerShell, in the
**inner extracted ZIP folder**, run:

```powershell
.\OPEN-AUDIOHUB-MUSIC-PREP.cmd --package-check
```

Equivalent: `py -3 START-OFFLINE-WAV-PREP.py --package-check`.
Exit 0 / MATCH means the source files agree with the bundled manifest,
exit 2 / REFUSED means something is missing or different. This check
does not read private music, contact a network or alter your WAVs.

**This is a local self-check only, NOT authentication.** Both code and
manifest come from the same archive. Independently verify the actual
GitHub outer ZIP SHA256 and contained inner ZIP SHA256 BEFORE running
them. For each upgrade, extract a verified ZIP into a **new folder**,
leave the previous installed version and Pi SD untouched, and only
discard an older folder after actual Windows acceptance and backup.
If the check fails, do not continue using that folder: re-download and
hash a trusted copy. There is no automatic update or installer.

## First-run local WAV demonstration — no personal audio needed

In the extracted Windows portable ALPHA, double-click
`OPEN-AUDIOHUB-MUSIC-PREP.cmd` and choose **6. Run offline demo
(synthetic; no music needed)**. It exercises the **real** bounded PCM16
stereo 48-kHz WAV file and folder verification code with two short
generated synthetic WAV samples. The report shows: renamed/reordered
two-track copy MATCH, a missing track correctly DIFFERS, and the read-only
Stop mechanism correctly refuses to report an incomplete scan as verified.

No MP3/FLAC, personal WAV path, FFmpeg, Scream driver, network connection,
Pi4, speaker sound or copyrighted music is needed for this demonstration.
Only a freshly created, private OS temporary directory is written with
**synthetic test files**; it is removed when the check finishes or fails.
No operator music files are created, read, altered or removed. If the
computer's temporary folder is unsafe (linked/network), the demo refuses.

Terminal alternative from the **same extracted portable ZIP**:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --demo
```

Expect `SYNTHETIC WAV DEMO PASS: 2` and exit code 0; a failed check
reports `SYNTHETIC WAV DEMO FAILED` and exit 2. The desktop GUI has
an equivalent clear PASS/FAIL message. The demonstration requires the
same separately installed Python 3.11+/Tk desktop as the existing GUI.
It is a useful **Windows operator S3 app-start demonstration**,
but not proof of real music compatibility, FFmpeg conversion,
Edifier sound, secure Pi login, SD transfers, licenses or production GO.
Keep the previously checked portable ZIP for rollback.

## Hear the WAV you JUST converted, without picking it again

After an explicitly confirmed, successful conversion that has already
passed final read-back verification, the Windows GUI now enables
**9. Hear last verified export (no file picker)**. This button is disabled
until a conversion actually succeeds; it never starts playback automatically.
It uses only the filename and full SHA256 captured from that exact completed
conversion, not an editable path in a later file-picker dialog. A change to
the source/destination selection or a new conversion attempt clears this
one-click shortcut.

Clicking button 9 asks for audible **Windows PC** playback and volume consent
exactly like button 8, and plays the first three seconds at **-12 dB**
only after rechecking the current WAV against the original SHA256.
If another process changes or replaces the WAV after conversion, the replay
is **REFUSED before sound**. Original WAV and system volume remain unchanged.
The existing button **8** still lets you explicitly pick *any* owned local
compatible WAV. This is not a Pi4/Edifier audio test.

## Hear a prepared WAV on the Windows PC (new, opt-in)

The portable **Windows GUI** now has **8. Hear 3-second owned WAV on this
Windows PC** and **Stop PC sound preview**. Select a previously prepared,
**owned or licensed local PCM16 stereo 48-kHz WAV**. AudioHub asks
explicitly for audible playback and reminds you to adjust your speaker
or headphone volume. Only after you confirm does it perform a complete
read-only WAV format and SHA256 check and play the **first 3 seconds at
most** through the default **Windows PC sound device**, with a fixed
**12 dB digital attenuation** in the temporary memory clip. Original WAV
and system mixer volume are unchanged. Lower your PC volume before trying. The GUI remains
responsive while the sample plays. Stop requests interrupt Windows
PlaySound where supported; any already-running sample is limited to
3 seconds.

The sample is assembled as a bounded in-memory WAV (maximum 576,044
bytes) and passed to Windows built-in `winsound.PlaySound`. Nothing is
exported, converted, copied, uploaded or written to a temporary file:
the original WAV remains unchanged. No FFmpeg, extra sound library,
Pi4, Edifier, Scream driver, Bluetooth connection or network is
required. It uses **the Windows PC's default speaker/headphone output**
and neither selects nor controls a remote device. A WAV that does not
meet the existing strict local verification requirements is refused
**before audio playback**. No sound begins from opening the GUI.

Explicit Windows terminal alternative:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --audition-wav "C:\Private\Prepared\owned-song.wav"
```

This is an explicitly audible action. Exit 0 means the Windows sound
API completed its call, **not** that the operator heard audio or Pi/
Edifier speakers worked. Exit 2 means missing, unsafe, changed, wrong
format or unavailable Windows sound output. No private filename is
written in the tool's report. A genuine audible Windows test requires
the operator to listen and note whether it played, including any
wrong-channel/silence issue. Keep the volume low for a first test.

## GUI: choose source and target, then explicitly confirm

On Windows, open a PowerShell terminal in the **extracted inner portable ZIP**
folder. With the already-required Python 3.11+ and a local desktop session,
run:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --gui
```

The GUI provides **Choose source** (owned MP3/FLAC), **Choose new WAV**
(an unused filename in an existing LOCAL folder), **1. Preview** and
**2. Convert**. After **Choose source**, the GUI automatically SUGGESTS
an unused local sibling filename ending `-AudioHub.wav` (or
`-AudioHub-2.wav` and so on when occupied). It creates/reserves NOTHING
until separate confirmation; check the suggestion before Preview. A
manually chosen/typed target is preserved, and **Choose new WAV** can
always select a different existing local folder. If no safe short name
is available, choose the unused target manually. Existing targets are
never overwritten, even if a suggested name becomes occupied later. Preview has NO decoder and creates nothing. After a
successful preview, the second button requires typing **CONVERT** in a
modal dialog. Cancel, closing the dialog or changing either path never
starts FFmpeg; paths changed after Preview must be previewed again.
External FFmpeg availability is checked before enabling the Convert button;
if missing the GUI explains what is required without trying to install it.
While a bounded conversion runs, the fields and file-picker buttons are
locked, preventing edits and accidental repeat starts. Completion displays
the new WAV SHA256 without logging your private filenames. Both the
GUI and terminal path use the SAME non-overwriting, memory-bounded local
conversion. The GUI has no remote access and is not available on a
headless PC. Installing FFmpeg separately on your own PC remains necessary.

## Verify a prepared WAV without FFmpeg (no writes)

After converting, leave the newly created file in the output field and click
**3. Verify WAV (read-only)**. You can also paste an existing local WAV path
in that field and use Verify directly. The tool checks the complete bounded
PCM16 stereo 48-kHz data, detects truncated/linked/unsafe files and reports
SHA256; it never calls FFmpeg, modifies files or contacts the Pi. For the
same operation in the extracted Windows portable folder:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --verify-wav "C:\\Private\\Prepared\\owned-song.wav"
```

The check prints no private filename. PCM24 and other formats are not
supported by this particular PC-side verifier. A successful result proves
local WAV structure only, **not audible Edifier playback** or permission
to transfer copyrighted music. Use the independently checked SHA256 after
any manual transfer; retain old SD and all original media.

## Check a private WAV folder in one step (no writes, no FFmpeg)

For a manually prepared music folder, choose **4. Check WAV folder (read-only)**
in the same GUI. This checks **1 to 40 direct .wav tracks**, each PCM16 stereo
48 kHz, fully reads their content and reports a collection SHA256. The folder
may contain unrelated files; only direct .wav files are inspected. The scan
refuses symlinks, corrupt/truncated WAVs, ambiguous case-colliding names,
folders with over 256 direct entries, and changes during the check. It runs
on a background worker so the GUI remains responsive, with editing locked
until completion. No files are created, played, transferred or modified.

Offline terminal equivalent, also available in the extracted Windows ZIP:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --verify-folder "C:\Private\Prepared"
```

The result is a deterministic **ordered-content fingerprint**, not a
filename-preserving backup manifest. It never prints the private filenames
or paths; use single-file Verify for individual hashes. It does not verify
the Pi4 USB speaker, owner permissions, music copyright, free SD space, or
the success of a later USB copy. Recheck the selected folder after any
manual transfer and keep all original files and the previous SD card.

## Progress and safe stop for long read-only scans

The existing Windows GUI displays a private per-track counter while checking
**4. Check WAV folder** or **5. Compare WAV copy** (for example:
`READ-ONLY ORIGINAL FOLDER: 3/20 WAVs inspected`). The **Stop read-only
check** button is enabled only for these scans. Click it at any time to
request cancellation; the worker checks the request between bounded WAV
read chunks and before reporting a successful verification. After a stop,
the application reports **STOPPED** instead of a potentially misleading
MATCH or VERIFIED result; it does not touch originals or copied WAVs.
The scan remains on a background thread and all UI updates occur on the
desktop thread. No filenames, directory paths or media metadata are
displayed in progress messages. The Stop button is intentionally disabled
for the separately confirmed WAV **conversion**; conversion still follows
its own bounded completion, cleanup and no-overwrite safety rules.
Closing the GUI during a read-only scan requests Stop first; close it
once STOPPED is displayed.

## Check an existing WAV copy against the original (no writes)

In the Windows GUI use **5. Compare WAV copy (read-only)**, then select the
original local prepared WAV folder and the different local folder you copied
it into manually. Each folder must contain 1–40 direct PCM16 stereo 48-kHz
WAVs and pass the bounded safety checks. The worker performs no writes,
transfers, uploads or FFmpeg calls, and does not show private file names.

The equivalent command from the extracted portable Windows package is:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --compare-folders "C:\Private\Prepared" "D:\MyCopiedWavs"
```

Exit 0 means **MATCH**: exactly the same complete WAV file contents, including
duplicate-file counts, regardless of names or filename sorting. Exit 1 means
**DIFFERS**: both folders are valid, but some contents or their multiplicities
differ. Exit 2 means **REFUSED**: identical/invalid/missing/unsafe folders.
Results use an order-independent **copy-content SHA256** computed from the
sorted multiset of each fully verified file's size and hash. The existing
`--verify-folder` ordered collection SHA256 remains unchanged and is
deliberately distinct. Renaming/reordering copied files no longer creates a
false mismatch; repeated identical tracks are not silently discarded.

A MATCH does not prove matching filenames, folder layout, timestamps,
permissions, licenses, Pi/Edifier sound, an SD restore, or a durable
cross-device transaction. Do not automatically erase or overwrite anything
on DIFFERS. Preserve your originals and old Pi SD.

## Step 1 — no-write preview (FFmpeg not required)

From a trusted Windows terminal in the extracted portable alpha folder:

```powershell
py -3 START-OFFLINE-WAV-PREP.py --source "C:\Private\owned-song.flac" --output "C:\Private\Prepared\owned-song.wav"
```

The preview checks supported suffix, size and safe source/destination paths
only. It neither opens an audio decoder nor creates/overwrites files. The
folder `C:\Private\Prepared` must already exist. For MP3 use `.mp3`.
Never paste your actual private file paths into public issue reports.

## Step 2 — explicitly write one new WAV, no overwrite

```powershell
py -3 START-OFFLINE-WAV-PREP.py --source "C:\Private\owned-song.flac" --output "C:\Private\Prepared\owned-song.wav" --convert
```

Review the preview and type exactly **CONVERT** and Enter in that same
trusted local terminal. Cancel with any other input. FFmpeg is invoked
without a shell, with an exact MP3/FLAC demuxer and local-file/pipe-only
protocols. Its output is decoded into a bounded temporary PCM16 WAV; only
after a complete, valid conversion is the destination **exclusively** created
with no replace. **Before success**, AudioHub reopens the final destination,
validates complete PCM16 stereo 48-kHz data, and compares its full SHA256
and byte count to the streamed output. On a failed final read-back, the
operation refuses success and removes only its own unchanged newly created
file, never a replacement file from another process. This is local file
integrity at completion, **not audible sound**. An existing target is
always refused. Input audio is
never edited, renamed or deleted. New-file permissions are private (0600)
on POSIX; manage Windows NTFS ACLs yourself.

The output contains no original tags, artwork or metadata; expect a
**loss of MP3 quality / possible resampling** and conversion of FLAC to
16-bit PCM, not a lossless or hi-res guarantee. Each source input is bounded
to 512 MiB; output is bounded to 64 MiB (including WAV header) and up to
30 minutes. Failed/oversized exports do not publish a new WAV, and a timeout
cannot mark an incomplete conversion as successful. Only the exact selected
new target may be created; no Pi state, volume, mixer or network changes.

## Step 3 — verify and transfer manually

The utility reports the new WAV only after destination read-back and
prints its byte count and SHA256, **not your filenames**. Independently
inspect the output WAV and hash on the trusted PC. Keep all originals and the original Pi SD unchanged. Separately
approve any local music transfer using the existing
`audiohub-music-transfer` workflow only after AH-005 secure local owner
access and safe Pi shutdown are authorized. Backup/verify all other
WAV/EQ/MP3/FLAC/personal data independently; the WAV-only transfer is not
a complete SD backup.

No automatic Pi flash, Bluetooth pairing, WLAN setup, SSH, hardware sound
verification, public release or licensed redistribution is implied.
