#!/usr/bin/env bash
set -euo pipefail

TOOL_ROOT="${VOXPRESS_WHISPER_TOOL_ROOT:-$HOME/.local/share/voxpress/tools}"
CONVERTER="${VOXPRESS_WHISPER_CPP_CONVERT_SCRIPT:-$TOOL_ROOT/whisper.cpp/models/convert-h5-to-ggml.py}"
WHISPER_TARGET="${VOXPRESS_OPENAI_WHISPER_REPO:-$TOOL_ROOT/whisper}"
MEL_FILTERS="$WHISPER_TARGET/whisper/assets/mel_filters.npz"
CONVERTER_URL="https://raw.githubusercontent.com/ggerganov/whisper.cpp/master/models/convert-h5-to-ggml.py"

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

download_file() {
  local url="$1"
  local output="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --show-error -o "$output" "$url"
    return
  fi

  if command -v wget >/dev/null 2>&1; then
    wget -O "$output" "$url"
    return
  fi

  echo "ERROR: neither curl nor wget is available" >&2
  exit 1
}

extract_openai_whisper_assets() {
  local download_dir="$1"
  local target_dir="$2"
  local staging_dir="$3"

  python3 - "$download_dir" "$target_dir" "$staging_dir" <<'PY'
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

download_dir = Path(sys.argv[1])
target_dir = Path(sys.argv[2])
staging_dir = Path(sys.argv[3])

archives = sorted(
    [path for path in download_dir.iterdir() if path.name.startswith(("openai_whisper-", "openai-whisper-"))],
    key=lambda path: path.stat().st_mtime,
)
if not archives:
    raise SystemExit("No openai-whisper archive was downloaded")

archive = archives[-1]
staging_dir.mkdir(parents=True, exist_ok=True)


def relative_whisper_path(name):
    parts = [part for part in Path(name).parts if part not in ("", ".")]
    for index, part in enumerate(parts):
        if part == "whisper":
            rel = Path(*parts[index:])
            return rel
    return None


def wanted(rel):
    if rel is None:
        return False
    if rel == Path("whisper/__init__.py"):
        return True
    return len(rel.parts) >= 2 and rel.parts[0] == "whisper" and rel.parts[1] == "assets"


def write_file(rel, data):
    destination = staging_dir / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


if tarfile.is_tarfile(archive):
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            rel = relative_whisper_path(member.name)
            if not wanted(rel):
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            write_file(rel, source.read())
elif zipfile.is_zipfile(archive):
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                continue
            name = info.filename
            rel = relative_whisper_path(name)
            if not wanted(rel):
                continue
            write_file(rel, zf.read(name))
else:
    raise SystemExit(f"Unsupported openai-whisper archive: {archive}")

mel_filters = staging_dir / "whisper/assets/mel_filters.npz"
if not mel_filters.is_file():
    raise SystemExit("Downloaded openai-whisper archive did not contain whisper/assets/mel_filters.npz")

for source in staging_dir.rglob("*"):
    if not source.is_file():
        continue
    destination = target_dir / source.relative_to(staging_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
PY
}

echo "Tool root: $TOOL_ROOT"

if ! python3 -m pip --version >/dev/null 2>&1; then
  echo "ERROR: python3 with pip is required to download openai-whisper assets" >&2
  exit 1
fi

mkdir -p "$(dirname "$CONVERTER")" "$WHISPER_TARGET"

if [[ -f "$CONVERTER" ]]; then
  echo "Keeping existing converter: $CONVERTER"
else
  echo "Downloading whisper.cpp converter"
  converter_tmp="$tmp_dir/convert-h5-to-ggml.py"
  download_file "$CONVERTER_URL" "$converter_tmp"
  install -m 0644 "$converter_tmp" "$CONVERTER"
  echo "Installed converter: $CONVERTER"
fi

if [[ -f "$MEL_FILTERS" ]]; then
  echo "Keeping existing OpenAI Whisper assets: $MEL_FILTERS"
else
  echo "Downloading openai-whisper source package for assets only"
  download_dir="$tmp_dir/openai-whisper-download"
  staging_dir="$tmp_dir/openai-whisper-staging"
  mkdir -p "$download_dir" "$staging_dir"
  python3 -m pip --disable-pip-version-check download --no-deps openai-whisper -d "$download_dir"
  extract_openai_whisper_assets "$download_dir" "$WHISPER_TARGET" "$staging_dir"
  echo "Installed OpenAI Whisper assets: $MEL_FILTERS"
fi

echo "Verifying converter syntax"
python3 -m py_compile "$CONVERTER"

if [[ ! -f "$MEL_FILTERS" ]]; then
  echo "ERROR: missing mel filters: $MEL_FILTERS" >&2
  exit 1
fi

echo "Verified mel filters: $MEL_FILTERS"
echo
echo "Training env note:"
echo "  This script does not install torch, transformers, peft, or soundfile."
echo "  Prepare a separate training env and set VOXPRESS_TRAIN_PYTHON or training_python_path."
echo "  This script does not build or enable whisper.cpp quantize."
