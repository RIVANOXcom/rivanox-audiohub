#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
# Fail the image build if first-boot service packaging is inconsistent.
python3 files/audit_rootfs.py "${ROOTFS_DIR}"
# Check the ACTUAL ARM64 staged image, not just checked-in source:
# the operator command must be installed, executable and non-symlinked.
test -f "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
test -x "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
test ! -L "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
test "$(stat -c '%a' "${ROOTFS_DIR}/usr/local/bin/audiohub-music")" = 755
# Verify the new image ships an empty private folder for user-supplied WAVs.
test -d "${ROOTFS_DIR}/home/audiohub/PrivateMusic"
test ! -L "${ROOTFS_DIR}/home/audiohub/PrivateMusic"
test "$(stat -c '%a' "${ROOTFS_DIR}/home/audiohub/PrivateMusic")" = 700

# Generate only allowlisted public-facing package metadata; never export host secrets.
python3 files/rootfs_package_inventory.py \
  --rootfs "${ROOTFS_DIR}" \
  --output "${ROOTFS_DIR}/usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
