#!/bin/bash -e
# SPDX-License-Identifier: AGPL-3.0-only
# Fail the image build if first-boot service packaging is inconsistent.
python3 files/audit_rootfs.py "${ROOTFS_DIR}"
# Native rootfs proof: installed build identity must be a root-owned,
# symlink-free exact file with bounded fixed fields and ALPHA NO-GO.
python3 - "${ROOTFS_DIR}/etc/audiohub/build-identity.json" <<'PY'
import json
import os
import re
import stat
import sys

path = sys.argv[1]
assert not os.path.islink(path)
meta = os.stat(path, follow_symlinks=False)
assert stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_nlink == 1
assert stat.S_IMODE(meta.st_mode) == 0o644 and 0 < meta.st_size <= 256
with open(path, encoding="ascii") as handle:
    value = json.load(handle)
assert type(value) is dict
assert set(value) == {"schema", "source_sha", "pi_gen_sha",
                      "ci_run_id", "hardware_verified", "release_approved"}
assert value["schema"] == "rivanox-audiohub-image-identity/1"
assert all(type(value[field]) is str and re.fullmatch("[0-9a-f]{40}", value[field])
           for field in ("source_sha", "pi_gen_sha"))
assert value["ci_run_id"] is None or (
    type(value["ci_run_id"]) is int and 0 < value["ci_run_id"] < 10**20)
assert value["hardware_verified"] is False and value["release_approved"] is False
print("Read-only offline image identity staged: format and ALPHA NO-GO verified.")
PY
# Check the ACTUAL ARM64 staged image, not just checked-in source:
# the operator command must be installed, executable and non-symlinked.
test -f "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
test -x "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
test ! -L "${ROOTFS_DIR}/usr/local/bin/audiohub-music"
test "$(stat -c '%a' "${ROOTFS_DIR}/usr/local/bin/audiohub-music")" = 755
# Install/execute the new operator-confirmed WAV backup/restore command.
test -f "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer"
test -x "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer"
test ! -L "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer"
test "$(stat -c '%a' "${ROOTFS_DIR}/usr/local/bin/audiohub-music-transfer")" = 755
# The preset CLI must be present as an actual executable, not a symlink.
test -f "${ROOTFS_DIR}/usr/local/bin/audiohub-presets-transfer"
test -x "${ROOTFS_DIR}/usr/local/bin/audiohub-presets-transfer"
test ! -L "${ROOTFS_DIR}/usr/local/bin/audiohub-presets-transfer"
test "$(stat -c '%a' "${ROOTFS_DIR}/usr/local/bin/audiohub-presets-transfer")" = 755
# Verify the new image ships an empty private folder for user-supplied WAVs.
test -d "${ROOTFS_DIR}/home/audiohub/PrivateMusic"
test ! -L "${ROOTFS_DIR}/home/audiohub/PrivateMusic"
test "$(stat -c '%a' "${ROOTFS_DIR}/home/audiohub/PrivateMusic")" = 700

# Generate only allowlisted public-facing package metadata; never export host secrets.
python3 files/rootfs_package_inventory.py \
  --rootfs "${ROOTFS_DIR}" \
  --output "${ROOTFS_DIR}/usr/share/doc/audiohub/ROOTFS-PACKAGES.json"
