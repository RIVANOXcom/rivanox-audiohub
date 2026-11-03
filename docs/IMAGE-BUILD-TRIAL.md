# Isolated image build experiment

This branch triggers a GitHub Actions build of an **unverified** Raspberry Pi 4 SD-card image. It does not create a GitHub Release.

Acceptance criteria for this trial:

1. The pinned 64-bit pi-gen revision is fetched successfully.
2. The Raspberry Pi OS Lite chroot and custom audio stage build successfully.
3. An `*.img.xz` file and SHA-256 checksum are produced as short-lived, explicitly unverified CI artifacts.
4. No shared setup password is introduced.
5. No hardware-compatibility or safety claims are made based on the CI build alone.

If the runner lacks sufficient disk space or ARM emulation support, record the exact failure and adjust the build method; do not bypass safety checks.

Branch: `audiohub-preview-build`
