# Bluetooth authorization hardening — alpha review

A hardware-free policy audit found that the previous BlueZ `PropertiesChanged(Paired=True)` handler automatically set `Trusted=True` on any reported device, even if the event was unrelated to an authorization request from the current AudioHub pairing agent.

The alpha policy now admits trust only if:

- The image booted without pre-existing paired peers;
- The ten-minute first-pairing window has not expired;
- The count is between one and two paired devices;
- The device has a still-valid (90-second) pending authorization issued by this agent;
- At most two pending devices are considered simultaneously.

The existing already-trusted peers remain usable after reboot. This guard **does not** implement secure appliance ownership, a safe authenticated add-device mode or a screenless recovery protocol. It must be tested against Android/BlueZ bonding behavior; some devices may require an altered handshake. Fail closed when the authorization request is missing, rather than automatically trust an unrelated device.

This is a source-level hardening step for Workbench `PJ2611-0001:R001`, requirement AH-005 / ID 3271. No stable image release should be inferred.
