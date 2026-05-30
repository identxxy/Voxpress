# Voxpress Architecture

Voxpress is a desktop companion layer around Voxtype. It does not perform ASR
itself; Voxtype records audio and runs Whisper-compatible transcription, while
Voxpress handles the desktop input workflow.

## Flow

1. `voxpress-pause-listener` watches an X11 key using XInput.
2. On key press, it calls `voxtype record start` and shows the status popup.
3. On key release, it calls `voxtype record stop` and shows transcribing state.
4. Voxtype sends recognized text to `voxpress-postprocess-preview`.
5. The post-process hook converts Traditional Chinese to Simplified Chinese,
   opens editable preview, and writes the confirmed text back to stdout.
6. Voxtype places the final text on the clipboard.
7. `voxpress-paste-x11` verifies the expected text marker, pastes into the
   target window, and restores the previous clipboard.

If correction collection is enabled, `voxpress-pause-listener` also records a
parallel 16 kHz mono WAV using PulseAudio/PipeWire while Voxtype records. The
temporary audio path is written into runtime state before Voxtype runs the
post-process hook. `voxpress-postprocess-preview` saves the audio only when the
user edited the preview text; unchanged and canceled previews delete the
temporary audio.

## Popup UI

`voxpress-popup-ui` is a GTK daemon with two separate windows:

- `StatusWindow` is non-interactive and focusless. It shows `Recording`,
  `Transcribing`, and auto-hidden `Saved correction` states.
- `PreviewWindow` is interactive. It owns text editing, confirm, and cancel.

Status and preview deliberately do not share one GTK toplevel. X11 window
mapping and configure events are asynchronous, and a shared toplevel can show a
transient frame at a stale or window-manager-selected position before the final
move/resize is processed.

## Settings

Settings live in `~/.config/voxpress/settings.json` by default. See
`config/settings.example.json`.

Important fields:

- `trigger_key`
- `confirm_key`
- `cancel_key`
- `append_newline`
- `language_mode`
- popup opacity, size, and position fields
- correction dataset storage cap and daily training controls

Key names are X11/GDK key names such as `Pause`, `Return`, and `Scroll_Lock`.

## X11 Assumptions

The current implementation assumes an X11 desktop session. Wayland support needs
different key listening and text insertion primitives.

## Personal Fine-Tuning

`voxpress-correction-store` keeps edited correction samples under
`~/.local/share/voxpress/corrections/`. Audio is stored as WAV files and metadata
is stored in SQLite.

`voxpress-finetune-daily.timer` wakes the scheduler every 15 minutes. The script
uses the configured daily training time and records one attempt per day. Before
training it performs repeated `nvidia-smi` checks; if the GPU is busy, training
is skipped and retried later.

Successful LoRA training saves the adapter and processor as offline training
artifacts. `voxpress-export-whisper-deploy` can then merge the LoRA into the
base Hugging Face Whisper model and hand the merged model to a configured
whisper.cpp conversion pipeline. If no conversion tooling is configured, the run
is recorded as trained but not deployable.

`auto_train_max_minutes` and `auto_train_max_epochs` both limit the training
phase; the first limit hit stops training. The epoch cap prevents very small
correction sets from being replayed until the full wall-clock budget is used.
Export/package conversion is treated as deterministic packaging and has no
default timeout. Operators can set `VOXPRESS_EXPORT_TIMEOUT_SECONDS` for the
export subprocess or `VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS` for the whole daily
run if they want a separate watchdog.

Promotion only accepts deployable local whisper.cpp-style model artifacts. It
sets `[whisper].model` to that artifact and removes any experimental `cli`
wrapper settings, so realtime press-to-talk stays on Voxtype's local backend.
Promotion is enabled by default after the generated model passes a smoke test.
Legacy whisper.cpp quantizers are not auto-detected; operators can still opt in
with `VOXPRESS_WHISPER_CPP_QUANTIZE_BIN` after validating the binary on the
target model family.

The promoted model is copied to
`~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin`, and
Voxtype is pointed at that stable path. Timestamped run directories are treated
as temporary workspaces: after a successful promotion, older run directories are
deleted and the active run keeps only small logs and manifests.
Promotion runs a local Voxtype smoke transcription before switching the active
model and rejects degenerate outputs such as repeated punctuation. Python
wrapper markers are treated as training/debug artifacts and are not promotable.
