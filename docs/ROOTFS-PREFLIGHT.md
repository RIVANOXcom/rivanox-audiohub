# RootFS packaging preflight

This gate runs on the **unverified** ARM64 SD image build before the image is compressed.

It checks that the target root filesystem actually includes the three system/user startup services, configured user linger, Python sources, all five UI locales, mandatory PipeWire/BlueZ binaries, restricted source permissions, and three independent virtual EQ sink configurations. A failing check terminates `pi-gen` and no artifact should be promoted.

The result is embedded as `/usr/share/doc/audiohub/rootfs-preflight.json` in the test image. It only validates **package composition**, not service startup on physical Pi hardware, Bluetooth pairing safety, network reliability, USB output or a DE/EU license audit. Those remain independent mandatory release gates.

Project: `PJ2611-0001:R001`, requirement AH-006 / Workbench #3272.
