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

## Popup UI

`voxpress-popup-ui` is a GTK daemon with two separate windows:

- `StatusWindow` is non-interactive and focusless. It shows only `Recording`
  and `Transcribing` states.
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

Key names are X11/GDK key names such as `Pause`, `Return`, and `Scroll_Lock`.

## X11 Assumptions

The current implementation assumes an X11 desktop session. Wayland support needs
different key listening and text insertion primitives.
