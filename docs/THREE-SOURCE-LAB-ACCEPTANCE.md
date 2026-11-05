# AudioHub three-source laboratory acceptance – ALPHA ONLY

The new alpha image **contains** a manual Windows UDP PCM receiver, but it
**does not start any network listener during boot**. This is deliberate:
legacy Scream UDP is unencrypted, has no sender authentication, and host
source-IP checks are spoofable. Neither the Windows driver nor admin login
are installed/configured by AudioHub. **Do not connect this unclaimed
prototype to a household, workplace, internet-routed or production LAN**.

Source-only and image CI tests are no substitute for actual Raspberry Pi4
plus Edifier R600USB speaker tests. No official release or claim of a
working three-source appliance exists.

## Test 1: no-network flash/boot baseline (operator)

1. Download a **specific** proven GitHub Actions image ZIP for the
   integration branch, sign in if asked, verify the image SHA256 against
   the accompanying `SHA256SUMS.txt`, then flash the `.img.xz` to a
   **spare** SD using Raspberry Pi Imager **Use custom**. This erases
   the selected SD; do not overwrite personal storage.
2. With no Ethernet or provisioned WLAN, connect Edifier R600USB by USB
   and power on the Pi4. Discover/pair phone `AudioHub` via Bluetooth
   during the first pairing window. Start quiet test music; note whether
   any real sound comes from Edifier.
3. Keep the device running for 10 minutes, power off fully, remove SD,
   and read `AUDIOHUB-TEST-REPORT.json` from the FAT boot partition.
   The report contains bounded aggregate metrics only and is mutable,
   not signed or acceptance proof.
4. Record actual device model, yes/no for pair and audible output,
   USB present/ready, audio route counts and any failure counters.
   **No report** means missing evidence, not necessarily a failed boot.
5. A freshly flashed alpha should not bind a Windows Scream UDP
   receiver. Source and pre-export tests prohibit a service registering
   `audiohub.network_laptop` or `--unsafe-lan-test` at startup.

## Test 2: independent Windows channel (separate isolated bench only)

This step requires an **authorized, separately prepared** Windows
sender and physically isolated two-device test LAN. A switch with
no uplink and manually configured test-only RFC1918 addresses is one
option. These are examples only, **not** real operator addresses:
Pi `192.168.55.20`, Windows `192.168.55.10`.

Prerequisites: a genuine locally tested Pi boot with a recognized USB
speaker and a running `audiohub` PipeWire user session; an operator
capable of launching a terminal **locally** on the test Pi; a Windows
Scream driver installed by the Windows owner from its official release
after independent license/security review, set deliberately to
**48,000 Hz / S16LE / stereo / unicast** with the Pi's test address
and UDP 4010. Upstream Scream defaults to multicast and will not
work with this unicast-only receiver without manual sender setup.
AudioHub never modifies Windows drivers, registry or firewall.

On the isolated Pi as the unprivileged audiohub PipeWire user,
deliberately start the development receiver:

```sh
PYTHONPATH=/opt/audiohub/src python3 -m audiohub.network_laptop \
  --sender-ip 192.168.55.10 --bind-ip 192.168.55.20 \
  --port 4010 --unsafe-lan-test --prefill-packets 3 --diagnostics
```

No API or unauthenticated web page enables this command. Without the
unsafe opt-in, without an exact private/loopback bind IP, with
`0.0.0.0`, or without the `audiohub.laptop` EQ sink plus successful
`wpctl set-default` to recognized USB output, startup **fails**.
The process exits with Ctrl-C; do not configure auto-start or port
forwarding. The receiver uses a maximum of 16 × 1152-byte PCM frames
(18,432 bytes), drops oldest on saturation and does not reconstruct
packet losses or clock drift. Diagnostic stderr prints only counters:
accepted/foreign/invalid packets, drop/backpressure and player failure.

Current phone-first provisioning and an authenticated terminal path do
not exist; this manual procedure is intentionally **not** a usable
consumer setup path. Do not weaken device security to make it easier.

## Test 3: three-way mix once each path passes independently

With the isolated bench and two real *independently accepted*
Bluetooth sources, test music, laptop and tablet concurrently. The
Pi4 Bluetooth controller's ability to receive two separate A2DP
streams is **not established**; if it cannot, record a hardware
capability blocker rather than pretending three-way success.

Check these distinct functions with low physical volume before
any full-level measurements:

| Channel | Source | Expected dedicated sink |
|---|---|---|
| Music | First Bluetooth phone | `audiohub.music` |
| Laptop | Manually permitted Windows LAN Scream | `audiohub.laptop` |
| Tablet | Second Bluetooth sender, only if supported | `audiohub.tablet` |

Measure: individual mute and volume isolation, independent EQ, 10
manual unplug/reconnect cycles for USB, Bluetooth disconnect/rejoin,
Windows packets stopped/resumed, audible routing to Edifier only (not
HDMI), routing recovery, and recording of bounded failures. For a
future production build, also capture measured latency, full-level
true-peak clipping and a 24-hour soak. Conservative software mix
gain limiting is **not** a real peak limiter, and no hardware metric
has been signed off.

## Release and trust gates

No physical owner authentication, trusted phone Wi-Fi onboarding,
network sender authentication, dual-A2DP hardware proof, Windows
driver license acceptance, product distribution approval or official
release. The separate prior Windows PRs #11/#12/#19 remain unmerged
and unmodified; this branch ports their reviewed source into the
complete image test pipeline and **adds internal socket opt-in and
USB-default selection enforcement**. Any accepted production design
needs a different authenticated transport or a separately approved
trusted-LAN model.

Tracking: PAPA PJ2611-0001:R001; AH-002 #3268, AH-003 #3269,
AH-005 #3271, AH-009 #3275, GitHub issues #1/#2/#3.
