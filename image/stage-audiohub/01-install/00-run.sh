#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
install -d -m755 "${ROOTFS_DIR}/opt/audiohub/src" \
  "${ROOTFS_DIR}/etc/systemd/system" \
  "${ROOTFS_DIR}/opt/audiohub/web" \
  "${ROOTFS_DIR}/etc/systemd/user" \
  "${ROOTFS_DIR}/etc/systemd/user/default.target.wants" \
  "${ROOTFS_DIR}/etc/wireplumber/wireplumber.conf.d" \
  "${ROOTFS_DIR}/var/lib/systemd/linger"
cp -a files/src/audiohub "${ROOTFS_DIR}/opt/audiohub/src/"
cp -a files/web/. "${ROOTFS_DIR}/opt/audiohub/web/"
cp files/systemd/audiohub-bluetooth.service "${ROOTFS_DIR}/etc/systemd/system/"
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
install -d -o audiohub -g audiohub -m700 /home/audiohub/.config
PYTHONPATH=/opt/audiohub/src runuser -u audiohub -- python3 -m audiohub.eq_setup
CHROOT
