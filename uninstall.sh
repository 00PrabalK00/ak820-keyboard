#!/usr/bin/env bash
set -euo pipefail
systemctl --user disable --now ak820-reconnect.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/ak820-reconnect.service"
rm -f "$HOME/.local/bin/ak820-control"
rm -f "$HOME/.local/share/applications/ak820-control.desktop"
rm -rf "$HOME/.local/share/ak820-control"
systemctl --user daemon-reload
echo "AK820 Linux Control removed. Config left at ~/.config/ak820-control/"
