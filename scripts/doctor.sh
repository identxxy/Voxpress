#!/usr/bin/env bash
set -u

missing_count=0
warning_count=0

ok() {
  printf 'OK      %s\n' "$1"
}

missing() {
  printf 'MISSING %s\n' "$1"
  missing_count=$((missing_count + 1))
}

warn() {
  printf 'WARN    %s\n' "$1"
  warning_count=$((warning_count + 1))
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

executable_exists() {
  local exe="$1"

  if [[ -z "$exe" ]]; then
    return 1
  fi

  if [[ "$exe" == */* ]]; then
    [[ -x "$exe" ]]
  else
    command_exists "$exe"
  fi
}

check_command() {
  local cmd="$1"

  if command_exists "$cmd"; then
    ok "command: $cmd"
  else
    missing "command: $cmd"
  fi
}

check_xdotool() {
  local bundled="$HOME/.local/share/voxtype/xdotool-env/bin/xdotool"

  if command_exists xdotool; then
    ok "command: xdotool"
  elif [[ -x "$bundled" ]]; then
    ok "command: xdotool ($bundled)"
  else
    missing "command: xdotool"
  fi
}

check_python_import() {
  local python_bin="$1"
  local module="$2"
  local label="$3"

  if ! executable_exists "$python_bin"; then
    missing "$label not found: $python_bin"
    return
  fi

  if "$python_bin" - "$module" <<'PY' >/dev/null 2>&1
import importlib
import sys

importlib.import_module(sys.argv[1])
PY
  then
    ok "$label import: $module"
  else
    missing "$label import: $module"
  fi
}

check_optional_python_import() {
  local python_bin="$1"
  local module="$2"
  local label="$3"

  if ! executable_exists "$python_bin"; then
    warn "$label not found: $python_bin"
    return
  fi

  if "$python_bin" - "$module" <<'PY' >/dev/null 2>&1
import importlib
import sys

importlib.import_module(sys.argv[1])
PY
  then
    ok "$label import: $module"
  else
    warn "$label import missing: $module"
  fi
}

check_desktop_python_stack() {
  local python_bin="$1"

  if ! executable_exists "$python_bin"; then
    missing "desktop python stack not found: $python_bin"
    return
  fi

  if "$python_bin" <<'PY' >/dev/null 2>&1
import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gdk, GdkX11, GLib, Gtk  # noqa: F401
PY
  then
    ok "desktop python stack: Gtk/GdkX11/AyatanaAppIndicator3/cairo ($python_bin)"
  else
    missing "desktop python stack: Gtk/GdkX11/AyatanaAppIndicator3/cairo ($python_bin)"
  fi
}

read_training_python_from_settings() {
  local settings_path="$1"

  python3 - "$settings_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text())
except Exception:
    sys.exit(1)

value = data.get("training_python_path") or ""
if isinstance(value, str):
    print(value, end="")
PY
}

resolve_training_python() {
  local settings_path="${VOXPRESS_SETTINGS:-${VOXTYPE_POPUP_SETTINGS:-$HOME/.config/voxpress/settings.json}}"
  training_python="${VOXPRESS_TRAIN_PYTHON:-}"
  training_python_source="VOXPRESS_TRAIN_PYTHON"

  if [[ -n "$training_python" ]]; then
    return 0
  fi

  training_python_source="default"

  if [[ -f "$settings_path" ]]; then
    if command_exists python3; then
      local parsed
      parsed="$(read_training_python_from_settings "$settings_path")"
      local status=$?
      if [[ $status -eq 0 && -n "$parsed" ]]; then
        training_python="$parsed"
        training_python_source="$settings_path"
        return 0
      fi
      if [[ $status -ne 0 ]]; then
        warn "could not read training_python_path from $settings_path"
      fi
    else
      warn "could not read $settings_path because python3 is missing"
    fi
  fi

  training_python="python3"
}

check_file() {
  local path="$1"
  local label="$2"

  if [[ -f "$path" ]]; then
    ok "$label: $path"
  else
    missing "$label: $path"
  fi
}

check_optional_file() {
  local path="$1"
  local label="$2"

  if [[ -f "$path" ]]; then
    ok "$label: $path"
  else
    warn "$label missing: $path"
  fi
}

echo "Voxpress doctor"
echo

echo "Runtime commands"
for cmd in \
  python3 \
  systemctl \
  xinput \
  xmodmap \
  xclip \
  xwininfo \
  xrandr \
  notify-send \
  parec \
  voxtype
do
  check_command "$cmd"
done
check_xdotool

echo
echo "Python runtime imports"
runtime_python="/usr/bin/python3"
if [[ ! -x "$runtime_python" ]]; then
  runtime_python="python3"
fi
check_desktop_python_stack "$runtime_python"
check_python_import python3 opencc "postprocess python (python3)"

echo
echo "Optional training"
if command_exists nvidia-smi; then
  ok "command: nvidia-smi"
else
  warn "command missing: nvidia-smi"
fi

training_python=""
training_python_source=""
resolve_training_python
if executable_exists "$training_python"; then
  ok "training python: $training_python ($training_python_source)"
  for module in torch transformers peft soundfile; do
    check_optional_python_import "$training_python" "$module" "training python"
  done
else
  warn "training python not found: $training_python ($training_python_source)"
  warn "training imports skipped: torch transformers peft soundfile"
fi

echo
echo "Export tooling"
converter_path="${VOXPRESS_WHISPER_CPP_CONVERT_SCRIPT:-$HOME/.local/share/voxpress/tools/whisper.cpp/models/convert-h5-to-ggml.py}"
openai_whisper_repo="${VOXPRESS_OPENAI_WHISPER_REPO:-$HOME/.local/share/voxpress/tools/whisper}"
mel_filters_path="$openai_whisper_repo/whisper/assets/mel_filters.npz"
check_optional_file "$converter_path" "whisper.cpp converter"
check_optional_file "$mel_filters_path" "OpenAI Whisper mel filters"

echo
if [[ $missing_count -eq 0 ]]; then
  if [[ $warning_count -eq 0 ]]; then
    echo "Summary: OK"
  else
    echo "Summary: OK with $warning_count warning(s)"
  fi
  exit 0
fi

echo "Summary: $missing_count missing, $warning_count warning(s)"
exit 1
