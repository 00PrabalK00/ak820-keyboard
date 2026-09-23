#!/usr/bin/env python3
"""Core helpers for AK820 Linux Control."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import time
from dataclasses import dataclass

CONFIG_DIR = pathlib.Path.home() / ".config" / "ak820-control"
CONFIG_FILE = CONFIG_DIR / "config.json"
SERVICE_NAME = "ak820-reconnect.service"


def run(cmd: list[str], timeout: float = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"Timed out: {' '.join(cmd)}"


def bt(*args: str, timeout: float = 10) -> tuple[int, str]:
    return run(["bluetoothctl", *args], timeout=timeout)


def parse_info(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if ":" in s:
            key, value = s.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def parse_device_line(line: str) -> tuple[str, str] | None:
    m = re.search(r"Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", line.strip())
    return (m.group(1).upper(), m.group(2).strip()) if m else None


def detect_ak820() -> tuple[str | None, str | None]:
    for command in [("devices", "Paired"), ("paired-devices",), ("devices",)]:
        rc, out = bt(*command)
        if rc not in (0, 1):
            continue
        for line in out.splitlines():
            parsed = parse_device_line(line)
            if parsed and "AK820" in parsed[1].upper():
                return parsed
    return None, None


def read_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def write_config(mac: str, name: str = "AK820") -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"mac": mac.upper(), "name": name}, indent=2) + "\n")


def service_state() -> tuple[str, str]:
    _, active = run(["systemctl", "--user", "is-active", SERVICE_NAME], timeout=3)
    _, enabled = run(["systemctl", "--user", "is-enabled", SERVICE_NAME], timeout=3)
    return (
        active.splitlines()[0] if active else "unknown",
        enabled.splitlines()[0] if enabled else "unknown",
    )


def bluetooth_service_state() -> str:
    rc, out = run(["systemctl", "is-active", "bluetooth.service"], timeout=3)
    return out.splitlines()[0] if rc == 0 and out else "inactive"


def adapter_power_control() -> tuple[str, str]:
    hci = pathlib.Path("/sys/class/bluetooth/hci0/device")
    try:
        device = hci.resolve()
    except Exception:
        return "unknown", ""
    for p in [device, device.parent, *list(device.parents)[:4]]:
        control = p / "power" / "control"
        vendor = p / "idVendor"
        if control.exists() and (vendor.exists() or p == device):
            try:
                return control.read_text().strip(), str(control)
            except Exception:
                pass
    return "unknown", ""


def adapter_address() -> str:
    try:
        return pathlib.Path("/sys/class/bluetooth/hci0/address").read_text().strip()
    except Exception:
        return "unknown"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def self_tests(mac: str) -> list[Check]:
    checks: list[Check] = []
    rc, _ = run(["bluetoothctl", "--version"], timeout=3)
    checks.append(Check("BlueZ CLI", rc == 0, "bluetoothctl available" if rc == 0 else "bluetoothctl missing"))

    svc = bluetooth_service_state()
    checks.append(Check("Bluetooth service", svc == "active", svc))

    power, path = adapter_power_control()
    checks.append(Check("USB autosuspend", power == "on", f"{power} · {path or 'path unavailable'}"))

    if mac:
        _, out = bt("info", mac, timeout=4)
        info = parse_info(out)
        checks.append(Check("Keyboard paired", info.get("Paired") == "yes", info.get("Paired", "unknown")))
        checks.append(Check("Keyboard trusted", info.get("Trusted") == "yes", info.get("Trusted", "unknown")))
        checks.append(Check("Keyboard connected", info.get("Connected") == "yes", info.get("Connected", "unknown")))
    else:
        checks.append(Check("Keyboard detected", False, "No AK820 selected"))

    active, enabled = service_state()
    checks.append(Check("Reconnect watchdog", active == "active", f"{active}, {enabled}"))
    return checks


def timed_connect(mac: str) -> tuple[bool, float, str]:
    start = time.monotonic()
    rc, out = bt("connect", mac, timeout=15)
    elapsed_ms = (time.monotonic() - start) * 1000
    ok = rc == 0 or "successful" in out.lower() or "succeeded" in out.lower()
    return ok, elapsed_ms, out
