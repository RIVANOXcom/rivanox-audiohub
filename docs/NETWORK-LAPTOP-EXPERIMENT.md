# Windows laptop audio over LAN — development prototype (AH-002)

Status: **SOURCE PROTOTYPE ONLY. Not deployed, not auto-enabled, not a release.**

## Goal and selected wire format

The existing three virtual PipeWire sinks are `audiohub.music`, `audiohub.laptop`, and `audiohub.tablet`. This source-only receiver prototype accepts an explicitly chosen Windows host's legacy Scream UDP packets and forwards stereo PCM **only** to `audiohub.laptop` with `pw-cat --target=audiohub.laptop`. It does not mix packets into the Bluetooth capture node and does not change the system default sink.

Scream is an external Windows virtual sound-card project: https://github.com/duncanthrax/scream. Its legacy UDP protocol uses a five-byte format header followed by up to 1152 bytes of interleaved PCM. This prototype deliberately accepts only **48,000 Hz, 16-bit little-endian, two-channel PCM** with a stereo (3) or unspecified (0) channel mask. Other sampling rates, widths, layouts and malformed/oversized/unaligned packets are dropped. There is no automatic resampling, codec transcoding, packet sequence number, encryption or sender authentication.

`pw-cat` is part of PipeWire and supports raw PCM from stdin with an explicit target, format, sample rate and channel count (see https://man.archlinux.org/man/pw-cat.1.en). The implementation imports no Scream source code or Windows driver; any independently distributed Scream software retains its upstream MS-PL license and must be reviewed before packaging.

## Deliberately manual test (engineers only)

**Never expose the receiver to an untrusted network or the public Internet.** UDP source IP filtering is not strong authentication and can be spoofed on some LANs. The receiver is not a solution to the mandatory device ownership claim. Do not deploy this receiver as a service or include it in a consumer image until an authenticated enrollment and isolation strategy is approved.

For an isolated developer setup, after separately configuring PipeWire with the three AudioHub sinks and a recognized USB output:

1. Configure a trusted Windows Scream sender explicitly for **48 kHz / 16-bit / stereo**, **unicast** to the test Pi's private IPv4 address, UDP port **4010**. Consult the upstream Scream instructions for the installed Windows driver revision. Do not assume Scream is a Windows built-in feature.
2. Choose one known Windows sender IP and one Pi interface IP, both private addresses. On the intended test Pi, with the dedicated unprivileged audio user and a functioning PipeWire user session, run manually:

   ```bash
   PYTHONPATH=src python3 -m audiohub.network_laptop \
     --sender-ip 192.168.1.10 --bind-ip 192.168.1.20 \
     --port 4010 --unsafe-lan-test
   ```

   Replace these **documentation-only example addresses** with the actual local test values. The program refuses to bind without the explicit unsafe-test flag, rejects public senders/bind IPs, and checks for both `audiohub.laptop` and an eligible USB sink before opening the UDP socket.
3. Stop the manual process after the test. Do not configure a port forward, automatic systemd startup, public bind, remote access, or network-wide discovery.

No passwords, device identities or sender addresses are written to a status file by this prototype. It does not control the web UI and has no unattended setup path.

## Source checks and known limitations

- Tests validate legacy Scream framing and exact stereo PCM handoff, reject non-target senders and unsupported formats, and mock PipeWire presence/absence and the targeted `pw-cat` launch.
- Valid frames are sent to the unprivileged `pw-cat` process using nonblocking, bounded writes. A stalled pipe drops frames rather than accumulating an unlimited queue. On broken pipes, the player can restart after a brief backoff.
- This does **not** implement a true jitter buffer, packet-loss concealment, trusted sender authentication, guaranteed stream identity, reconnect metrics, rate adaptation, real-time clock drift correction, or live mixer status. The UDP protocol has no packet sequence numbers or retransmission. Consequently latency, dropouts, and simultaneous source performance are still unverified.
- The receiver is not installed as a systemd service and is never started by the image installer. It cannot by itself satisfy the flash-and-boot usability target or secure phone-based onboarding.

## Required physical validation before any merge/release claim

Record exact image and source hashes, USB device and Pi revision, Windows and Scream versions, sender configuration, PipeWire and `pw-cat` versions, and redacted logs. Test the real `audiohub.laptop` channel with the Edifier USB speakers. Independently start phone Bluetooth and a third supported input; prove three-way simultaneous output, channel separation, mute/volume/EQ isolation, peak-limiter behavior, unplug/replug, network drop/recovery, power cycling, browser-closed playback, and at least 24 hours endurance. Treat dual Bluetooth as conditional. An authorized owner enrollment/security model and legal review are mandatory before enabling a network receiver by default.

Tracking: PAPA project `PJ2611-0001:R001`, AH-002 requirement 3268, GitHub issue #3.
