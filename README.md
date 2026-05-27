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
- Automatic newline after confirmed dictation, useful for terminal workflows.
- Clipboard save/restore so the system clipboard is only used transiently.
- Kitty/terminal-aware paste key selection.
- Tray indicator with enable/disable/restart/settings actions.

## Runtime Model

Voxpress keeps the components separate:

- `voxpress-pause-listener` watches XInput key events and calls
  `voxtype record start/stop/cancel`.
- `voxpress-popup-ui` is a GTK socket daemon. It has a non-interactive
  `StatusWindow` for `Recording` / `Transcribing`, and a separate interactive
  `PreviewWindow` for editing confirmed text.
- `voxpress-postprocess-preview` is configured as Voxtype's post-process hook.
  It converts text with OpenCC, opens preview, appends newline if configured,
  and writes an expected-paste marker.
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

Python package:

- `opencc`

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
- recognition language mode

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
