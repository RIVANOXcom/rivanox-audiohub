#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
if [ ! -d "${ROOTFS_DIR}" ]; then
  copy_previous
fi
