#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
# Fail the image build if first-boot service packaging is inconsistent.
python3 files/audit_rootfs.py "${ROOTFS_DIR}"
# Generate only allowlisted public-facing package metadata; never export host secrets.
python3 files/rootfs_package_inventory.py \
  --rootfs "${ROOTFS_DIR}" \
  --output "${ROOTFS_DIR}/usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
