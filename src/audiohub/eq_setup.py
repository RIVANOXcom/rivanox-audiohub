# SPDX-License-Identifier: AGPL-3.0-only
"""Pre-create the three virtual EQ sinks for the unprivileged PipeWire user."""
import os
from pathlib import Path
from .mixer import defaults, pipewire_filter_config


def main():
    home = Path.home()
    target = home / ".config" / "pipewire" / "pipewire.conf.d" / "90-audiohub-eq.conf"
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_text(pipewire_filter_config(defaults()))
    os.chmod(target, 0o600)


if __name__ == "__main__":
    main()
