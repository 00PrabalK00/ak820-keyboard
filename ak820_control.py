#!/usr/bin/env python3
"""AK820 Linux Control.

Small Linux control panel for AJAZZ AK820-series Bluetooth keyboards.
Uses BlueZ bluetoothctl and systemd --user. No third-party Python packages.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from tkinter import messagebox, ttk

APP_NAME = "AK820 Linux Control"
CONFIG_DIR = pathlib.Path.home() / ".config" / "ak820-control"
CONFIG_FILE = CONFIG_DIR / "config.json"
SERVICE_NAME = "ak820-reconnect.service"
POLL_MS = 500


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


def detect_ak820() -> tuple[str | None, str | None]:
    commands = [("devices", "Paired"), ("paired-devices",), ("devices",)]
    seen: set[str] = set()
    for command in commands:
        rc, out = bt(*command)
        if rc not in (0, 1):
            continue
        for line in out.splitlines():
            m = re.search(r"Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", line.strip())
            if not m:
                continue
            mac, name = m.group(1).upper(), m.group(2).strip()
            if mac in seen:
                continue
            seen.add(mac)
            if "AK820" in name.upper():
                return mac, name
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


def adapter_power_control() -> tuple[str, str]:
    hci = pathlib.Path("/sys/class/bluetooth/hci0/device")
    try:
        device = hci.resolve()
    except Exception:
        return "unknown", ""

    candidates = [device, device.parent, *list(device.parents)[:4]]
    for p in candidates:
        control = p / "power" / "control"
        vendor = p / "idVendor"
        if control.exists() and (vendor.exists() or p == device):
            try:
                return control.read_text().strip(), str(control)
            except Exception:
                pass
    return "unknown", ""


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x590")
        self.minsize(700, 520)

        cfg = read_config()
        self.mac = str(cfg.get("mac", "")).upper()
        self.device_name = str(cfg.get("name", "AK820"))
        if not self.mac:
            mac, name = detect_ak820()
            if mac:
                self.mac, self.device_name = mac, name or "AK820"
                write_config(self.mac, self.device_name)

        self.last_connected: bool | None = None
        self.disconnect_started: float | None = None
        self.reconnect_samples: deque[float] = deque(maxlen=50)
        self.busy = False

        self.status_var = tk.StringVar(value="Checking…")
        self.device_var = tk.StringVar(value=self.device_name)
        self.mac_var = tk.StringVar(value=self.mac or "Not detected")
        self.paired_var = tk.StringVar(value="—")
        self.trusted_var = tk.StringVar(value="—")
        self.connected_var = tk.StringVar(value="—")
        self.battery_var = tk.StringVar(value="—")
        self.adapter_var = tk.StringVar(value="—")
        self.service_var = tk.StringVar(value="—")
        self.reconnect_var = tk.StringVar(value="No samples yet")

        self._build_ui()
        self.after(100, self.refresh_async)
        self.after(POLL_MS, self._poll)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("TkDefaultFont", 20, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var, font=("TkDefaultFont", 11, "bold")).pack(side="right")
        ttk.Label(
            root,
            text="Bluetooth connection, persistence and reconnect diagnostics for AJAZZ AK820 keyboards.",
        ).pack(anchor="w", pady=(4, 16))

        device = ttk.LabelFrame(root, text="Keyboard", padding=12)
        device.pack(fill="x")
        grid = ttk.Frame(device)
        grid.pack(fill="x")

        rows = [
            ("Device", self.device_var),
            ("MAC", self.mac_var),
            ("Paired", self.paired_var),
            ("Trusted", self.trusted_var),
            ("Connected", self.connected_var),
            ("Battery", self.battery_var),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(grid, text=label + ":", width=13).grid(
                row=i // 2, column=(i % 2) * 2, sticky="w", padx=(0, 6), pady=3
            )
            ttk.Label(grid, textvariable=var, width=25).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", pady=3
            )
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

        buttons = ttk.Frame(device)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Connect", command=lambda: self.action("connect")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Disconnect", command=lambda: self.action("disconnect")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Trust", command=lambda: self.action("trust")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Detect AK820", command=self.detect_async).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Refresh", command=self.refresh_async).pack(side="right")

        persistence = ttk.LabelFrame(root, text="Persistence", padding=12)
        persistence.pack(fill="x", pady=(12, 0))
        ttk.Label(persistence, text="USB adapter power:").grid(row=0, column=0, sticky="w")
        ttk.Label(persistence, textvariable=self.adapter_var).grid(row=0, column=1, sticky="w", padx=(8, 24))
        ttk.Label(persistence, text="Reconnect service:").grid(row=0, column=2, sticky="w")
        ttk.Label(persistence, textvariable=self.service_var).grid(row=0, column=3, sticky="w", padx=(8, 0))
        persistence.columnconfigure(3, weight=1)

        svc = ttk.Frame(persistence)
        svc.grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(
            svc,
            text="Enable persistent reconnect",
            command=lambda: self.service_action("enable"),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            svc,
            text="Disable service",
            command=lambda: self.service_action("disable"),
        ).pack(side="left")

        diag = ttk.LabelFrame(root, text="Reconnect timing", padding=12)
        diag.pack(fill="x", pady=(12, 0))
        ttk.Label(diag, textvariable=self.reconnect_var).pack(anchor="w")
        ttk.Label(
            diag,
            text="Observed from Linux seeing the link drop until Connected returns. This is not physical keypress latency.",
        ).pack(anchor="w", pady=(4, 0))

        log_frame = ttk.LabelFrame(root, text="Live log", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        self._log("Ready")

    def _log(self, msg: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _require_mac(self) -> bool:
        if self.mac:
            return True
        messagebox.showwarning(
            APP_NAME,
            "No AK820 was detected. Pair it first, then click Detect AK820.",
        )
        return False

    def detect_async(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._log("Searching BlueZ for an AK820…")

        def worker() -> None:
            mac, name = detect_ak820()
            self.after(0, lambda: self._finish_detect(mac, name))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_detect(self, mac: str | None, name: str | None) -> None:
        self.busy = False
        if not mac:
            self._log("No AK820 found")
            messagebox.showinfo(APP_NAME, "No paired AK820 was found by BlueZ.")
            return
        self.mac, self.device_name = mac, name or "AK820"
        write_config(self.mac, self.device_name)
        self.mac_var.set(self.mac)
        self.device_var.set(self.device_name)
        self._log(f"Detected {self.device_name} at {self.mac}")
        self.refresh_async()

    def action(self, op: str) -> None:
        if not self._require_mac() or self.busy:
            return
        self.busy = True
        self._log(f"{op.capitalize()} requested")

        def worker() -> None:
            start = time.monotonic()
            rc, out = bt(op, self.mac, timeout=15)
            elapsed = (time.monotonic() - start) * 1000
            self.after(0, lambda: self._finish_action(op, rc, out, elapsed))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_action(self, op: str, rc: int, out: str, elapsed_ms: float) -> None:
        self.busy = False
        summary = out.splitlines()[-1] if out else f"exit {rc}"
        self._log(f"{op.capitalize()}: {summary} ({elapsed_ms:.0f} ms)")
        if rc != 0 and "successful" not in out.lower() and "succeeded" not in out.lower():
            messagebox.showerror(APP_NAME, out or f"{op} failed")
        self.refresh_async()

    def service_action(self, op: str) -> None:
        if not self._require_mac():
            return
        write_config(self.mac, self.device_name)
        cmd = (
            ["systemctl", "--user", "enable", "--now", SERVICE_NAME]
            if op == "enable"
            else ["systemctl", "--user", "disable", "--now", SERVICE_NAME]
        )
        rc, out = run(cmd, timeout=10)
        if rc == 0:
            self._log(f"Reconnect service {op}d")
        else:
            self._log(out)
            messagebox.showerror(APP_NAME, out or "systemd operation failed. Run install.sh first.")
        self.refresh_async()

    def refresh_async(self) -> None:
        if not self.mac:
            self.status_var.set("No device")
            return

        def worker() -> None:
            _, out = bt("info", self.mac, timeout=4)
            data = parse_info(out)
            pwr, pwr_path = adapter_power_control()
            active, enabled = service_state()
            self.after(0, lambda: self._apply_status(data, pwr, pwr_path, active, enabled))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_status(
        self,
        data: dict[str, str],
        pwr: str,
        pwr_path: str,
        active: str,
        enabled: str,
    ) -> None:
        paired = data.get("Paired", "unknown")
        trusted = data.get("Trusted", "unknown")
        connected = data.get("Connected", "unknown")
        battery = data.get("Battery Percentage", data.get("Percentage", "unavailable"))

        self.paired_var.set(paired)
        self.trusted_var.set(trusted)
        self.connected_var.set(connected)
        self.battery_var.set(battery)
        self.adapter_var.set(pwr + (" (autosuspend blocked)" if pwr == "on" else ""))
        self.service_var.set(f"{active}, {enabled}")
        self.status_var.set("Connected" if connected == "yes" else "Disconnected")

        now_connected = connected == "yes"
        if self.last_connected is None:
            self.last_connected = now_connected
        elif self.last_connected and not now_connected:
            self.disconnect_started = time.monotonic()
            self._log("Bluetooth link disconnected")
            self.last_connected = False
        elif not self.last_connected and now_connected:
            if self.disconnect_started is not None:
                elapsed = time.monotonic() - self.disconnect_started
                self.reconnect_samples.append(elapsed)
                avg = sum(self.reconnect_samples) / len(self.reconnect_samples)
                self.reconnect_var.set(
                    f"Last reconnect: {elapsed:.2f} s   Average: {avg:.2f} s   Samples: {len(self.reconnect_samples)}"
                )
                self._log(f"Bluetooth link restored after {elapsed:.2f} s")
            self.disconnect_started = None
            self.last_connected = True

    def _poll(self) -> None:
        self.refresh_async()
        self.after(POLL_MS, self._poll)


if __name__ == "__main__":
    App().mainloop()
