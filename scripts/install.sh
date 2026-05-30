#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${HOME}/.config/voxpress"
VOXTYPE_CONFIG="${HOME}/.config/voxtype/config.toml"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
APPLICATIONS_DIR="${HOME}/.local/share/applications"

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$SYSTEMD_USER_DIR" "$APPLICATIONS_DIR"

install -m 755 "$ROOT"/bin/voxpress-* "$BIN_DIR"/

if [[ ! -f "$CONFIG_DIR/settings.json" ]]; then
  install -m 644 "$ROOT/config/settings.example.json" "$CONFIG_DIR/settings.json"
fi

if [[ -f "$VOXTYPE_CONFIG" ]]; then
  CONFIG_UPDATED="$(
    python3 - "$VOXTYPE_CONFIG" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
replacements = {
    "voxtype-save-clipboard-x11": "voxpress-save-clipboard-x11",
    "voxtype-paste-x11": "voxpress-paste-x11",
    "voxtype-postprocess-preview": "voxpress-postprocess-preview",
    "voxtype-popup-ui": "voxpress-popup-ui",
}
updated = text
for old, new in replacements.items():
    updated = updated.replace(old, new)
if updated != text:
    path.write_text(updated, encoding="utf-8")
    print("1")
else:
    print("0")
PY
  )"
fi

install -m 644 "$ROOT"/packaging/systemd/user/*.service "$SYSTEMD_USER_DIR"/
install -m 644 "$ROOT"/packaging/systemd/user/*.timer "$SYSTEMD_USER_DIR"/
install -m 644 "$ROOT"/packaging/desktop/*.desktop "$APPLICATIONS_DIR"/

systemctl --user daemon-reload

# Voxpress replaces the legacy Voxtype desktop listener and tray indicator.
systemctl --user disable --now \
  voxtype-pause-listener.service \
  voxtype-indicator.service \
  >/dev/null 2>&1 || true

systemctl --user enable --now \
  voxpress-pause-listener.service \
  voxpress-indicator.service \
  voxpress-finetune-daily.timer

if [[ "${CONFIG_UPDATED:-0}" == "1" ]]; then
  systemctl --user try-restart voxtype.service >/dev/null 2>&1 || true
fi

printf 'Voxpress installed. Configure Voxtype with config/voxtype.snippet.toml if needed.\n'
