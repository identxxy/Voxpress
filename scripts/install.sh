#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${HOME}/.config/voxpress"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
APPLICATIONS_DIR="${HOME}/.local/share/applications"

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_USER_DIR" "$APPLICATIONS_DIR"

install -m 755 "$ROOT"/bin/voxpress-* "$BIN_DIR"/

if [[ ! -f "$CONFIG_DIR/settings.json" ]]; then
  install -m 644 "$ROOT/config/settings.example.json" "$CONFIG_DIR/settings.json"
fi

install -m 644 "$ROOT"/packaging/systemd/user/*.service "$SYSTEMD_USER_DIR"/
install -m 644 "$ROOT"/packaging/desktop/*.desktop "$APPLICATIONS_DIR"/

systemctl --user daemon-reload
systemctl --user enable --now voxpress-pause-listener.service voxpress-indicator.service

printf 'Voxpress installed. Configure Voxtype with config/voxtype.snippet.toml if needed.\n'
