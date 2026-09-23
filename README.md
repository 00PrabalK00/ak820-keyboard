# AK820 Linux Control

A polished Linux control center for AJAZZ AK820-series Bluetooth keyboards, built on BlueZ.

## What you get

- Dark desktop dashboard with live connection state
- Auto-detection of paired AK820 keyboards
- Pair/trust/connect status and battery state when exposed by BlueZ
- One-click connect, disconnect and trust
- Persistent 3-second reconnect watchdog with a user-level systemd service
- USB Bluetooth adapter autosuspend diagnostics
- Live disconnect/reconnect telemetry with last, average and best recovery time
- BlueZ connect-command timing test
- Built-in **Health Tests** for BlueZ, Bluetooth service, USB power management, pairing, trust, connection and watchdog state
- Live diagnostic event log
- Standard-library unit tests and GitHub Actions CI
- No Python packages beyond Tkinter and the standard library

## Install on Ubuntu

```bash
git clone https://github.com/00PrabalK00/ak820-keyboard.git
cd ak820-keyboard
sudo apt install bluez python3-tk
chmod +x install.sh
./install.sh
ak820-control
```

Enable automatic recovery even when the GUI is closed:

```bash
systemctl --user enable --now ak820-reconnect.service
```

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

The app also has a **Health Tests** tab for live host-side checks.

## Timing note

The dashboard's connect timing measures how long a BlueZ connect command takes to complete. It is **not** physical keypress-to-screen latency. True input latency requires an external timing reference such as high-speed video or hardware instrumentation.

## RGB / keymap limitation

The Bluetooth interface exposes normal HID functionality, but vendor RGB and keymap commands are not reliably available through the AK820 Max Bluetooth HID interface. This project intentionally avoids undocumented vendor writes that could put a keyboard into a bad state. Wired vendor-protocol support can be added once the exact USB revision/protocol is validated.

## Configuration

Detected keyboard configuration is stored at:

```text
~/.config/ak820-control/config.json
```

## Project layout

```text
ak820_control.py                 GUI dashboard
ak820_core.py                    BlueZ + diagnostics helpers
ak820_reconnect.py               reconnect worker
systemd/ak820-reconnect.service  user service
tests/test_core.py               unit tests
install.sh                       local installer
uninstall.sh                     uninstaller
```

## References

- AJAZZ drivers: https://ajazz.net/pages/ajazz-drivers
- BlueZ Device API: https://bluez.readthedocs.io/en/latest/device-api/
- BlueZ Input API: https://bluez.readthedocs.io/en/latest/input-api/

## License

MIT
