#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Build ONLY an unverified development image. Never publish as a stable release.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="c851f00178c64b87a86c06c2be216bd89d62e55b"
WORK="${AUDIOHUB_BUILD_DIR:-$ROOT/.pi-gen-build}"
if [[ "${AUDIOHUB_BUILD_ACCEPT_PREVIEW:-}" != "YES" ]]; then
  echo "Refusing unverified image build. Set AUDIOHUB_BUILD_ACCEPT_PREVIEW=YES." >&2
  exit 2
fi
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Linux build system required." >&2; exit 2
fi
for command in git python3 debootstrap qemu-aarch64-static parted xz; do
  if ! command -v "$command" >/dev/null; then
    echo "Missing required tool: $command" >&2; exit 2
  fi
done
mkdir -p "$WORK"
if [[ ! -d "$WORK/pi-gen/.git" ]]; then
  git init -q "$WORK/pi-gen"
  git -C "$WORK/pi-gen" remote add origin https://github.com/RPi-Distro/pi-gen.git
fi
git -C "$WORK/pi-gen" fetch --depth=1 origin "$PIN"
git -C "$WORK/pi-gen" checkout -q --detach FETCH_HEAD
test "$(git -C "$WORK/pi-gen" rev-parse HEAD)" = "$PIN"
cp -a "$ROOT/image/stage-audiohub" "$WORK/pi-gen/"
rm -rf "$WORK/pi-gen/stage-audiohub/01-install/files/src"
install -d "$WORK/pi-gen/stage-audiohub/01-install/files/src"
cp -a "$ROOT/src/audiohub" "$WORK/pi-gen/stage-audiohub/01-install/files/src/"
rm -rf "$WORK/pi-gen/stage-audiohub/01-install/files/web"
install -d "$WORK/pi-gen/stage-audiohub/01-install/files/web"
cp -a "$ROOT/web/." "$WORK/pi-gen/stage-audiohub/01-install/files/web/"
touch "$WORK/pi-gen/stage2/SKIP_IMAGES"
cat > "$WORK/pi-gen/config" <<'CONFIG'
IMG_NAME='AudioHub-Pi4-UNVERIFIED'
PI_GEN_RELEASE='AudioHub ALPHA – unverified test build'
RELEASE='trixie'
FIRST_USER_NAME='audiohub'
DISABLE_FIRST_BOOT_USER_RENAME=1
TARGET_HOSTNAME='audiohub'
ENABLE_SSH=0
LOCALE_DEFAULT='en_US.UTF-8'
TIMEZONE_DEFAULT='Europe/Berlin'
WPA_COUNTRY='DE'
STAGE_LIST='stage0 stage1 stage2 stage-audiohub'
DEPLOY_COMPRESSION='xz'
CONFIG
printf "FIRST_USER_PASS='%s'\n" "$(openssl rand -hex 32)" >> "$WORK/pi-gen/config"
echo "pi-gen SHA: $PIN"
echo "Building unverified pi image. This may need >30 GB of free disk space."
(cd "$WORK/pi-gen" && sudo ./build.sh)
find "$WORK/pi-gen/deploy" -maxdepth 1 -type f -printf '%f\n'
