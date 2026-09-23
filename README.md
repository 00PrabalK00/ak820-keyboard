# AK820 Linux Control

A lightweight Linux control panel for AJAZZ AK820-series Bluetooth keyboards.

AJAZZ currently publishes the AK820 Max vendor driver for Windows only. This project fills the Linux gap for the part that is safe and well-supported through BlueZ: connection state, trust, persistent reconnect and reconnect diagnostics.

## Features

* Auto-detects paired AK820 keyboards
* Shows paired, trusted, connected and battery state when BlueZ exposes it
* One-click connect, disconnect and trust
* Persistent 3 second reconnect watchdog using a user-level systemd service
* Shows Bluetooth USB runtime power state so adapter autosuspend issues are visible
* Measures observed disconnect-to-reconnect time
* Live event log
* No Python packages required beyond Tkinter and the standard library

## Important limitation

Bluetooth mode exposes the normal HID keyboard interfaces but vendor RGB/configuration commands are not reliably available over Bluetooth on the AK820 Max. This app deliberately does not send undocumented vendor HID writes. Wired RGB/keymap support can be added after validating the exact USB revision and protocol.

## Install on Ubuntu

```bash
sudo apt install bluez python3-tk
./install.sh
ak820-control
```

To keep the keyboard reconnecting even when the GUI is closed:

```bash
systemctl --user enable --now ak820-reconnect.service
```

Check it with:

```bash
systemctl --user status ak820-reconnect.service
```

## Configuration

The detected keyboard is stored in:

```text
~/.config/ak820-control/config.json
```

## Why this exists

BlueZ exposes connection and trust state through its Device API and supports reconnect behavior for HID devices. AJAZZ's official downloads currently list the AK820 Max driver as Windows-only, so Linux users otherwise have to manage these settings manually.

## References

* AJAZZ driver page: https://ajazz.net/pages/ajazz-drivers
* BlueZ Device API: https://bluez.readthedocs.io/en/latest/device-api/
* BlueZ Input API: https://bluez.readthedocs.io/en/latest/input-api/

## License

MIT
