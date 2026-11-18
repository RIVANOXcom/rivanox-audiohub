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
with no replace. An existing target is always refused. Input audio is
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

The utility prints only the generated WAV byte count and SHA256, **not
your filenames**. Independently inspect the output WAV and hash on the
trusted PC. Keep all originals and the original Pi SD unchanged. Separately
approve any local music transfer using the existing
`audiohub-music-transfer` workflow only after AH-005 secure local owner
access and safe Pi shutdown are authorized. Backup/verify all other
WAV/EQ/MP3/FLAC/personal data independently; the WAV-only transfer is not
a complete SD backup.

No automatic Pi flash, Bluetooth pairing, WLAN setup, SSH, hardware sound
verification, public release or licensed redistribution is implied.
