#!/usr/bin/env bash
set -euo pipefail

settings_path="${VOXPRESS_SETTINGS:-${VOXTYPE_POPUP_SETTINGS:-$HOME/.config/voxpress/settings.json}}"
history_root="${VOXPRESS_TRAINING_HISTORY_DIR:-$HOME/.local/share/voxpress/training-history}"
logdir="$history_root/tensorboard"
port="${VOXPRESS_TENSORBOARD_PORT:-6006}"

training_python="${VOXPRESS_TRAIN_PYTHON:-}"
if [[ -z "$training_python" && -f "$settings_path" ]]; then
  training_python="$(python3 - "$settings_path" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        settings = json.load(handle)
except Exception:
    settings = {}
print(settings.get("training_python_path", ""))
PY
)"
fi

tensorboard_bin="${VOXPRESS_TENSORBOARD_BIN:-}"
if [[ -z "$tensorboard_bin" && -n "$training_python" ]]; then
  candidate="$(dirname "$training_python")/tensorboard"
  if [[ -x "$candidate" ]]; then
    tensorboard_bin="$candidate"
  fi
fi
if [[ -z "$tensorboard_bin" ]]; then
  tensorboard_bin="$(command -v tensorboard || true)"
fi
if [[ -z "$tensorboard_bin" ]]; then
  echo "tensorboard not found. Set VOXPRESS_TENSORBOARD_BIN or training_python_path." >&2
  exit 2
fi

mkdir -p "$logdir"
exec "$tensorboard_bin" --logdir "$logdir" --port "$port" "$@"
