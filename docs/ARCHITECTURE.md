# Audio architecture

Target: Raspberry Pi 4, Raspberry Pi OS Lite 64-bit, PipeWire/WirePlumber, BlueZ, and a local web application.

```text
Bluetooth phone ------> music input ------> music EQ/gain ---+
Windows laptop --------> laptop input -----> laptop EQ/gain --+--> master limiter/volume --> Edifier USB speaker
Tablet / other source -> tablet input -----> tablet EQ/gain --+
```

Independent virtual sinks are intended to prevent one source's EQ and gain from modifying another source. The final system must expose measured route status and prevent output clipping when signals are mixed.

## Source-gain budget (experimental; not a limiter)

The headless source supervisor now requests a *conservatively attenuated* USB master volume instead of applying the full requested master percentage unconditionally. It treats all three unmuted channels as potentially playing at full scale at the same time. For every channel, the estimated maximum amplitude is `volume/100 * 10^((sum of positive bass/mid/treble dB)/20)`; muted channels contribute zero. A budget multiplier of `min(1, 1/sum(amplitudes))` is then applied to the requested master volume. With three unmuted inputs at 100% and flat EQ, the master level is limited to one-third of the requested value. The estimate deliberately does not depend on current Bluetooth connections, so a network/laptop stream cannot unexpectedly bypass the budget.

This is **not** a hard peak limiter or a guarantee of no clipping: the response of the running filter chain, PipeWire mixing order, signal peaks, device gain staging, and actual R600USB audio have not been validated. Positive EQ boost is conservatively accounted for, including worst-case simultaneous band boosts. A genuine output limiter and measured three-input clipping acceptance remain mandatory for release. The UI controls remain a read-only prototype. EQ is currently generated during image setup; changing saved EQ values does not yet reload live PipeWire filters. Do not label this feature fully operational until those remaining tasks have hardware evidence.

Design decisions:

- Keep the UI independent from audio playback so music does not stop when the browser closes.
- Favor network or wired laptop audio for consistent latency.
- Treat two parallel Bluetooth A2DP streams as experimental until physically demonstrated.
- Use LAN when available; provisioning Wi-Fi must not require a keyboard or monitor.
- Pairing should match the simplicity of a consumer Bluetooth receiver while closing unauthorized re-pairing after ownership is established.
- Separate security-sensitive privileged network/Bluetooth management from unprivileged audio mixing.

Development and threat-model details are refined as tests reveal behavior.
