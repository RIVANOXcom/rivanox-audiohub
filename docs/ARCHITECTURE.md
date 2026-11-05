# Audio architecture

Target: Raspberry Pi 4, Raspberry Pi OS Lite 64-bit, PipeWire/WirePlumber, BlueZ, and a local web application.

```text
BT source #1 -------> Input 1 (internal: music) ---> EQ/gain --+
Manual LAN sender ---> Input 2 (internal: laptop) --> EQ/gain --+--> conservative gain budget/master --> USB speaker
BT source #2* -------> Input 3 (internal: tablet) --> EQ/gain --+
* Second simultaneous Bluetooth A2DP input is hardware-UNVERIFIED.
```

Independent virtual sinks are intended to prevent one source's EQ and gain from modifying another source. The final system must expose measured route status and prevent output clipping when signals are mixed.

Design decisions:

- Keep the UI independent from audio playback so music does not stop when the browser closes.
- Favor network or wired laptop audio for consistent latency.
- Treat two parallel Bluetooth A2DP streams as experimental until physically demonstrated.
- Use LAN when available; provisioning Wi-Fi must not require a keyboard or monitor.
- Pairing should match the simplicity of a consumer Bluetooth receiver while closing unauthorized re-pairing after ownership is established.
- Separate security-sensitive privileged network/Bluetooth management from unprivileged audio mixing.

Development and threat-model details are refined as tests reveal behavior.

## Stable technical channels versus owner-visible labels

The `music/laptop/tablet` identifiers are **internal PipeWire route keys**
and retained for backward compatibility, **not an obligation to attach a
phone, laptop, or tablet**. Display names are user-defined generic
`Input 1/2/3` labels. A future authenticated controller must keep
names, source identities and input transport bindings as three distinct
state concepts: a rename is not a Bluetooth pairing authorization,
a transport change or a network listener enable.

Draft PR #26 supplies browser-local preview labels and separate private
Pi-local CLI name storage; neither changes an active stream. Existing
engineering code has a maximum of two Bluetooth A2DP receiver routes
and one dormant, untrusted manual Scream UDP PCM route. Arbitrary
source/transport reassignment needs explicit collision-safe owner
validation plus real Pi4 device tests. The master is a conservative
linear gain budget, **not a measured true-peak limiter**. There is no
working authenticated phone UI yet.

See [PROJECT-HANDOFF.md](PROJECT-HANDOFF.md) and
[ENGINEERING-BACKLOG.md](ENGINEERING-BACKLOG.md) for exact gated work.

## Offline flexible source routing (Draft PR #29)

The internal sink identifiers stay fixed for compatibility but the
engineering route policy is not a permanent product/device category:

- `music`, `laptop`, `tablet` are three stable EQ slots, shown
  as independently renameable Input 1/2/3 in browser preview.
- The private `source-routes.json` policy reserves exactly **one**
  of these slots for the **manually** launched LAN receiver. Up to
  two explicitly configured Bluetooth source MACs may be assigned
  to distinct **remaining** slots; the legacy default auto mode
  preserves old BT1/BT2 + LAN-slot behavior.
- The BT supervisor reloads this policy each poll, closes/replaces
  managed capture loopbacks when reassigned, and denies all BT routes
  when the local policy is invalid or unsafe.
- The isolated manual Windows PCM receiver pins the configured LAN
  sink after private policy validation; if the policy changes while
  the receiver runs, the receiver exits rather than flowing into
  another channel. UDP remains **off by default**, plaintext,
  unauthenticated and source-IP-spoofable.
- A label is independent of route assignment, and an assigned
  MAC is NOT proof of a trusted/paired owner device. There is no
  user-facing authenticated API or validated Pi4 source switching yet.

Implementation details and console lab commands:
[FLEXIBLE-SOURCE-ROUTING-LAB.md](FLEXIBLE-SOURCE-ROUTING-LAB.md).
