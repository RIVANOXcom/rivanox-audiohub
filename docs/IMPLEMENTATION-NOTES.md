# Implementation notes

The initial checked-in Python module implements input validation, state defaults, PipeWire three-channel parametric filter-chain rendering, command construction, and safe speaker/source discovery. These are **unit-tested logic components**, not proof of working hardware routing.

The PipeWire filter-chain uses the documented `param_eq` builtin with independent nodes for each channel. The Edifier USB output is preferred when present. If multiple ambiguous USB outputs exist, automatic selection is disabled rather than redirecting audio to an unrelated USB peripheral.

Next engineering work:

- Dedicated non-root runtime and persistent user-level PipeWire/WirePlumber services
- Bluetooth pairing agent with ownership-safe claim process
- Route supervisor starting and restarting Bluetooth loopbacks
- Windows network-audio sink; dependency-specific notices and reproducible builds
- Local authenticated controller with translated messages
- Image builder and real Pi 4 hardware acceptance

Avoid interpreting a passing unit-test badge as proof of hardware operation.

## Corrupted device assignment recovery (source-only)

The runtime validates the local Bluetooth-to-channel mapping before using it. An entry must have a standard six-byte Bluetooth address and one of the two Bluetooth-assigned channels (`music` or `tablet`). Duplicate channel claims, duplicate normalized addresses, unhashable values, and unexpected JSON shapes are ignored instead of crashing polling. Only valid entries are retained in memory; invalid on-disk mapping files are **not** automatically overwritten. A later successful assignment from a valid detected source can persist a clean mapping through the existing atomic writer. This avoids silently destroying local recovery evidence solely because the source file is malformed.

This is a defensive software change, not verified Bluetooth pairing, reconnection, three-source playback, or Raspberry Pi 4 acceptance. Physical fault-injection and recovery testing remain mandatory.
