#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
# Fail the image build if first-boot service packaging is inconsistent.
python3 files/audit_rootfs.py "${ROOTFS_DIR}"
