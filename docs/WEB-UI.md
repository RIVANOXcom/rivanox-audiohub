# Web UI preview

A responsive, five-language control-panel **prototype** is available under `web/`. It is intentionally not yet connected to a privileged device-control API.

The source includes translations for `en`, `de`, `es`, `fr`, and `it`, using browser language detection and a manually selectable language. It provides mock per-source volume, mute and 3-band EQ sliders. The preview explicitly says that audio output is unaffected.

This prevents the repository from promising a working administration interface before secure device ownership and provisioning have been implemented. Audio does not require this page to remain open.

Security requirements for the future controller:

1. Device-specific first-claim secret without a universal shared password.
2. Authenticated settings mutations and protection against cross-site requests.
3. Local-network-only exposure with a safe AP provisioning process.
4. A reset/recovery path usable without a monitor or keyboard.
5. Device state/metadata protected from unauthenticated clients.
