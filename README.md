# Voxpress

Talk is cheap, vibe me the code.

Voxpress is a Linux/X11 desktop dictation companion for people who want speech
input that works in any focused window, including terminals and mixed
Chinese/English text fields.

macOS and Windows ship system dictation. Linux/X11 still lacks a stable,
background, arbitrary-window voice input layer that behaves well with terminal
paste, CJK text, and local Whisper transcription. Voxpress fills that gap by
wrapping the upstream [Voxtype](https://github.com/peteonrails/voxtype) CLI and
config hooks with a Linux desktop UX.

Voxpress is not a fork of Voxtype. Voxtype still handles recording control,
Whisper model management, and transcription; Voxpress adds the X11 desktop
layer around it.

## What It Adds

- Hold-to-talk X11 key listener, defaulting to `Pause`.
- GTK editable preview before text is inserted.
- Traditional Chinese to Simplified Chinese cleanup with OpenCC.
- Clipboard-safe paste that restores the user's previous clipboard.
- Terminal-aware paste behavior, including `Ctrl+Shift+V` where needed.
- Tray settings for enable/disable/restart, keys, language mode, and preview UI.
- Optional edited-preview correction collection for personal fine-tuning.
- Optional daily personal model update pipeline.

## How It Works

1. Hold the trigger key to start recording through Voxtype.
2. Release the key to stop recording and transcribe locally.
3. Voxpress cleans up the text and opens an editable GTK preview.
4. Confirmed text is pasted into the original target window through a guarded
   clipboard marker.
5. If you edited the preview, Voxpress can save the audio/text pair as a
   correction sample for personal training.

The main scripts are installed as `voxpress-*` commands and run as user systemd
services plus Voxtype pre/post hooks.

## Requirements

Voxpress currently targets GNOME/X11-style desktop sessions. Wayland support is
not implemented yet.

Runtime dependencies:

- `voxtype`, already installed and configured with a local Whisper model.
- Python 3.
- GTK3 / PyGObject (`gi`).
- Ayatana AppIndicator GI bindings.
- `opencc`.
- X11 desktop tools: `xinput`, `xmodmap`, `xclip`, `xdotool`, `xwininfo`,
  `xrandr`, `notify-send`.
- `parec` from PulseAudio/PipeWire tools if correction audio collection is
  enabled.

Optional personal-training dependencies:

- NVIDIA GPU tooling, especially `nvidia-smi`, for idle checks.
- Python environment with `torch`, `transformers`, `peft`, `soundfile`, and
  `tensorboard`.
- Hugging Face access/cache for the configured base Whisper model.

Optional export tooling for automatic model promotion:

- whisper.cpp's `convert-h5-to-ggml.py`.
- OpenAI Whisper source assets, especially `whisper/assets/mel_filters.npz`.
- A validated whisper.cpp quantizer only if you explicitly want quantization.
  Older quantizers may produce models that load but transcribe badly, so
  Voxpress does not auto-detect quantizers.

The checkout includes `scripts/doctor.sh` for dependency checks and
`scripts/install-training-tools.sh` for minimal export-tool bootstrap. Treat
them as setup aids, not as a guarantee that every desktop, driver, or
model-cache state can be fixed automatically.

## Install

Clone the repo and run:

```bash
./scripts/install.sh
```

Then merge the relevant settings from `config/voxtype.snippet.toml` into
`~/.config/voxtype/config.toml`. At minimum, Voxtype should call:

```toml
[output]
mode = "clipboard"
pre_output_command = "~/.local/bin/voxpress-save-clipboard-x11"
post_output_command = "~/.local/bin/voxpress-paste-x11"

[output.post_process]
command = "~/.local/bin/voxpress-postprocess-preview"
timeout_ms = 300000
trim = false
fallback_on_empty = false
```

The installer copies:

- scripts to `~/.local/bin/voxpress-*`
- default settings to `~/.config/voxpress/settings.json` if missing
- user services to `~/.config/systemd/user/`
- a `voxtype.service` drop-in that waits for the desktop display environment
  before launching Voxtype
- desktop launchers to `~/.local/share/applications/`

It leaves Voxtype as the transcription backend, but disables the legacy
`voxtype-pause-listener.service` and `voxtype-indicator.service` if they are
present, because those conflict with the Voxpress listener and tray UI. When
Voxpress is enabled, `voxtype.service` is started before the listener. When
Voxpress is disabled from the tray, `voxtype.service` is stopped as well so the
local Whisper model does not keep GPU memory allocated.

## Usage

1. Put focus in an input field or terminal.
2. Hold `Pause` to record.
3. Release `Pause` to transcribe.
4. Edit the preview text if needed.
5. Press `Enter` to insert, or `Scroll Lock` to cancel.

Defaults can be changed from the tray menu:

- hold-to-talk, confirm, and cancel keys
- language mode
- original vs personal fine-tuned recognition model
- preview size, position, opacity, and text size
- append-newline behavior
- correction storage and daily training settings
- Python executable used for offline training

## Personal Custom Training

Personal training is optional. The short version is:

```text
edited preview corrections -> daily LoRA -> GGML export -> quality gate -> stable current model
```

Only manually edited and confirmed preview samples are saved. Daily training can
fine-tune a LoRA adapter from those corrections, merge it into the base Whisper
model, export a whisper.cpp/GGML artifact, test it through Voxtype local mode on
recent corrected samples, and promote it only if it beats the original
`large-v3-turbo` baseline.

By default, corrected audio is capped at `256 MB`; training is capped by both
`30` minutes and `5` epochs; and successful promotion replaces one stable
personal model at:

```text
~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin
```

Timestamped training run directories are temporary workspaces and are pruned
after promotion, so Voxpress does not keep one full model per day.

The tray settings can switch live recognition between the original
`large-v3-turbo` model and the stable personal model. If the original model is
selected, daily training may still update the personal model file, but it will
not silently take over live recognition.

When the personal model is selected, Voxpress removes the original model's
`initial_prompt` from live Voxtype config and keeps a small backup for switching
back. The prompt is useful for the base model, but it can dominate short
utterances from the fine-tuned GGML model.

Training logs include `train-metrics.jsonl` with per-step average loss and a
TensorBoard event stream under:

```text
~/.local/share/voxpress/training-history/tensorboard/YYYY-MM-DD/<run-id>/
```

Open the full training history with:

```bash
voxpress-training-tensorboard
```

Then visit `http://localhost:6006`. The helper uses the configured
`training_python_path` to find the matching `tensorboard` binary. From a source
checkout before install, run `scripts/open-training-tensorboard.sh` instead.
Promotion also writes `model-quality-gate.json`, comparing the exported personal
model against the original model on recent corrected samples. Raw run logs are
mirrored under:

```text
~/.local/share/voxpress/training-history/runs/YYYY-MM-DD/<run-id>/
```

Useful settings in `~/.config/voxpress/settings.json`:

- `correction_collection_enabled`
- `correction_max_storage_mb`
- `recognition_model_mode`
- `auto_train_enabled`
- `auto_train_time`
- `auto_train_max_minutes`
- `auto_train_max_epochs`
- `auto_promote_model`
- `training_python_path`

## Services

```bash
systemctl --user status voxpress-pause-listener.service
systemctl --user status voxpress-indicator.service
systemctl --user restart voxpress-pause-listener.service
systemctl --user restart voxpress-indicator.service
journalctl --user -u voxpress-pause-listener.service -f
```

The tray menu can also enable, disable, or restart the listener. Disabling
Voxpress stops both `voxpress-pause-listener.service` and `voxtype.service`, so
the local Whisper model releases its GPU memory. Enabling Voxpress starts
`voxtype.service` again before starting the listener.

## Credits

Voxpress stands on top of:

- [Voxtype](https://github.com/peteonrails/voxtype) for recording control,
  Whisper model management, and transcription.
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) for local inference
  in Voxtype's local backend.
- [OpenAI Whisper](https://github.com/openai/whisper) for the speech
  recognition model family.
- [OpenCC](https://github.com/BYVoid/OpenCC) for Traditional-to-Simplified
  Chinese conversion.
- GTK, X11/XInput, xclip, and xdotool for Linux desktop integration.

Voxpress is only the glue and UX layer around those projects.

## Status

This is a pragmatic desktop tool currently focused on GNOME/X11-style sessions.
Wayland support is future work because direct key listening and text insertion
need a different strategy there.
