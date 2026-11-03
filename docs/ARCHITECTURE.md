# Audio architecture

Target: Raspberry Pi 4, Raspberry Pi OS Lite 64-bit, PipeWire/WirePlumber, BlueZ, and a local web application.

```text
Bluetooth phone ------> music input ------> music EQ/gain ---+
Windows laptop --------> laptop input -----> laptop EQ/gain --+--> master limiter/volume --> Edifier USB speaker
Tablet / other source -> tablet input -----> tablet EQ/gain --+
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
