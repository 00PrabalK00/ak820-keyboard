#!/usr/bin/env python3
"""AK820 Linux Control — polished BlueZ dashboard for AJAZZ AK820 keyboards."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from tkinter import messagebox, ttk

from ak820_core import (
    SERVICE_NAME, adapter_address, adapter_power_control, bt, detect_ak820,
    parse_info, read_config, run, self_tests, service_state, timed_connect,
    write_config,
)

APP_NAME = "AK820 Linux Control"
POLL_MS = 1000

BG = "#0b1020"
PANEL = "#121a2e"
PANEL_2 = "#18223a"
TEXT = "#e8eefc"
MUTED = "#8ea0c2"
ACCENT = "#65d1ff"
GOOD = "#6ee7a8"
WARN = "#ffd166"
BAD = "#ff6b81"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("920x690")
        self.minsize(820, 610)
        self.configure(bg=BG)

        self._style()
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

        self.device_var = tk.StringVar(value=self.device_name)
        self.mac_var = tk.StringVar(value=self.mac or "Not detected")
        self.connection_var = tk.StringVar(value="CHECKING")
        self.paired_var = tk.StringVar(value="—")
        self.trusted_var = tk.StringVar(value="—")
        self.battery_var = tk.StringVar(value="—")
        self.power_var = tk.StringVar(value="—")
        self.service_var = tk.StringVar(value="—")
        self.adapter_var = tk.StringVar(value="—")
        self.reconnect_var = tk.StringVar(value="No reconnect samples yet")
        self.test_summary_var = tk.StringVar(value="Run the health check to test the stack.")
        self.connect_time_var = tk.StringVar(value="Not measured")

        self._build()
        self.after(100, self.refresh_async)
        self.after(POLL_MS, self._poll)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, borderwidth=0)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Card.TFrame", background=PANEL_2)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Card.TLabel", background=PANEL_2, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Sans", 24, "bold"))
        style.configure("Hero.TLabel", background=PANEL, foreground=TEXT, font=("Sans", 18, "bold"))
        style.configure("Metric.TLabel", background=PANEL_2, foreground=ACCENT, font=("Sans", 17, "bold"))
        style.configure("Good.TLabel", background=PANEL, foreground=GOOD, font=("Sans", 11, "bold"))
        style.configure("Bad.TLabel", background=PANEL, foreground=BAD, font=("Sans", 11, "bold"))
        style.configure("TButton", background=PANEL_2, foreground=TEXT, padding=(14, 9), font=("Sans", 10, "bold"))
        style.map("TButton", background=[("active", "#243252")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#06101a")
        style.map("Accent.TButton", background=[("active", "#8de0ff")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 10))
        style.map("TNotebook.Tab", background=[("selected", PANEL_2)], foreground=[("selected", TEXT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=30)
        style.configure("Treeview.Heading", background=PANEL_2, foreground=TEXT, font=("Sans", 10, "bold"))
        style.map("Treeview", background=[("selected", "#26385d")])

    def _build(self) -> None:
        shell = ttk.Frame(self, padding=(22, 18))
        shell.pack(fill="both", expand=True)

        top = ttk.Frame(shell)
        top.pack(fill="x")
        ttk.Label(top, text="AK820 // CONTROL", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="Linux · BlueZ", style="Muted.TLabel").pack(side="right", pady=(8, 0))

        ttk.Label(
            shell,
            text="Connection control, persistence, diagnostics and live recovery telemetry.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(shell)
        notebook.pack(fill="both", expand=True)
        dash = ttk.Frame(notebook, padding=(2, 14))
        diag = ttk.Frame(notebook, padding=(2, 14))
        tests = ttk.Frame(notebook, padding=(2, 14))
        notebook.add(dash, text="Dashboard")
        notebook.add(diag, text="Diagnostics")
        notebook.add(tests, text="Health Tests")

        self._build_dashboard(dash)
        self._build_diagnostics(diag)
        self._build_tests(tests)

    def _card(self, parent, title: str, var: tk.StringVar, col: int) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 6 if col < 3 else 0))
        ttk.Label(card, text=title.upper(), style="Card.TLabel", foreground=MUTED).pack(anchor="w")
        ttk.Label(card, textvariable=var, style="Metric.TLabel").pack(anchor="w", pady=(5, 0))
        parent.columnconfigure(col, weight=1)

    def _build_dashboard(self, root) -> None:
        hero = ttk.Frame(root, style="Panel.TFrame", padding=18)
        hero.pack(fill="x")
        left = ttk.Frame(hero, style="Panel.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, textvariable=self.device_var, style="Hero.TLabel").pack(anchor="w")
        ttk.Label(left, textvariable=self.mac_var, style="PanelMuted.TLabel").pack(anchor="w", pady=(3, 0))
        self.state_label = ttk.Label(hero, textvariable=self.connection_var, style="Good.TLabel")
        self.state_label.pack(side="right", padx=(12, 0))

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", pady=(12, 12))
        ttk.Button(buttons, text="Connect", style="Accent.TButton", command=lambda: self.action("connect")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Disconnect", command=lambda: self.action("disconnect")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Trust", command=lambda: self.action("trust")).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Detect keyboard", command=self.detect_async).pack(side="left")
        ttk.Button(buttons, text="Refresh", command=self.refresh_async).pack(side="right")

        metrics = ttk.Frame(root)
        metrics.pack(fill="x", pady=(0, 12))
        self._card(metrics, "Paired", self.paired_var, 0)
        self._card(metrics, "Trusted", self.trusted_var, 1)
        self._card(metrics, "Battery", self.battery_var, 2)
        self._card(metrics, "USB Power", self.power_var, 3)

        persistence = ttk.Frame(root, style="Panel.TFrame", padding=16)
        persistence.pack(fill="x")
        ttk.Label(persistence, text="Persistent reconnect", style="Hero.TLabel", font=("Sans", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(persistence, textvariable=self.service_var, style="PanelMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(persistence, text="Enable watchdog", command=lambda: self.service_action(True)).grid(row=0, column=1, rowspan=2, padx=(18, 8))
        ttk.Button(persistence, text="Disable", command=lambda: self.service_action(False)).grid(row=0, column=2, rowspan=2)
        persistence.columnconfigure(0, weight=1)

        timing = ttk.Frame(root, style="Panel.TFrame", padding=16)
        timing.pack(fill="x", pady=(12, 0))
        ttk.Label(timing, text="Recovery telemetry", style="Hero.TLabel", font=("Sans", 13, "bold")).pack(anchor="w")
        ttk.Label(timing, textvariable=self.reconnect_var, style="PanelMuted.TLabel").pack(anchor="w", pady=(5, 0))

    def _build_diagnostics(self, root) -> None:
        row = ttk.Frame(root, style="Panel.TFrame", padding=16)
        row.pack(fill="x")
        for label, var in [
            ("Adapter", self.adapter_var),
            ("Connect command", self.connect_time_var),
        ]:
            box = ttk.Frame(row, style="Panel.TFrame")
            box.pack(side="left", fill="x", expand=True)
            ttk.Label(box, text=label.upper(), style="PanelMuted.TLabel").pack(anchor="w")
            ttk.Label(box, textvariable=var, style="Panel.TLabel", font=("Sans", 12, "bold")).pack(anchor="w", pady=(3, 0))

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(12, 12))
        ttk.Button(actions, text="Measure connect time", style="Accent.TButton", command=self.measure_connect_async).pack(side="left")
        ttk.Label(
            actions,
            text="Measures BlueZ connect-command completion, not physical keypress latency.",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0))

        logbox = ttk.Frame(root, style="Panel.TFrame", padding=10)
        logbox.pack(fill="both", expand=True)
        self.log = tk.Text(
            logbox, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=("Monospace", 10), padx=8, pady=8, wrap="word", state="disabled",
        )
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(logbox, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        self._log("Dashboard ready")

    def _build_tests(self, root) -> None:
        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, textvariable=self.test_summary_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(header, text="Run all tests", style="Accent.TButton", command=self.run_tests_async).pack(side="right")

        self.test_tree = ttk.Treeview(root, columns=("result", "detail"), show="headings")
        self.test_tree.heading("result", text="Result")
        self.test_tree.heading("detail", text="Check / detail")
        self.test_tree.column("result", width=100, stretch=False)
        self.test_tree.column("detail", width=650)
        self.test_tree.pack(fill="both", expand=True)
        self.test_tree.tag_configure("pass", foreground=GOOD)
        self.test_tree.tag_configure("fail", foreground=BAD)

    def _log(self, msg: str) -> None:
        if not hasattr(self, "log"):
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _require_mac(self) -> bool:
        if self.mac:
            return True
        messagebox.showwarning(APP_NAME, "No AK820 detected. Pair it first, then use Detect keyboard.")
        return False

    def detect_async(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._log("Scanning BlueZ for AK820…")
        def worker():
            mac, name = detect_ak820()
            self.after(0, lambda: self._finish_detect(mac, name))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_detect(self, mac, name) -> None:
        self.busy = False
        if not mac:
            self._log("No paired AK820 found")
            messagebox.showinfo(APP_NAME, "No paired AK820 was found.")
            return
        self.mac, self.device_name = mac, name or "AK820"
        write_config(self.mac, self.device_name)
        self.mac_var.set(self.mac)
        self.device_var.set(self.device_name)
        self._log(f"Detected {self.device_name} · {self.mac}")
        self.refresh_async()

    def action(self, op: str) -> None:
        if not self._require_mac() or self.busy:
            return
        self.busy = True
        self._log(f"{op.capitalize()} requested")
        def worker():
            start = time.monotonic()
            rc, out = bt(op, self.mac, timeout=15)
            ms = (time.monotonic() - start) * 1000
            self.after(0, lambda: self._finish_action(op, rc, out, ms))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_action(self, op, rc, out, ms) -> None:
        self.busy = False
        summary = out.splitlines()[-1] if out else f"exit {rc}"
        self._log(f"{op.capitalize()}: {summary} · {ms:.0f} ms")
        if rc != 0 and "successful" not in out.lower() and "succeeded" not in out.lower():
            messagebox.showerror(APP_NAME, out or f"{op} failed")
        self.refresh_async()

    def service_action(self, enable: bool) -> None:
        if not self._require_mac():
            return
        write_config(self.mac, self.device_name)
        args = ["systemctl", "--user", "enable" if enable else "disable", "--now", SERVICE_NAME]
        rc, out = run(args, timeout=10)
        self._log(("Enabled" if enable else "Disabled") + " reconnect watchdog" if rc == 0 else out)
        self.refresh_async()

    def measure_connect_async(self) -> None:
        if not self._require_mac():
            return
        self.connect_time_var.set("Measuring…")
        def worker():
            ok, ms, out = timed_connect(self.mac)
            self.after(0, lambda: self._finish_measure(ok, ms, out))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_measure(self, ok, ms, out) -> None:
        self.connect_time_var.set(f"{ms:.1f} ms" + ("" if ok else " · failed"))
        self._log(f"Connect timing: {ms:.1f} ms · {'PASS' if ok else 'FAIL'}")

    def run_tests_async(self) -> None:
        self.test_summary_var.set("Running host health checks…")
        for item in self.test_tree.get_children():
            self.test_tree.delete(item)
        def worker():
            checks = self_tests(self.mac)
            self.after(0, lambda: self._finish_tests(checks))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_tests(self, checks) -> None:
        passed = sum(c.ok for c in checks)
        for c in checks:
            self.test_tree.insert("", "end", values=("PASS" if c.ok else "FAIL", f"{c.name} — {c.detail}"), tags=("pass" if c.ok else "fail",))
        self.test_summary_var.set(f"{passed}/{len(checks)} checks passed")
        self._log(f"Health tests complete: {passed}/{len(checks)} passed")

    def refresh_async(self) -> None:
        if not self.mac:
            self.connection_var.set("NO DEVICE")
            return
        def worker():
            _, out = bt("info", self.mac, timeout=4)
            data = parse_info(out)
            power, _ = adapter_power_control()
            active, enabled = service_state()
            addr = adapter_address()
            self.after(0, lambda: self._apply_status(data, power, active, enabled, addr))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_status(self, data, power, active, enabled, addr) -> None:
        connected = data.get("Connected", "unknown")
        self.paired_var.set(data.get("Paired", "unknown").upper())
        self.trusted_var.set(data.get("Trusted", "unknown").upper())
        self.battery_var.set(data.get("Battery Percentage", data.get("Percentage", "N/A")))
        self.power_var.set(power.upper())
        self.adapter_var.set(f"hci0 · {addr}")
        self.service_var.set(f"{active} · {enabled} · checks every 3 s")
        self.connection_var.set("CONNECTED" if connected == "yes" else "DISCONNECTED")
        self.state_label.configure(style="Good.TLabel" if connected == "yes" else "Bad.TLabel")

        now_connected = connected == "yes"
        if self.last_connected is None:
            self.last_connected = now_connected
        elif self.last_connected and not now_connected:
            self.disconnect_started = time.monotonic()
            self.last_connected = False
            self._log("Bluetooth link dropped")
        elif not self.last_connected and now_connected:
            if self.disconnect_started is not None:
                elapsed = time.monotonic() - self.disconnect_started
                self.reconnect_samples.append(elapsed)
                avg = sum(self.reconnect_samples) / len(self.reconnect_samples)
                best = min(self.reconnect_samples)
                self.reconnect_var.set(
                    f"Last {elapsed:.2f} s   ·   Avg {avg:.2f} s   ·   Best {best:.2f} s   ·   n={len(self.reconnect_samples)}"
                )
                self._log(f"Link restored in {elapsed:.2f} s")
            self.disconnect_started = None
            self.last_connected = True

    def _poll(self) -> None:
        self.refresh_async()
        self.after(POLL_MS, self._poll)


if __name__ == "__main__":
    App().mainloop()
