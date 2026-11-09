#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Start the *manual* Windows TLS audio bench session, not a service."""
from audiohub.windows_bridge_setup import main

if __name__ == "__main__":
    raise SystemExit(main())
