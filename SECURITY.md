# Security Policy

## Reporting vulnerabilities

Do not disclose a vulnerability through a public GitHub issue. Use GitHub's **Report a vulnerability** feature when enabled; otherwise contact [RIVANOX Support](https://rivanox.com/support/) with a request for a private security reporting channel. Do not send secrets or exploit details through public forms.

## Supported versions

No general-availability version exists. Preview builds are for controlled research only. Hardware-specific exploits, exposed setup credentials, Bluetooth pairing bypass, network exposure, and persistence problems are considered release-blocking issues.

## Security principles

- No remotely accessible default administrative password in a public release.
- No permanent unrestricted Bluetooth pairing after device ownership is established.
- Web settings require authenticated access and protection against cross-origin changes.
- No public Internet access, port forwarding, or cloud telemetry by default.
- Per-device onboarding must be usable without SSH or an attached display.
- Never publish an SD image until physical boot, input, output and recovery tests have passed.

Security fixes may be published independently of feature releases. There is no promised response time for this alpha project.

## Preview status/web local-file security baseline (2026-11-05)

The experimental HTTP service is **read-only and loopback-bound by default**;
manual non-loopback binding is an unauthenticated development exception,
not a supported remote management interface. It cannot claim the Pi owner
or change Bluetooth/audio settings.

Static web assets are selected by an allowlist of fixed URLs. Runtime reads
must reject all symlinked path components, FIFOs/devices, empty or oversized
files (512 KiB maximum for any static asset). The runtime status JSON must
also be read as a bounded (32 KiB), ordinary non-symlinked file; malformed,
overlarge, removed or otherwise unsafe status must report **stale/false**
health with zero counters, never raw identifiers or user secrets.

The native Pi rootfs pre-export audit now rejects nonregular, symlinked,
empty or oversized installed web assets, and checks the installed Python
handler retains bounded nofollow reads. Automated source and image tests
are necessary but are not proof of physically secure owner enrollment,
network threat resistance, Pi4/Edifier sound, legal redistribution rights
or GA readiness. Never expose the alpha web port on the public Internet.

## Private runtime JSON persistence (2026-11-05 development)

Historical AudioHub alpha `runtime.py` wrote user-assignment and status
JSON through a predictable `.tmp` pathname and read JSON without a size
or symlink guard. [Draft PR #44](https://github.com/RIVANOXcom/rivanox-audiohub/pull/44)
changes this legacy AGPL path to open directories by non-symlinked
file descriptors, require private owner permissions, bound input/output
to 32KiB, reject special/hardlinked/foreign-owned targets, and publish
only via 0600 randomly named exclusive atomic temp files plus fsync.
A failed read falls back to safe defaults rather than accepting
partially parsed or untrusted local configuration.

The source and native ARM64 tests must be independently checked at the
exact PR #44 SHA. These controls do not create owner enrollment, network
authentication, firmware license permission or a stable device release.

## Managed audio route cleanup after unexpected failure

In the legacy headless alpha runtime, an unexpected poll error was
previously caught without necessarily stopping already-created
`pw-loopback` child processes. [Draft PR #45](https://github.com/RIVANOXcom/rivanox-audiohub/pull/45)
adds guarded cleanup of all managed routes on errors and service exit.
Cleanup failures are escalated instead of silently ignored; the
`audiohub-runtime.service` systemd unit explicitly uses
`KillMode=control-group` so any unresponsive child belongs to a
service cgroup stopped on restart. Source and native ARM64 validation
must be checked at exact CI SHAs. This does not prove the audio
amplifier/mixer hardware route is safe or secure owner enrollment.

## Bluetooth automatic trust is limited to recent agent authorization

Legacy pairing initially accepted an arbitrary BlueZ `Device1.Paired` event
as grounds to mark that device `Trusted`, even without a preceding explicit
audiohub agent RequestAuthorization callback. [Draft PR #46](https://github.com/RIVANOXcom/rivanox-audiohub/pull/46)
requires matching in-memory one-use authorizations (45 seconds; at most two),
true current BlueZ Paired property and BlueZ-origin signal filtering before
grading trust. Existing trusted devices can reconnect after the discovery
window; untrusted clients cannot authorize services solely from open
discovery. Agent Release clears pending requests. The temporary firstboot
window is **not ownership verification**. Native Pi/BlueZ hardware tests,
secure owner claiming and legal release signoff remain OPEN.

## Bounded Bluetooth adapter discovery after agent crashes

Official BlueZ Adapter1 documentation defines PairableTimeout=0 and
DiscoverableTimeout=0 as unlimited. Legacy AudioHub set unlimited
DiscoverableTimeout, which could leave pairing discoverability open after
an agent crash. Draft PR #46 configures finite 600-second timeouts for
**both** Adapter1 properties, first closes previously discoverable and
pairable adapter states, and uses Linux monotonic boot-relative deadline
instead of a fresh timeout on every systemd restart. This is a defense in
depth for the alpha guest pairing window, **not** secure authenticated
owner enrollment. Confirm exact native run + real device behavior before
enabling general availability.

## Bounded PipeWire process output (legacy ALPHA safety maintenance)

The original `runtime.run()` and offline `hardware_preflight.probe()`
used `subprocess.run(capture_output=True)` to acquire arbitrary `pw-dump`
text, with no stdout byte cap. Draft [PR #47](https://github.com/RIVANOXcom/rivanox-audiohub/pull/47)
uses `selectors` for bounded incremental capture (4MiB max), requires a
strict process timeout, kills its own process group when rejected, launches
with an argv list and `shell=False`, discards stderr to avoid leaking
Bluetooth/USB IDs, and refuses invalid UTF-8. The graph parser also caps
object count at 8192. An oversized or broken query yields no trusted
readout; playback routing continues to fail closed. The native Pi image
must pass the new pre-export security guard in addition to unit tests.
These are NOT proofs of real audible playback, secure ownership, legal
rights or stable product readiness.

## Physical hardware observation is NOT automatic acceptance (legacy alpha)

Draft PR #48 adds `audiohub.manual_acceptance`, an offline local-console
checklist for real Edifier USB sound, multi-input mixing, channel isolation,
USB unplug failsafe, clipping and a separate 24-hour endurance test. It
asks only after the non-mutating PipeWire topology preflight succeeds.
Answers are fixed yes/no/skip values; user-entered text/identifiers are
discarded; it writes no files, starts no network listeners and neither
pairs devices nor drives audio. Reports cannot flip the existing false
hardware, ownership, commercial license or release flags, even if every
answer is yes. This does not replace independent Pi4 device testing.
See docs/HARDWARE-OBSERVATION-RUNBOOK.md.

## PipeWire duplicate routing identity refusal (legacy alpha)

The original `virtual_sinks()` silently overwrote repeated virtual sink
names and `bluetooth_sources()` accepted the first valid candidate MAC
profile. Draft PR #49 now refuses globally repeated PipeWire Node IDs,
duplicate virtual mixer sink names and repeated Bluetooth source addresses;
the existing supervisor stops its managed players when it cannot trust
virtual sinks. The read-only hardware topology and graph-link report also
refuse positive evidence when Node IDs collide. Tests include malformed
node metadata and legitimate distinct addresses. This is source/in-image
safety maintenance, not a completed Pi4/Edifier physical audio test.

## Privileged offline diagnostic runtime path hardening

The system-owned `firstboot_diag` service must never follow an attacker-
controlled symlink in a parent component of an unprivileged user's status
path. Draft PR #50 opens every absolute directory component using
`O_DIRECTORY|O_NOFOLLOW` via directory FDs and validates the last
runtime directory and status file are owned by the expected audiohub UID
and have no group/other rights. Hardlinks, invalid user IDs, traversal,
missing or overlarge JSON fail as stale; no identifiers are exported.
Tests verify valid existing private runtime status remains readable and
unsupported inputs cannot make a report appear healthy. Offline report
still means observation ONLY, no authentication, warranty or release.

## Experimental laptop LAN receiver must not buffer unlimited PipeWire output

The source-only, explicitly opted-in, UNAUTHENTICATED Windows Scream UDP
receiver previously called `subprocess.run(capture_output=True)` for both
`pw-dump` graph inspection and `wpctl set-default` in periodic readiness
checks. Draft PR #51 replaces those with the same standard-library bounded
capture already used by the live supervisor: 4MiB total stdout, 5-second
command timeout, no shell, discarded stderr, process-group termination on
failure. Missing/oversized/corrupt graph data prevents `wpctl` or playback;
failed `wpctl` also denies readiness. The receiver is still disabled
unless an operator explicitly launches the unsafe LAN experiment. This is
not cryptographic network peer authentication, a secure consumer service,
real Edifier sound validation or public release approval.

## Alpha status HTTP worker exhaustion and log privacy

Python's default ThreadingHTTPServer spawns a thread for every accepted
connection. The original read-only AudioHub status preview also inherited
BaseHTTPRequestHandler.log_message, which logs raw URL paths/query data to
systemd stderr. Draft PR #52 caps accepted request workers to 8 with a
nonblocking BoundedSemaphore, bounds socket reads to 5 seconds, closes extra
connections, releases worker slots even on failures, and suppresses
attacker-supplied request-line logging. The service continues to bind
only to local IPv4 loopback unless an engineer explicitly opts into an
unsafe specific RFC1918 interface. The GET/API remains read-only; the
new controls are resource safety and privacy improvements, NOT authentication
or permission to expose the preview to the Internet.
