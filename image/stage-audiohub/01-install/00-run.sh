#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
install -d -m755 "${ROOTFS_DIR}/opt/audiohub/src" \
  "${ROOTFS_DIR}/usr/local/bin" \
  "${ROOTFS_DIR}/etc/systemd/system" \
  "${ROOTFS_DIR}/opt/audiohub/web" \
  "${ROOTFS_DIR}/etc/systemd/user" \
  "${ROOTFS_DIR}/etc/systemd/user/default.target.wants" \
  "${ROOTFS_DIR}/etc/wireplumber/wireplumber.conf.d" \
  "${ROOTFS_DIR}/var/lib/systemd/linger"
cp -a files/src/audiohub "${ROOTFS_DIR}/opt/audiohub/src/"
cp -a files/web/. "${ROOTFS_DIR}/opt/audiohub/web/"
install -m755 files/bin/audiohub-music "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
install -m755 files/bin/audiohub-music-transfer "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer"
install -m755 files/bin/audiohub-presets-transfer "${ROOTFS_DIR}/usr/local/bin/audiohub-presets-transfer"
cp files/systemd/audiohub-bluetooth.service "${ROOTFS_DIR}/etc/systemd/system/"
cp files/systemd/audiohub-firstboot-diag.service "${ROOTFS_DIR}/etc/systemd/system/"
cp files/systemd/audiohub-runtime.service "${ROOTFS_DIR}/etc/systemd/user/"
cp files/systemd/audiohub-status-web.service "${ROOTFS_DIR}/etc/systemd/user/"
ln -sfn ../audiohub-runtime.service \
  "${ROOTFS_DIR}/etc/systemd/user/default.target.wants/audiohub-runtime.service"
ln -sfn ../audiohub-status-web.service \
  "${ROOTFS_DIR}/etc/systemd/user/default.target.wants/audiohub-status-web.service"
cp files/wireplumber/90-audiohub.conf "${ROOTFS_DIR}/etc/wireplumber/wireplumber.conf.d/"
touch "${ROOTFS_DIR}/var/lib/systemd/linger/audiohub"
on_chroot <<'CHROOT'
set -e
systemctl enable bluetooth.service
systemctl enable audiohub-bluetooth.service
systemctl enable audiohub-firstboot-diag.service
install -d -o audiohub -g audiohub -m700 /home/audiohub/.config
# Empty protected folder on the NEW image only. The operator supplies WAVs.
install -d -o audiohub -g audiohub -m700 /home/audiohub/PrivateMusic
# Native chroot smoke: command is installed and callable without PYTHONPATH.
runuser -u audiohub -- /usr/local/bin/audiohub-music --help >/dev/null

# Real installed local music launcher: bounded operator arguments and
# non-playing anonymous file-list mode. Empty native image music folder
# intentionally refuses instead of starting PipeWire or leaking titles.
set +e
empty_library_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music /home/audiohub/PrivateMusic --list 2>&1)"
empty_library_status="$?"
invalid_level_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --level loud 2>&1)"
invalid_level_status="$?"
invalid_time_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --minutes 31 2>&1)"
invalid_time_status="$?"
set -e
test "$empty_library_status" -eq 2
test "$invalid_level_status" -eq 2
test "$invalid_time_status" -eq 2
case "$empty_library_output" in *"Local player unavailable or stopped"*) ;; *) exit 1 ;; esac
case "$invalid_level_output" in *"Only quiet, soft or normal"*) ;; *) exit 1 ;; esac
case "$invalid_time_output" in *"Minutes must be a whole number"*) ;; *) exit 1 ;; esac

# Actual installed Pi4 stereo channel option must fail closed for invalid
# names. This cannot play sound or modify user volume or other sinks.
set +e
invalid_channel_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --channel center 2>&1)"
invalid_channel_status="$?"
set -e
test "$invalid_channel_status" -eq 2
case "$invalid_channel_output" in *"Only both, left or right stereo"*) ;; *) exit 1 ;; esac

# Installed original stereo diagnostic is never allowed to emit audio
# unattended in a native build chroot. It must reach Python's TTY gate,
# not become an unknown shell command or spawn a player.
set +e
speaker_noninteractive_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --speaker-test 2>&1)"
speaker_noninteractive_status="$?"
set -e
test "$speaker_noninteractive_status" -eq 2
case "$speaker_noninteractive_output" in *"Local player unavailable or stopped"*) ;; *) exit 1 ;; esac

# Selecting a valid single side must reach the installed Python TTY guard.
# The native image test is unattended and MUST NOT create audible output.
set +e
speaker_side_noninteractive_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --speaker-test left 2>&1)"
speaker_side_noninteractive_status="$?"
set -e
test "$speaker_side_noninteractive_status" -eq 2
case "$speaker_side_noninteractive_output" in *"Local player unavailable or stopped"*) ;; *) exit 1 ;; esac

# The installed guided speaker check must also refuse native unattended
# chroot execution before any sink inspection or audible player subprocess.
set +e
speaker_guide_noninteractive_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --speaker-guide 2>&1)"
speaker_guide_noninteractive_status="$?"
set -e
test "$speaker_guide_noninteractive_status" -eq 2
case "$speaker_guide_noninteractive_output" in *"Local player unavailable or stopped"*) ;; *) exit 1 ;; esac

# Real installed non-playing --check is a multi-prerequisite operator status.
# The fresh image contains no WAVs, so readiness must refuse with safe guidance.
# It must never start an audio session, reconfigure PipeWire or expose titles.
set +e
empty_check_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music --check 2>&1)"
empty_check_status="$?"
set -e
test "$empty_check_status" -eq 2
case "$empty_check_output" in *"WAV library: NEEDS ATTENTION"*"Private PipeWire music input:"*"Local PipeWire playback tool:"*"No playback, global mixer/route change or file write occurred."*) ;; *) exit 1 ;; esac
# Offline transfer help is a NON-WRITING native ARM64 command smoke.
runuser -u audiohub -- /usr/local/bin/audiohub-music-transfer --help >/dev/null
# Exercise the real installed wrapper's TWO and THREE-argument forwarding.
# Both paths safely refuse before any transfer; no disk/TTY/owner changes.
set +e
verify_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music-transfer verify-backup /home/audiohub/PrivateMusic 2>&1)"
verify_status="$?"
resume_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music-transfer backup /home/audiohub/PrivateMusic --resume 2>&1)"
resume_status="$?"
set -e
test "$verify_status" -eq 2
test "$resume_status" -eq 2
case "$verify_output" in *"Safe offline WAV transfer refused"*) ;; *) exit 1 ;; esac
case "$resume_output" in *"Safe offline WAV transfer refused"*) ;; *) exit 1 ;; esac

# Old SD lacking an installed launcher: these 3/4-arg commands run using
# the NEW image's installed Python utility. Non-TTY refusal guarantees
# no unattended source edits, mounts, WAV copies or external archive writes.
set +e
old_wav_backup_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music-transfer backup-old /home/audiohub/PrivateMusic /home/audiohub/PrivateMusic 2>&1)"
old_wav_backup_status="$?"
old_wav_resume_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music-transfer backup-old /home/audiohub/PrivateMusic /home/audiohub/PrivateMusic --resume 2>&1)"
old_wav_resume_status="$?"
old_wav_verify_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-music-transfer verify-backup-old /home/audiohub/PrivateMusic /home/audiohub/PrivateMusic 2>&1)"
old_wav_verify_status="$?"
set -e
test "$old_wav_backup_status" -eq 2
test "$old_wav_resume_status" -eq 2
test "$old_wav_verify_status" -eq 2
case "$old_wav_backup_output" in *"Safe offline WAV transfer refused"*) ;; *) exit 1 ;; esac
case "$old_wav_resume_output" in *"Safe offline WAV transfer refused"*) ;; *) exit 1 ;; esac
case "$old_wav_verify_output" in *"Safe offline WAV transfer refused"*) ;; *) exit 1 ;; esac
runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer --help >/dev/null
# Native three-argument first-SD migration smoke: require Python's safe
# non-TTY refusal, not a shell-wrapper usage error; never open/mount old SD.
set +e
old_preset_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer export-old /home/audiohub/.config/audiohub /home/audiohub/PrivateMusic 2>&1)"
old_preset_status="$?"
set -e
test "$old_preset_status" -eq 2
case "$old_preset_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac
# Confirm the installed merger/preview reach the Python argument handler.
# Running non-interactively must refuse without creating files or applying EQ.
set +e
merge_preview_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer plan-profiles /home/audiohub/PrivateMusic 2>&1)"
merge_preview_status="$?"
merge_apply_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer merge-profiles /home/audiohub/PrivateMusic 2>&1)"
merge_apply_status="$?"
set -e
test "$merge_preview_status" -eq 2
test "$merge_apply_status" -eq 2
case "$merge_preview_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac
case "$merge_apply_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac

# Native bundled read-only SD checks: installed script dispatches two/four args
# to Python; trusted-TTY guard must reject unattended automatic migration.
set +e
sd_plan_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer plan-new /home/audiohub/PrivateMusic 2>&1)"
sd_plan_status="$?"
sd_after_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer check-new /home/audiohub/PrivateMusic 2>&1)"
sd_after_status="$?"
sd_old_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer check-backup /home/audiohub/PrivateMusic /home/audiohub/PrivateMusic /home/audiohub/.config/audiohub 2>&1)"
sd_old_status="$?"
set -e
test "$sd_plan_status" -eq 2
test "$sd_after_status" -eq 2
test "$sd_old_status" -eq 2
case "$sd_plan_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac
case "$sd_after_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac
case "$sd_old_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac

# Native installed guided migration is a reviewed INTERACTIVE operation.
# Non-TTY chroot execution must refuse inside its Python guard before
# creating archives, copying WAVs, changing mixer or asking for consent.
set +e
guided_restore_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer restore-guided /home/audiohub/PrivateMusic 2>&1)"
guided_restore_status="$?"
set -e
test "$guided_restore_status" -eq 2
case "$guided_restore_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac

# Installed 4-argument first old-SD backup guide is never unattended:
# no trusted TTY means the Python guard must fail without touching files.
set +e
guided_backup_output="$(runuser -u audiohub -- /usr/local/bin/audiohub-presets-transfer backup-guided /home/audiohub/PrivateMusic /home/audiohub/PrivateMusic /home/audiohub/.config/audiohub 2>&1)"
guided_backup_status="$?"
set -e
test "$guided_backup_status" -eq 2
case "$guided_backup_output" in *"Private preset operation safely refused"*) ;; *) exit 1 ;; esac
PYTHONPATH=/opt/audiohub/src runuser -u audiohub -- python3 -m audiohub.eq_setup
CHROOT
