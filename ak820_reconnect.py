#!/usr/bin/env python3
"""Persistent reconnect worker for AK820 Linux Control."""

import json
import pathlib
import subprocess
import time

CONFIG = pathlib.Path.home() / ".config" / "ak820-control" / "config.json"
INTERVAL = 3.0


def run_bt(*args: str) -> str:
    try:
        p = subprocess.run(
            ["bluetoothctl", *args],
            capture_output=True,
            text=True,
            timeout=12,
        )
        return (p.stdout or "") + (p.stderr or "")
    except Exception:
        return ""


def load_mac() -> str:
    try:
        return str(json.loads(CONFIG.read_text()).get("mac", "")).strip().upper()
    except Exception:
        return ""


def main() -> None:
    while True:
        mac = load_mac()
        if mac:
            info = run_bt("info", mac)
            if "Connected: yes" not in info:
                run_bt("connect", mac)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
