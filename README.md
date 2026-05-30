# Voxpress

Talk is cheap, vibe me the code.

Voxpress is a Linux desktop companion layer for local speech-to-text input. It
uses [Voxtype](https://github.com/peteonrails/voxtype) as the recording and
Whisper transcription engine, then adds an X11 hold-to-talk key, editable GTK
preview, Simplified Chinese conversion, transient clipboard paste, and a tray
settings UI.

This is not a fork of Voxtype. Voxpress is a small integration layer around the
Voxtype CLI and config hooks.

## Features

- Local free speech-to-text through Voxtype and Whisper models.
- Chinese + English constrained recognition by default.
- Hold-to-talk X11 key listener, defaulting to `Pause`.
- Editable GTK preview before insertion.
- Configurable trigger, confirm, and cancel keys from the tray menu.
- Traditional Chinese to Simplified Chinese conversion with OpenCC.
- Optional edited-preview correction dataset collection for personal fine-tuning.
- Daily personal LoRA fine-tune scheduler with NVIDIA GPU idle checks.
- Automatic newline after confirmed dictation, useful for terminal workflows.
- Clipboard save/restore so the system clipboard is only used transiently.
- Kitty/terminal-aware paste key selection.
- Tray indicator with enable/disable/restart/settings actions.

## Runtime Model

Voxpress keeps the components separate:

- `voxpress-pause-listener` watches XInput key events and calls
  `voxtype record start/stop/cancel`.
- `voxpress-popup-ui` is a GTK socket daemon. It has a non-interactive
  `StatusWindow` for `Recording`, `Transcribing`, and `Saved correction`, and a
  separate interactive `PreviewWindow` for editing confirmed text.
- `voxpress-postprocess-preview` is configured as Voxtype's post-process hook.
  It converts text with OpenCC, opens preview, appends newline if configured,
  writes an expected-paste marker, and saves edited preview corrections when a
  captured audio path is available.
- `voxpress-correction-store` stores only manually edited preview samples. Audio
  stays as WAV files under `~/.local/share/voxpress/corrections/audio/`; SQLite
  stores metadata and training history.
- `voxpress-finetune-daily` is run by a user systemd timer. It checks that the
  NVIDIA GPU is idle before training. Training always produces LoRA artifacts;
  automatic promotion is enabled by default after a smoke test and only accepts
  deployable whisper.cpp-style local model artifacts, not Python wrapper markers.
- `voxpress-train-whisper-lora` fine-tunes a LoRA adapter on corrected samples.
- `voxpress-export-whisper-deploy` merges the LoRA into the base Whisper model
  and exports a deployable whisper.cpp GGML artifact.
- `voxpress-save-clipboard-x11` and `voxpress-paste-x11` make clipboard output
  behave like direct input while restoring the user's previous clipboard.
- `voxpress-indicator` provides the tray settings UI.

## Requirements

Voxpress currently targets GNOME/X11-style desktops.

System packages:

- Python 3
- GTK3 / PyGObject (`gi`)
- Ayatana AppIndicator GI bindings
- `xinput`
- `xmodmap`
- `xclip`
- `xdotool`
- `xwininfo`
- `xrandr`
- `notify-send`
- `parec` from PulseAudio/PipeWire tools, used for corrected-sample audio
  capture
- `nvidia-smi` if daily automatic training is enabled

Python package:

- `opencc`

Optional training packages for personal fine-tuning:

- `torch`
- `transformers`
- `peft`
- `soundfile`

Optional deployment tooling for automatic personal-model promotion:

- whisper.cpp conversion tooling exposed through
  `VOXPRESS_WHISPER_CPP_CONVERT_SCRIPT` and `VOXPRESS_OPENAI_WHISPER_REPO`
- optionally an explicitly configured `VOXPRESS_WHISPER_CPP_QUANTIZE_BIN` and
  `VOXPRESS_WHISPER_QUANTIZE_TYPE`; legacy whisper.cpp quantizers are not
  auto-detected because incompatible quantizers can produce loadable but
  degenerate models

Training is capped by both `auto_train_max_minutes` and
`auto_train_max_epochs`; the first limit hit stops the training phase. This keeps
small correction sets from being replayed for the full wall-clock budget.
Export/package conversion is deterministic and has no default timeout; set
`VOXPRESS_EXPORT_TIMEOUT_SECONDS` or `VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS`
only if an operational watchdog is needed.
After a generated model passes the local smoke test, Voxpress switches Voxtype
to that model by default.
The promoted model is copied to a stable path under
`~/.local/share/voxpress/models/current/`, and timestamped training run
directories are pruned after promotion so large intermediate artifacts do not
accumulate.

Runtime dependency:

- `voxtype` installed and configured with a local Whisper model.

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
- settings to `~/.config/voxpress/settings.json` if missing
- user services to `~/.config/systemd/user/`
- desktop launchers to `~/.local/share/applications/`

It keeps `voxtype.service` enabled, but disables the legacy
`voxtype-pause-listener.service` and `voxtype-indicator.service` if they are
present, because those conflict with the Voxpress listener and tray UI.

## Usage

1. Put focus in an input field or terminal.
2. Hold `Pause` to record.
3. Release `Pause` to transcribe.
4. Edit the preview text.
5. Press `Enter` to insert, or `Scroll Lock` to cancel.

Defaults can be changed from the tray menu:

- `Hold-to-talk key`
- `Preview confirm key`
- `Preview cancel key`
- popup opacity, panel alpha, text size, dimensions, position
- append-newline behavior
- correction storage, daily training, and the Python executable used for
  offline training
- recognition language mode

## Personal Custom Training

When preview text is manually edited and confirmed, Voxpress can save that
audio/text pair as a correction sample. Daily training can then fine-tune a LoRA
adapter, export it to a whisper.cpp GGML model, smoke-test it, and switch
Voxtype to the new personal model automatically.

By default, corrected audio is capped at `256 MB`, training is capped by both
`30` minutes and `5` epochs, and successful promotion replaces a single stable
model at:

```text
~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin
```

Timestamped training runs are temporary workspaces and are pruned after
promotion, so Voxpress does not keep one full model per day.

Important knobs in `~/.config/voxpress/settings.json`:

- `correction_collection_enabled`: save edited preview samples.
- `correction_max_storage_mb`: storage cap for correction audio, default `256`.
- `auto_train_enabled`: enable the daily scheduler.
- `auto_train_time`: local 24-hour time gate, default `04:00`.
- `auto_train_max_minutes`: wall-clock training cap, default `30`.
- `auto_train_max_epochs`: sample replay cap, default `5`.
- `auto_promote_model`: switch to the new model after smoke test, default
  `true`.
- `training_python_path`: Python executable with `torch`, `transformers`,
  `peft`, and `soundfile`.

## Services

```bash
systemctl --user status voxpress-pause-listener.service
systemctl --user status voxpress-indicator.service
systemctl --user restart voxpress-pause-listener.service
systemctl --user restart voxpress-indicator.service
journalctl --user -u voxpress-pause-listener.service -f
```

The tray menu can also enable, disable, or restart the listener.

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
