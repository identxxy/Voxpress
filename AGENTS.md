# AGENTS.md

Project-level guidance for agents working on Voxpress.

## Scope

- Keep this file suitable for the public repository.
- Do not put personal machine paths, private workflow notes, credentials,
  unpublished experiments, or local-only session state here.
- Put local/private collaboration notes under `studio/`; that directory is
  intentionally ignored by git.
- Keep durable public project knowledge in `README.md`, `docs/`, or this file.

## Project Identity

- Project name: Voxpress.
- Slogan: "Talk is cheap, vibe me the code."
- Voxpress is not a fork of Voxtype. It is a Linux desktop companion layer
  around Voxtype CLI hooks and services.
- Always credit upstream Voxtype: https://github.com/peteonrails/voxtype.

## Architecture

- `bin/voxpress-pause-listener`
  - X11/XInput hold-to-talk listener.
  - Runs `xinput test-xi2 --root`.
  - Resolves configured `trigger_key` through `xmodmap -pke`.
  - On key press: saves target window, clears expected paste marker, shows
    `recording`, starts corrected-sample audio capture, then runs
    `voxtype record start`.
  - On key release: if shorter than `VOXTYPE_MIN_RECORDING_MS` default 650 ms,
    cancels; otherwise shows `transcribing`, then runs `voxtype record stop`.
  - Corrected-sample audio capture uses `parec` by default to write 16 kHz mono
    WAV under `$XDG_RUNTIME_DIR/voxtype/correction-audio/`. Override with
    `VOXPRESS_AUDIO_CAPTURE_CMD`, where `{path}` is replaced by the target WAV.

- `bin/voxpress-popup-ui`
  - GTK3 daemon using Unix socket `$XDG_RUNTIME_DIR/voxtype/popup-ui.sock`.
  - Commands: `daemon`, `recording`, `transcribing`, `saved-correction`,
    `preview`, `hide`, `ping`.
  - Internally split into `PopupDaemon`, `StatusWindow`, `PreviewWindow`.
  - `StatusWindow` is non-interactive, focusless, pointer-pass-through, and
    normally hidden with opacity 0. It must not share a `Gtk.Window` with
    preview.
  - `PreviewWindow` is interactive, takes focus, and handles text editing.

- `bin/voxpress-postprocess-preview`
  - Voxtype post-process hook.
  - Converts Traditional Chinese to Simplified Chinese using OpenCC `t2s`.
  - Opens GTK preview unless `VOXTYPE_PREVIEW=0`.
  - Restores focus to the target window after preview.
  - Appends newline by default when output is non-empty.
  - Writes `$XDG_RUNTIME_DIR/voxtype/expected_paste_text` for the paste hook.
  - Saves a correction sample only when the preview text was manually edited and
    confirmed. Unchanged and canceled previews delete the temporary correction
    audio.

- `bin/voxpress-run-with-user-env`
  - Small launcher used by the installed `voxtype.service` drop-in.
  - Waits for `DISPLAY`/`WAYLAND_DISPLAY`, imports graphical-session variables
    from `systemctl --user show-environment`, then `exec`s the real command.
  - This prevents Voxtype from starting after reboot without `DISPLAY` /
    `XAUTHORITY`, which breaks preview, X11 clipboard output, and paste hooks.

- `bin/voxpress-correction-store`
  - Stores edited correction samples under
    `~/.local/share/voxpress/corrections/`.
  - Audio is stored as WAV files under `audio/YYYY-MM-DD/`; metadata is stored
    in `index.sqlite`.
  - Applies both storage and sample-count retention. Defaults are 256 MB and
    1000 samples.

- `bin/voxpress-finetune-daily`
  - User systemd timer entrypoint for personal training.
  - Timer wakes every 15 minutes; the script gates actual work by
    `auto_train_time` and records one attempt per day.
  - Before training, it checks `nvidia-smi` repeatedly. Defaults: 2 checks,
    300 seconds apart, GPU/process utilization threshold 30%, process memory
    threshold 4096 MB.
  - Trains only on corrected samples. There is no held-out evaluation set.
  - Promotes only deployable local whisper.cpp/GGML model artifacts.
  - Promotion writes `[whisper].model` in `~/.config/voxtype/config.toml` and
    removes experimental `mode = "cli"` / `whisper_cli_path` keys.
  - Promotion first smoke-tests through Voxtype local mode and rejects empty or
    degenerate outputs.
  - The promoted model is copied to
    `~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin`.
    Timestamped run directories are temporary and are pruned after successful
    promotion, leaving only small logs/manifests for the active run.

- `bin/voxpress-train-whisper-lora`
  - Fine-tunes a LoRA adapter from corrected samples.
  - Default base model is `openai/whisper-large-v3-turbo`.
  - Uses `torch`, `transformers`, `peft`, and `soundfile`.
  - Training stops when either `--max-minutes` or `--max-epochs` is reached.
    The epoch cap prevents tiny correction sets from replaying for the whole
    wall-clock budget.
  - Writes adapter, processor, export logs, and `train-result.json` into the
    timestamped run directory.

- `bin/voxpress-export-whisper-deploy`
  - Merges LoRA into the base Hugging Face Whisper model.
  - Converts the merged model to whisper.cpp GGML using
    `convert-h5-to-ggml.py`.
  - Default tool root is `~/.local/share/voxpress/tools`.
  - Default converter path is
    `~/.local/share/voxpress/tools/whisper.cpp/models/convert-h5-to-ggml.py`.
  - Default OpenAI Whisper assets/repo path is
    `~/.local/share/voxpress/tools/whisper`; the converter needs
    `whisper/assets/mel_filters.npz` there.
  - whisper.cpp quantizers are not auto-detected because an older quantizer
    produced loadable but degenerate large-v3-turbo output. Use an explicit
    `VOXPRESS_WHISPER_CPP_QUANTIZE_BIN` only after validating that binary on the
    target model family.

- `bin/voxpress-save-clipboard-x11` and `bin/voxpress-paste-x11`
  - Save current clipboard before Voxtype writes output.
  - Paste only if clipboard matches the expected marker.
  - Repair trailing newline if Voxtype clipboard output strips it.
  - Restore the previous clipboard in the background after paste.
  - Terminal windows use `Ctrl+Shift+V`; other GUI windows use `Shift+Insert`.

- `bin/voxpress-indicator`
  - Ayatana AppIndicator tray UI.
  - Provides enable/disable/restart/settings.
  - Settings dialog writes `~/.config/voxpress/settings.json`.
  - Language changes update `~/.config/voxtype/config.toml` and restart
    `voxtype.service`.
  - Hold-to-talk key changes restart `voxpress-pause-listener.service`.

## Dependencies

Runtime desktop dependencies:

- Python 3.
- GTK3 / PyGObject (`gi`).
- Ayatana AppIndicator GI bindings.
- `xinput`, `xmodmap`, `xclip`, `xdotool`, `xwininfo`, `xrandr`, `notify-send`.
- `parec` from PulseAudio/PipeWire tooling for corrected-sample WAV capture.
- Voxtype installed and configured with local Whisper inference.

Python runtime package:

- `opencc`.

Personal training dependencies:

- Python env with `torch`, `transformers`, `peft`, and `soundfile`.
- `nvidia-smi` if automatic GPU-idle gating is enabled.
- Hugging Face access/cache for the configured base model, default
  `openai/whisper-large-v3-turbo`.
- Enough local disk for a temporary merged Hugging Face model and one
  whisper.cpp/GGML export during training. Successful promotion prunes most
  run-local large artifacts, but the active run needs working space first.

Deployment/export tooling:

- `~/.local/share/voxpress/tools/whisper.cpp/models/convert-h5-to-ggml.py`.
  This can be the converter script from whisper.cpp.
- `~/.local/share/voxpress/tools/whisper/whisper/assets/mel_filters.npz`.
  The easiest source is the OpenAI Whisper Python package source tree.
- Optional: a validated modern whisper.cpp quantizer. Voxpress does not
  auto-detect quantizers; set `VOXPRESS_WHISPER_CPP_QUANTIZE_BIN` only after the
  exact binary has passed a real Voxtype smoke test on the target model family.

Minimal deployment-tool bootstrap:

```bash
mkdir -p ~/.local/share/voxpress/tools/whisper.cpp/models
curl -L \
  https://raw.githubusercontent.com/ggerganov/whisper.cpp/master/models/convert-h5-to-ggml.py \
  -o ~/.local/share/voxpress/tools/whisper.cpp/models/convert-h5-to-ggml.py

python -m pip download --no-deps openai-whisper -d /tmp/voxpress-whisper-download
python - <<'PY'
import tarfile
from pathlib import Path

download_dir = Path("/tmp/voxpress-whisper-download")
target = Path.home() / ".local/share/voxpress/tools/whisper"
target.mkdir(parents=True, exist_ok=True)
archive = sorted(download_dir.glob("openai_whisper-*.tar.gz"))[-1]
with tarfile.open(archive) as tar:
    members = [
        member for member in tar.getmembers()
        if "/whisper/assets/" in member.name or member.name.endswith("/whisper/__init__.py")
    ]
    tar.extractall(target, members=members)
root = next(target.glob("openai_whisper-*"))
for child in root.iterdir():
    destination = target / child.name
    if destination.exists():
        continue
    child.rename(destination)
root.rmdir()
PY
```

After bootstrap, verify:

```bash
python -m py_compile ~/.local/share/voxpress/tools/whisper.cpp/models/convert-h5-to-ggml.py
python - <<'PY'
import numpy as np
from pathlib import Path

path = Path.home() / ".local/share/voxpress/tools/whisper/whisper/assets/mel_filters.npz"
data = np.load(path)
print(sorted(data.files))
PY
```

If present, `scripts/install-training-tools.sh` may be used as a convenience
bootstrap for the converter and OpenAI Whisper assets, but it intentionally does
not install training Python packages or enable quantization. It should not be
treated as replacing the manual path checks above. If present,
`scripts/doctor.sh` may be used as a convenience environment audit, but agents
should still inspect the exact missing dependency or failed smoke-test reason
before changing code.

## Environment Overrides

Desktop/correction collection:

- `VOXPRESS_SETTINGS` / `VOXTYPE_POPUP_SETTINGS`: settings JSON path.
- `VOXPRESS_AUDIO_CAPTURE_CMD`: audio capture command template using `{path}`.
- `VOXPRESS_AUDIO_DEVICE`: source passed to the default `parec` capture path.
- `VOXPRESS_CORRECTION_COLLECTION`: enable/disable correction sample capture.
- `VOXPRESS_CORRECTION_STORE`: post-process hook path for
  `voxpress-correction-store`.
- `VOXPRESS_CORRECTION_DIR`: correction store root; defaults to
  `~/.local/share/voxpress/corrections`.
- `VOXPRESS_CORRECTION_MAX_STORAGE_MB`: corrected-audio retention cap.
- `VOXPRESS_CORRECTION_MAX_SAMPLES`: corrected-sample count retention cap.
- `VOXTYPE_AUDIO_PATH`: explicit audio path for post-process tests or custom
  integrations.
- `VOXTYPE_AUDIO_DURATION_SECONDS`: explicit audio duration metadata.

Daily scheduler and promotion:

- `VOXPRESS_AUTO_TRAIN_ENABLED`: override the daily training enable switch.
- `VOXPRESS_AUTO_TRAIN_MAX_MINUTES`: wall-clock training budget.
- `VOXPRESS_AUTO_TRAIN_MAX_EPOCHS`: corrected-sample replay cap.
- `VOXPRESS_AUTO_PROMOTE_MODEL`: enable/disable automatic promotion after a
  deployable train result.
- `VOXPRESS_GPU_CHECK_COUNT`: number of idle checks before training.
- `VOXPRESS_GPU_CHECK_INTERVAL_SECONDS`: delay between idle checks.
- `VOXPRESS_GPU_BUSY_UTILIZATION_PERCENT`: GPU utilization busy threshold.
- `VOXPRESS_GPU_BUSY_PROCESS_MEMORY_MB`: process memory busy threshold.
- `VOXPRESS_NVIDIA_SMI`: explicit `nvidia-smi` binary/path for GPU checks.
- `VOXPRESS_MODEL_RUNS_DIR`: timestamped training workspace root; defaults to
  `~/.local/share/voxpress/models/runs`.
- `VOXPRESS_CURRENT_MODEL_PATH`: stable promoted GGML model path; defaults to
  `~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin`.
- `VOXPRESS_TRAIN_PYTHON`: Python executable for training/export.
- `VOXPRESS_TRAIN_COMMAND`: custom training command template. Supported fields
  are `{manifest}`, `{output_dir}`, `{max_minutes}`, and `{max_epochs}`.
- `VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS`: optional scheduler-level watchdog.
- `VOXPRESS_MODEL_SMOKE_TIMEOUT_SECONDS`: Voxtype model smoke-test timeout.
- `VOXPRESS_SKIP_MODEL_SMOKE_TEST`: test-only escape hatch; do not use for
  real promotion unless the caller deliberately accepts bad-model risk.
- `VOXPRESS_VOXTYPE_BIN`: Voxtype CLI path used by the smoke test.
- `VOXTYPE_CONFIG_PATH`: Voxtype config path updated during promotion.
- `VOXPRESS_SYSTEMCTL`: `systemctl` path/command used to restart Voxtype.
- `VOXPRESS_WHISPER_CLI_WRAPPER`: wrapper path used to identify non-promotable
  dry-run or CLI-wrapper artifacts.

LoRA training:

- `VOXPRESS_BASE_WHISPER_MODEL`: Hugging Face base model.
- `VOXPRESS_TRAIN_LANGUAGE`: Whisper processor language; default `zh`.
- `VOXPRESS_TRAIN_MAX_EPOCHS`: direct trainer default when the scheduler does
  not pass `--max-epochs`.
- `VOXPRESS_TRAIN_MAX_STEPS`: trainer step cap.
- `VOXPRESS_TRAIN_BATCH_SIZE`: microbatch size.
- `VOXPRESS_TRAIN_GRAD_ACCUM`: gradient accumulation steps.
- `VOXPRESS_TRAIN_LR`: AdamW learning rate.
- `VOXPRESS_LORA_RANK`: LoRA rank.
- `VOXPRESS_LORA_ALPHA`: LoRA alpha.
- `VOXPRESS_EXPORT_TIMEOUT_SECONDS`: optional exporter subprocess timeout.
- `VOXPRESS_DRY_RUN_DEPLOY_MODEL`: dry-run trainer output marker path for
  tests; marker artifacts are intentionally not promotable.

Export/deployment:

- `VOXPRESS_WHISPER_TOOL_ROOT`: root for local whisper tooling.
- `VOXPRESS_WHISPER_CPP_CONVERT_SCRIPT`: explicit whisper.cpp converter script.
- `VOXPRESS_OPENAI_WHISPER_REPO`: explicit OpenAI Whisper source/assets path.
- `VOXPRESS_WHISPER_EXPORT_COMMAND`: custom export command template. Supported
  fields are `{base_model}`, `{adapter_dir}`, `{processor_dir}`, `{merged_dir}`,
  and `{output_dir}`.
- `VOXPRESS_WHISPER_CPP_QUANTIZE_BIN`: explicit quantizer binary.
- `VOXPRESS_WHISPER_QUANTIZE_TYPE`: quantization type; use `none`/`off` to
  disable quantization.

## Custom Training Pipeline

The personal training pipeline is intentionally local, bounded, and conservative.
It learns only from manually edited preview corrections, not from every accepted
transcription.

Data flow:

- `bin/voxpress-pause-listener` starts a temporary 16 kHz mono WAV capture on
  hold-to-talk press and records the pending path under
  `$XDG_RUNTIME_DIR/voxtype/correction_audio_path`.
- `bin/voxpress-postprocess-preview` owns the save decision. It saves only when
  preview text was edited and confirmed. Unchanged text, canceled preview, short
  taps, empty output, and missing audio should delete the temporary audio.
- `bin/voxpress-correction-store save-edited` moves the temporary WAV into the
  durable correction store and inserts metadata into SQLite. It enforces both
  byte and sample-count retention immediately after each insert.
- `bin/voxpress-finetune-daily run` is the scheduler entrypoint. It gates work
  by `auto_train_enabled`, `auto_train_time`, one attempt per local day, sample
  availability, GPU idle checks, and trainer dependency checks.
- The scheduler writes a `train-manifest.json` into a timestamped run directory,
  launches `bin/voxpress-train-whisper-lora`, captures `train.stdout.log` and
  `train.stderr.log`, and records training status in the correction database.
- `bin/voxpress-train-whisper-lora` loads the manifest, checks WAV sample rate,
  fine-tunes LoRA adapters on Whisper, writes `adapter/`, `processor/`, and
  delegates deployable artifact creation to `bin/voxpress-export-whisper-deploy`.
- `bin/voxpress-export-whisper-deploy` merges LoRA into the base Hugging Face
  model, converts the merged model to whisper.cpp/GGML, optionally applies an
  explicitly validated quantizer, and reports `deploy_model_path` as JSON.
- The scheduler promotes only real local whisper.cpp/GGML artifacts. It rejects
  dry-run wrapper markers, missing files, empty smoke output, and degenerate
  repeated-token smoke output.
- Promotion copies the deploy artifact to the stable current-model path, updates
  `[whisper].model` in the Voxtype config, removes experimental
  `[whisper].mode` / `whisper_cli_path` keys, restarts `voxtype.service`, records
  promotion metadata, and prunes large run artifacts.

Default data paths:

- Temporary correction audio:
  `$XDG_RUNTIME_DIR/voxtype/correction-audio/`.
- Pending correction markers:
  `$XDG_RUNTIME_DIR/voxtype/correction_audio_path` and
  `$XDG_RUNTIME_DIR/voxtype/correction_audio_duration`.
- Durable correction root:
  `~/.local/share/voxpress/corrections/`.
- Correction audio:
  `~/.local/share/voxpress/corrections/audio/YYYY-MM-DD/*.wav`.
- Correction database:
  `~/.local/share/voxpress/corrections/index.sqlite`.
- Daily scheduler state:
  `~/.local/share/voxpress/corrections/auto_train_state.json`.
- Training runs:
  `~/.local/share/voxpress/models/runs/<timestamp>/`.
- Stable promoted model:
  `~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin`.
- Stable promoted metadata:
  `~/.local/share/voxpress/models/current/metadata.json`.
- Default training tool root:
  `~/.local/share/voxpress/tools/`.

Training run contents:

- `train-manifest.json`: snapshot of selected correction samples.
- `train.stdout.log` / `train.stderr.log`: scheduler-captured trainer logs.
- `adapter/`: PEFT LoRA adapter, temporary after successful promotion.
- `processor/`: matching Whisper processor, temporary after successful
  promotion.
- `deploy/`: merged/exported model workspace, temporary after successful
  promotion.
- `deploy/merged-hf/`: intermediate merged Hugging Face model.
- `deploy/whisper-cpp-convert.stdout.log` and
  `deploy/whisper-cpp-convert.stderr.log`: converter logs.
- `deploy/custom-export.stdout.log` and `deploy/custom-export.stderr.log`:
  custom exporter logs when `VOXPRESS_WHISPER_EXPORT_COMMAND` is used.
- `model-smoke.config.toml`, `model-smoke.stdout.log`,
  `model-smoke.stderr.log`: promotion smoke-test artifacts.
- `train-result.json`: source of truth for train/export/promotion result.

## Settings Schema

Default settings live in `config/settings.example.json`.

Important keys:

- `trigger_key`: default `Pause`.
- `confirm_key`: default `Return`, displayed as Enter.
- `cancel_key`: default `Scroll_Lock`, displayed as Scroll Lock.
- `append_newline`: default true.
- `language_mode`: one of `zh_en`, `zh`, `en`, `auto`.
- `correction_collection_enabled`: default true.
- `correction_max_storage_mb`: default 256.
- `correction_max_samples`: default 1000.
- `auto_train_enabled`: default true.
- `auto_train_time`: default `04:00`.
- `auto_train_max_minutes`: default 30.
- `auto_train_max_epochs`: default 5.
- `auto_promote_model`: default true.
- `training_python_path`: optional Python executable path for training/export.
- `gpu_check_count`, `gpu_check_interval_seconds`,
  `gpu_busy_utilization_percent`, `gpu_busy_process_memory_mb`.
- `window_opacity`, `panel_alpha`, `text_bg_alpha`, `button_alpha`.
- `status_width`, `status_height`, `preview_width`, `preview_height`.
- `horizontal_fraction`, `vertical_fraction`.

Key names are X11/GDK key names, not arbitrary labels. Existing aliases:

- `Enter` -> `Return`
- `Scroll Lock` -> `Scroll_Lock`
- `Backspace` -> `BackSpace`

## X11 And GTK Design Notes

- X11 window mapping, move, resize, and configure events are asynchronous.
- The old single-window design reused one GTK toplevel for status and preview.
  This can show status UI at a window-manager-selected or stale location before
  later `move()` calls are processed.
- The current fix is structural: status and preview are separate windows.
- Status uses `Gtk.WindowType.POPUP` by default. It can be forced to toplevel
  with `VOXTYPE_STATUS_WINDOW_TYPE=toplevel`.
- Opacity 0 does not imply pointer pass-through. Status uses an empty input
  shape via `input_shape_combine_region(cairo.Region())`.
- Preview must not use pointer pass-through.
- Preview focus is enforced with GTK focus calls and optional `xdotool`
  `windowraise/windowactivate/windowfocus`.

## Clipboard Design Notes

- Voxpress still uses the X11 clipboard as the text transport layer because it
  is more reliable for CJK text in arbitrary GUI and terminal apps than direct
  key event synthesis.
- It is transient: the old clipboard is saved before Voxtype output and restored
  after paste.
- The paste hook must see a fresh expected marker before pasting. This prevents
  short taps or silent audio from pasting stale text.
- `xclip` should run in the background when restoring clipboard ownership.
  Running it in the foreground can block Voxtype's post-output hook.

## Personal Training Design Notes

- Only manually edited preview samples are saved. Do not save unchanged
  transcriptions as training data.
- The correction store is the only durable training dataset. Temporary audio in
  `$XDG_RUNTIME_DIR` is an implementation detail and should be removed unless a
  confirmed edit is saved.
- Corrected audio lives outside git under `~/.local/share/voxpress/corrections/`.
  Do not commit audio samples, SQLite data, model weights, Hugging Face caches,
  or whisper.cpp build trees.
- The model directory is intentionally bounded. After promotion, the only large
  long-lived artifact should be
  `~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin`.
- `runs/<timestamp>/` directories are workspaces for training/export logs. After
  successful promotion, large run artifacts (`deploy/`, `adapter/`,
  `processor/`, `*.bin`) are deleted.
- The scheduler records one attempt per local day only after a train attempt,
  failed train spawn, timeout, smoke failure, non-promoted train, or promotion
  result. Dependency-missing skips should not consume the daily attempt.
- The trainer uses a small LoRA adaptation over Whisper attention projections.
  This keeps personal updates cheap and bounded, but also means bad correction
  samples have high leverage when the dataset is tiny.
- The `--max-epochs` cap is as important as `--max-minutes`: with a very small
  correction set, replaying the same edits for the full wall-clock budget can
  overfit or destabilize the adapter.
- The current pipeline has no held-out evaluation set. Promotion quality is
  protected only by a deployability check plus a real Voxtype smoke test on a
  correction sample.
- Export/package conversion has no default timeout. Use
  `VOXPRESS_EXPORT_TIMEOUT_SECONDS` or `VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS`
  only as operational watchdogs.
- Smoke testing must load the model through a temporary Voxtype config with
  `[whisper].model` set to the absolute GGML path and `--whisper-mode local`.
  Passing the absolute path via `voxtype --model` is not equivalent; Voxtype's
  CLI `--model` accepts built-in model names and can silently fall back.
- A deployable model can still be bad. Keep `is_degenerate_transcription`
  conservative and extend it when a real failed smoke output is observed.
- If quantization is added, validate it by loading the exact quantized output
  with Voxtype and checking the transcription text. Older whisper.cpp quantizers
  can produce smaller models that load but repeat tokens.

## Validation Commands

Run these after meaningful edits:

```bash
python -m py_compile bin/voxpress-popup-ui bin/voxpress-pause-listener bin/voxpress-indicator bin/voxpress-postprocess-preview bin/voxpress-correction-store bin/voxpress-finetune-daily bin/voxpress-train-whisper-lora bin/voxpress-export-whisper-deploy bin/voxpress-whisper-cli-wrapper bin/voxpress-run-with-user-env
python -m unittest tests/test_voxpress_postprocess.py tests/test_voxpress_popup_ui.py tests/test_voxpress_listener_audio.py tests/test_voxpress_paste_x11.py tests/test_voxpress_correction_store.py tests/test_voxpress_finetune_daily.py tests/test_voxpress_export_whisper_deploy.py tests/test_voxpress_train_whisper_lora.py
bash -n bin/voxpress-paste-x11 scripts/install.sh scripts/doctor.sh scripts/install-training-tools.sh
bin/voxpress-indicator check
bin/voxpress-popup-ui ping
```

For documentation-only edits to this file, at minimum run:

```bash
git diff --check -- AGENTS.md
rg -n '(/[h]ome/vox|/[m]nt/afs|x[i]nyuan|run_[0-9]|api[_-]?key|[p]assword|[s]ecret)' AGENTS.md
```

Training-specific validation:

- Dependency check:

  ```bash
  bin/voxpress-train-whisper-lora --check-deps
  ```

- Export tooling check: verify the converter compiles and the OpenAI Whisper
  assets file contains usable mel filters:

  ```bash
  python -m py_compile ~/.local/share/voxpress/tools/whisper.cpp/models/convert-h5-to-ggml.py
  python - <<'PY'
import numpy as np
from pathlib import Path

path = Path.home() / ".local/share/voxpress/tools/whisper/whisper/assets/mel_filters.npz"
data = np.load(path)
print(sorted(data.files))
PY
  ```

- Scheduler GPU gate:

  ```bash
  bin/voxpress-finetune-daily check-gpu
  ```

- Safe scheduler dry/smoke validation: use a temporary `VOXPRESS_CORRECTION_DIR`
  and `VOXPRESS_MODEL_RUNS_DIR`, or the unit tests, unless the user explicitly
  wants to train on their real correction store. Avoid running a real full
  fine-tune as a generic validation step.
- Promotion validation: confirm the promoted model path is the stable current
  model, then verify Voxtype local mode loads that exact path instead of falling
  back to a built-in model.
- If `scripts/doctor.sh` exists, it can be run as an additional audit. If
  `scripts/install-training-tools.sh` exists, use it only as a bootstrap helper;
  still verify the converter/assets/quantizer paths above.

On a live install:

```bash
systemctl --user is-active voxtype.service voxpress-pause-listener.service voxpress-indicator.service
journalctl --user -u voxpress-finetune-daily.service -n 50 --no-pager
journalctl --user -u voxpress-pause-listener.service -n 20 --no-pager
```

Useful smoke tests:

- Preview confirm: open preview, send configured confirm key, assert stdout
  equals input.
- Preview cancel: open preview, press `Delete`, assert process is still
  running; press configured cancel key, assert stdout is empty.
- Listener key resolution: verify the configured `trigger_key` resolves through
  `xmodmap -pke` on the current X11 session.
- Custom model smoke: verify Voxtype loads
  `~/.local/share/voxpress/models/current/voxpress-personal-whisper.bin` from
  config and does not fall back to a built-in model.

## Known Limits

- Wayland support is not implemented. XInput listening and X11 paste behavior
  need replacement there.
- Streaming partial preview is not implemented. Current preview is final
  editable preview after Whisper transcription.
- Voxpress assumes Voxtype is already installed and configured with a model.
- The setup is designed for local desktop usage, not packaged distro install.
