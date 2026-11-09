# Experimental authenticated Windows LAN audio (not a release)

This manually activated experiment uses a Windows-local Scream UDP listener
bound to **127.0.0.1 only**, and a private Raspberry Pi TCP receiver over
**TLS 1.3**. The Pi certificate must match an out-of-band SHA256 DER pin.
A unique 32-byte shared secret proves the sender through a fresh server
nonce and HMAC-SHA256. No secret is transmitted on the network. The
receiver does not start PipeWire playback before successful authentication.

**Development only:** no Windows Scream driver, certificates, secrets,
unattended services, network discovery, phone onboarding, pairing, firewall
changes or main-branch release are supplied. On Windows, an existing
Scream driver must be manually configured for 48 kHz / S16LE / stereo
**unicast to 127.0.0.1:4010**. Its default multicast mode cannot feed this
bridge. This driver configuration is NOT verified on real Windows hardware.

## Threat boundary

One manually opted-in session, 1–30 whole minutes (10 default). The Pi
binds to an explicit RFC1918 interface, checks a specific Windows source
IP and accepts a single TLS connection. The Windows bridge accepts only
loopback UDP. A TLS certificate pin protects against another network
endpoint; the HMAC proof authenticates possession of the pre-shared key.
Scream on Windows itself does not authenticate local loopback senders.
A compromised endpoint, copied key, stolen Pi TLS private key or
network DoS remains a threat. No automatic restarts or open default port.
Malformed/oversized PCM, stale PipeWire/USB node generations, invalid
routing, blocked output, idle sender and session timeout fail closed.

## Operator-controlled offline setup

Generate a UNIQUE 32-byte shared secret on an isolated POSIX bench computer.
Do not reuse or commit it; transfer privately to both machines. Example:

~~~sh
python3 -c 'import os; p="audiohub-lab-psk.bin"; f=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.write(f,os.urandom(32)); os.close(f)'
chmod 600 audiohub-lab-psk.bin
~~~

On Windows the operator must ensure private NTFS ACLs for the secret file;
Python POSIX mode cannot verify Windows ACLs. The Pi rejects any linked,
wrong-size, nonregular, group-readable or foreign-owned key file. Manual
secret distribution, revocation and user-friendly key rotation are not
implemented. Never place the key in a command argument, logs or screenshot.

On the isolated Pi, create a temporary TLS certificate and private key
using the existing OpenSSL package, with private permissions:

~~~sh
umask 077
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout pi-lab-private.key -out pi-lab-public.crt -days 7 -subj '/CN=audiohub-isolated-lab'
chmod 600 pi-lab-private.key
openssl x509 -in pi-lab-public.crt -outform DER | sha256sum
~~~

Transfer the **lowercase 64-character certificate SHA256** out of band
to Windows. Never copy the Pi private certificate key to Windows.

## Explicit, manual local commands

Pi4: use its existing private manual LAN route, exact local PipeWire sink,
USB output and unprivileged audio user. Replace all illustrative IPs/paths
with actual isolated-test values:

~~~sh
PYTHONPATH=src python3 -m audiohub.secure_lan server --isolated-lab --bind-ip 192.168.10.30 --sender-ip 192.168.10.20 --port 4044 --key-file /private/audiohub-lab-psk.bin --cert-file /private/pi-lab-public.crt --cert-key-file /private/pi-lab-private.key --session-minutes 10
~~~

Windows PowerShell from repository root, with an existing Scream driver
already configured to unicast to local 127.0.0.1 UDP port 4010:

~~~powershell
$env:PYTHONPATH = "src"
python -m audiohub.secure_lan bridge --isolated-lab --server-ip 192.168.10.30 --port 4044 --udp-port 4010 --key-file "C:\private\audiohub-lab-psk.bin" --pin-sha256 REPLACE_WITH_VERIFIED_64_LOWERCASE_SHA256 --session-minutes 10
~~~

Use a physically isolated network, not public, home or corporate Wi-Fi/LAN.
No operator authorization to flash a card or alter a firewall is implied
by these instructions.

## Manual hardware smoke-test and rollback

1. Verify the exact Git commit and Source CI, independently confirm TLS
   fingerprint and key file permissions, and check neither listener starts
   automatically. Use an operator-approved spare SD and low speaker volume.
2. Launch Pi server then Windows bridge. Play a low-level sample via
   existing Scream audio output; verify actual Edifier audible PCM,
   latency and interruptions separately from process and packet counts.
3. Try wrong pin and wrong secret on an isolated test system: Pi must
   refuse sound. Check invalid frame, route changes, USB removal, silent
   sender and elapsed-time limit. Record sanitized results only.
4. Confirm both sockets close; no automatic reconnect, systemd unit,
   trust, routing, Wi-Fi or web settings should change.
5. Roll back by stopping both manually launched programs, restoring
   previous Windows audio output and removing operator-approved temporary
   network rules. Revoke temporary secrets under owner control, never
   through this code. The old Scream test receiver remains OFF by default.

## NO-GO gates

This source-only protocol is NOT a verified Windows installer or consumer
onboarding experience. Real Windows driver loopback unicast, Pi4 Edifier
output, TLS interoperability/latency, two simultaneous Bluetooth streams
plus LAN, clipping, 24h stability and all security failure cases need
hardware testing. Phone-based owner identity/Wi-Fi, key lifecycle, nine
unresolved third-party rootfs copyright notices, source-rights review,
legal redistribution approval and explicit CEO release consent remain
absent. AGPL-3.0-only source rights pending manual review; CI cannot
substitute a physical or legal acceptance.
