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

## Read-only on-device status preview (experimental)

The image-builder installs five-language web assets under `/opt/audiohub/web` and starts an unprivileged Python HTTP service on port `8765`. **Until authenticated ownership and a protected API are available, the status preview binds to `127.0.0.1:8765` by default.** This is intentionally **not** a usable phone-based setup portal; `http://audiohub.local:8765/` is *not* available from another device in the default image. A remote browser cannot access the current local-only preview.

Only an authorized engineer testing on an isolated trusted LAN can manually configure `AUDIOHUB_STATUS_BIND_IP=<a specific RFC1918 IPv4 address>` together with `AUDIOHUB_UNSAFE_STATUS_LAN=YES` in the process environment. The image's systemd unit **does not** set this opt-in. Public, multicast, wildcard (`0.0.0.0`), link-local and hostname bind targets are rejected even with the flag. The insecure exception is **not** owner enrollment and has no sender/client authentication; never use it for production, Internet or untrusted LAN access. Disabling LAN-by-default is a deliberate security/preview usability tradeoff, not evidence of a finished consumer first-boot path.

Only GET requests for strict allowlisted UI assets and `/api/status` work. The status endpoint exposes a whitelisted, redacted subset of runtime health (USB recognized, route counts, virtual channel count and freshness), not Bluetooth addresses, SSID, credentials or settings. All POST/PUT/PATCH/DELETE requests fail closed with HTTP 405. There is no authenticated write API yet, and visual volume/EQ controls remain demonstrations.

Never forward port 8765 to the public Internet. Device ownership, authenticated controls and secure Wi-Fi provisioning remain release blockers. This experimental integration requires Pi image rebuilding and hardware validation before being considered operational.
