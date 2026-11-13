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
PYTHONPATH=/opt/audiohub/src runuser -u audiohub -- python3 -m audiohub.eq_setup
CHROOT
