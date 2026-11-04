# Windows laptop audio over LAN — development prototype (AH-002)

Status: **SOURCE PROTOTYPE ONLY. Not deployed, not auto-enabled, not a release.**

## Goal and selected wire format

The existing three virtual PipeWire sinks are `audiohub.music`, `audiohub.laptop`, and `audiohub.tablet`. This source-only receiver prototype accepts an explicitly chosen Windows host's legacy Scream UDP packets and forwards stereo PCM **only** to `audiohub.laptop` with `pw-cat --target=audiohub.laptop`. It does not mix packets into the Bluetooth capture node and does not change the system default sink.

Scream is an external Windows virtual sound-card project: https://github.com/duncanthrax/scream. Its legacy UDP protocol uses a five-byte format header followed by up to 1152 bytes of interleaved PCM. This framing and the sample-rate marker were cross-checked against upstream `Receivers/unix/network.h`, `Receivers/unix/network.c`, and `Receivers/unix/pulseaudio.c` (https://github.com/duncanthrax/scream/tree/master/Receivers/unix): marker `1` means 48 kHz, while a marker with bit 7 set selects the 44.1-kHz family. This prototype deliberately accepts only **48,000 Hz, 16-bit little-endian, two-channel PCM** with a stereo (3) or unspecified (0) channel mask. Other sampling rates, widths, layouts and malformed/oversized/unaligned packets are dropped. There is no automatic resampling, codec transcoding, packet sequence number, encryption or sender authentication.

`pw-cat` is part of PipeWire and supports raw PCM from stdin with an explicit target, format, sample rate and channel count (see https://man.archlinux.org/man/pw-cat.1.en). The implementation imports no Scream source code or Windows driver; any independently distributed Scream software retains its upstream MS-PL license and must be reviewed before packaging.

## Deliberately manual test (engineers only)

**Never expose the receiver to an untrusted network or the public Internet.** UDP source IP filtering is not strong authentication and can be spoofed on some LANs. The receiver is not a solution to the mandatory device ownership claim. Do not deploy this receiver as a service or include it in a consumer image until an authenticated enrollment and isolation strategy is approved.

For an isolated developer setup, after separately configuring PipeWire with the three AudioHub sinks and a recognized USB output:

1. Configure a trusted Windows Scream sender explicitly for **48 kHz / 16-bit / stereo**, **unicast** to the test Pi's private IPv4 address, UDP port **4010**. **Scream defaults to multicast `239.255.77.77:4010`, which this manual prototype intentionally does not listen to.** Upstream `README.md` documents manual Windows registry `UnicastIPv4` / `UnicastPort` settings and a Windows reboot for opting into unicast. That driver configuration, installation and any administrator action must be performed separately and deliberately by the Windows owner; nothing in AudioHub performs it. Consult the upstream Scream instructions for the installed Windows driver revision. Do not assume Scream is a Windows built-in feature.
2. Choose one known Windows sender IP and one Pi interface IP, both private addresses. On the intended test Pi, with the dedicated unprivileged audio user and a functioning PipeWire user session, run manually:

   ```bash
   PYTHONPATH=src python3 -m audiohub.network_laptop \
     --sender-ip 192.168.1.10 --bind-ip 192.168.1.20 \
     --port 4010 --unsafe-lan-test \
     --prefill-packets 3 --diagnostics
   ```

   Replace these **documentation-only example addresses** with the actual local test values. The program refuses to bind without the explicit unsafe-test flag, rejects public senders/bind IPs, and checks for both `audiohub.laptop` and an eligible USB sink before opening the UDP socket.
3. Stop the manual process after the test. Do not configure a port forward, automatic systemd startup, public bind, remote access, or network-wide discovery.

No passwords, device identities or sender addresses are written to a status file by this prototype. It does not control the web UI and has no unattended setup path.

## Source checks and known limitations

- Tests validate legacy Scream framing and exact stereo PCM handoff, reject non-target senders and unsupported formats, and mock PipeWire presence/absence and the targeted `pw-cat` launch.
- Valid frames are sent to the unprivileged `pw-cat` process using nonblocking, bounded writes. A stalled pipe drops frames rather than accumulating an unlimited queue. On broken pipes, the player can restart after a brief backoff. A five-second sender idle interval closes the child playback process, and a three-second periodic PipeWire/USB inspection closes the player if the intended sink or recognized USB output disappears. These are source-level safeguards, **not** verified physical reconnect or device isolation.
- The new **bounded PCM packet queue** holds at most 16 packets (16 × 1152 = **18,432 bytes** maximum PCM payload) and discards the oldest packet when full; it never grows indefinitely or replays stale buffered frames after the player is stopped. For an 1152-byte stereo S16LE packet at 48 kHz, this upper capacity corresponds to 96 ms of nominal audio; this is a capacity bound, not a latency guarantee. The default prefill is one packet for backward compatibility; engineers may manually specify `--prefill-packets 3` (within 1–16) to test added jitter tolerance at the cost of startup latency. An unfilled prebuffer waits for more packets and may never start if a sender stops too early.
- With `--diagnostics` the receiver writes one machine-readable `audiohub.network { ... }` counters line to stderr every 60 seconds and upon termination. Counters distinguish received/accepted/invalid/foreign packets, queue overruns, write backpressure/failure, player starts/stops, idle shutdown and lost output. No address, device identity or PCM payload is logged. No SD-card file is written by these counters.
- This is a bounded **arrival-order packet queue**, **not** a sequence-aware jitter buffer or packet-loss concealment. It cannot reconstruct missing/late/reordered packets, authenticate sender identity, guarantee stream continuity or compensate clock drift. The UDP protocol has no packet sequence numbers or retransmission. Actual latency, packet loss, dropout recovery, and three-source performance remain unverified.
- The receiver is not installed as a systemd service and is never started by the image installer. It cannot by itself satisfy the flash-and-boot usability target or secure phone-based onboarding.

## Required physical validation before any merge/release claim

Record exact image and source hashes, USB device and Pi revision, Windows and Scream versions, sender configuration, PipeWire and `pw-cat` versions, and redacted logs. Test the real `audiohub.laptop` channel with the Edifier USB speakers. Independently start phone Bluetooth and a third supported input; prove three-way simultaneous output, channel separation, mute/volume/EQ isolation, peak-limiter behavior, unplug/replug, network drop/recovery, power cycling, browser-closed playback, and at least 24 hours endurance. Treat dual Bluetooth as conditional. An authorized owner enrollment/security model and legal review are mandatory before enabling a network receiver by default.

Tracking: PAPA project `PJ2611-0001:R001`, AH-002 requirement 3268, GitHub issue #3.
