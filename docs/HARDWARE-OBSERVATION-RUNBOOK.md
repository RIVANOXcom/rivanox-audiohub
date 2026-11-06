# AudioHub ALPHA — offline Pi4 + Edifier manual hardware observation

**Status: developer testing only; not a public release, ownership proof, safety certification, or commercial license approval.** The current public code remains AGPL-3.0-only. The human observations below cannot override the release/Model C gates.

## Prerequisites

Use an isolated Raspberry Pi 4 developer bench, real Edifier R600USB USB speakers and the **UNVERIFIED** experimental image from GitHub Actions if independently assessed safe for your lab. Start at low volume. Ensure PipeWire, WirePlumber and the AudioHub user services run, and physically connect the speakers. Existing topology-only checks are NOT proof that sound is actually audible.

Do not expose the read-only alpha web UI or the unauthenticated experimental laptop PCM receiver to the Internet. Do not test unknown Bluetooth devices on a production network.

## Run from the Pi's local owner-controlled terminal

First inspect the read-only, redacted PipeWire topology:

```bash
sudo -u audiohub env XDG_RUNTIME_DIR="/run/user/$(id -u audiohub)" PYTHONPATH=/opt/audiohub/src /usr/bin/python3 -m audiohub.hardware_preflight
```

Only when topology prerequisites are detected, run the interactive observation checklist:

```bash
sudo -u audiohub env XDG_RUNTIME_DIR="/run/user/$(id -u audiohub)" PYTHONPATH=/opt/audiohub/src /usr/bin/python3 -m audiohub.manual_acceptance
```

This tool **never starts playback**, changes volume, pairs a Bluetooth device, opens a network socket or writes a report. The person at the bench must independently operate each applicable audio source and confirm what they physically heard. Answers: `yes`, `no`, or `skip`. Invalid strings are discarded, not stored. The tool prints fixed, privacy-bounded JSON to the local console. If topology is incomplete, it asks no audio questions and exits with code 2.

## What the operator actually checks

1. Real Edifier speaker playback is **audible** at safe volume.
2. Bluetooth sources and the manually authorized laptop input can operate together on separate channels **only in a controlled lab**.
3. Per-channel mute and equalizer changes affect **only their intended input**.
4. Removing the USB audio device promptly disables routes, without HDMI or other unsafe fallback.
5. The mixed sound does not exhibit obvious clipping during the chosen low-volume test.
6. The separate **24-hour endurance test** has truly been performed. Answer `skip` if not yet completed.

A `yes` is an **operator's observation**, not measurement, calibrated audio testing, independent certification, cryptographic ownership, a right to distribute third-party software, or a completed legal review. The JSON **always** contains `hardware_accepted=false`, `ownership_authenticated=false`, `release_ready=false`, `legal_redistribution_approved=false`, and `model_c_license_effective=false` even when every human answer is affirmative. Exit code 0 only means the checklist produced a report.

For support/debugging, share only the redacted JSON after personally reviewing it. Do not send passwords, MAC addresses, unique serial numbers, screenshots with account details, raw `pw-dump` or private system logs.

## Blocking decisions after a manual session

Do not ship an SD card or flip license/rights flags. Hardware acceptance needs independently reviewed device results and secure owner claiming. Commercial release also requires the RIVANOX rightsholder's legal review and the nine remaining Raspberry Pi OS notice-path checks, including `raspberrypi-net-mods`. Owner-created PRIVATE future Model C repository is tracked in issue #37; source rights issue #32, OS rights #40 and actual Pi4/Edifier acceptance #2 remain open.

**Related:** [PAPA canonical recovery](PAPA_CANONICAL_RESUME_20261105.md), [Draft PR #48](https://github.com/RIVANOXcom/rivanox-audiohub/pull/48).
