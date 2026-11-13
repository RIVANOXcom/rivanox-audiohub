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
PYTHONPATH=/opt/audiohub/src runuser -u audiohub -- python3 -m audiohub.eq_setup
CHROOT
