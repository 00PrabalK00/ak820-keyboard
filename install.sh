#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/ak820-control"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"
APP_MENU_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/ak820-control"

command -v bluetoothctl >/dev/null || { echo "bluetoothctl is required. Install BlueZ first."; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required."; exit 1; }

mkdir -p "$APP_DIR" "$BIN_DIR" "$UNIT_DIR" "$APP_MENU_DIR" "$CONFIG_DIR"
install -m 0755 "$ROOT/ak820_control.py" "$APP_DIR/ak820_control.py"\ninstall -m 0644 "$ROOT/ak820_core.py" "$APP_DIR/ak820_core.py"
install -m 0755 "$ROOT/ak820_reconnect.py" "$APP_DIR/ak820_reconnect.py"
install -m 0644 "$ROOT/systemd/ak820-reconnect.service" "$UNIT_DIR/ak820-reconnect.service"

cat > "$BIN_DIR/ak820-control" <<EOF
#!/usr/bin/env bash
exec python3 "$APP_DIR/ak820_control.py" "\$@"
EOF
chmod +x "$BIN_DIR/ak820-control"

cat > "$APP_MENU_DIR/ak820-control.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=AK820 Linux Control
Comment=Bluetooth control and reconnect diagnostics for AJAZZ AK820 keyboards
Exec=$BIN_DIR/ak820-control
Terminal=false
Categories=Settings;HardwareSettings;
EOF

if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
  LINE="$(bluetoothctl devices Paired 2>/dev/null | grep -i 'AK820' | head -n1 || true)"
  if [[ -z "$LINE" ]]; then
    LINE="$(bluetoothctl paired-devices 2>/dev/null | grep -i 'AK820' | head -n1 || true)"
  fi

  if [[ "$LINE" =~ Device[[:space:]]+([0-9A-Fa-f:]{17})[[:space:]]+(.+) ]]; then
    MAC="${BASH_REMATCH[1]}"
    NAME="${BASH_REMATCH[2]}"
    python3 - "$CONFIG_DIR/config.json" "$MAC" "$NAME" <<'PY'
import json
import pathlib
import sys
pathlib.Path(sys.argv[1]).write_text(
    json.dumps({"mac": sys.argv[2].upper(), "name": sys.argv[3]}, indent=2) + "\n"
)
PY
    echo "Detected $NAME at $MAC"
  else
    echo "No paired AK820 detected yet. The GUI can detect it later."
  fi
fi

systemctl --user daemon-reload

echo
echo "Installed AK820 Linux Control."
echo "Run: ak820-control"
echo "Optional persistent reconnect: systemctl --user enable --now ak820-reconnect.service"
