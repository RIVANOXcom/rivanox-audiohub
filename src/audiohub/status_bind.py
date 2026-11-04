# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed interface selection for AudioHub's read-only alpha status UI.

Before a secure owner claim exists, HTTP exposure to a LAN is a deliberate
manual *development* exception. This module does not grant owner privileges.
"""
from __future__ import annotations

import ipaddress
import os

LOOPBACK = "127.0.0.1"
LAN_RANGES = tuple(ipaddress.IPv4Network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
))


def select_bind_address(environ=None):
    """Default to IPv4 loopback; only opt into a specific RFC1918 interface.

    Never accept a wildcard, public address, DNS hostname, or multicast.
    An explicit LAN test still has no authentication; it must not be bundled
    with an automatically set unsafe flag in an appliance image.
    """
    values = os.environ if environ is None else environ
    raw = values.get("AUDIOHUB_STATUS_BIND_IP", LOOPBACK)
    if not isinstance(raw, str):
        raise ValueError("Status bind IP must be a literal IPv4 address")
    try:
        ip = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError as exc:
        raise ValueError("Status bind IP must be a literal IPv4 address") from exc
    if ip.is_loopback:
        return str(ip)
    if not any(ip in block for block in LAN_RANGES):
        raise ValueError("Status listener may bind only to loopback or RFC1918 IPv4")
    if values.get("AUDIOHUB_UNSAFE_STATUS_LAN") != "YES":
        raise ValueError("LAN status preview requires explicit unsafe opt-in")
    return str(ip)
