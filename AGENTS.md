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
    `recording`, then runs `voxtype record start`.
  - On key release: if shorter than `VOXTYPE_MIN_RECORDING_MS` default 650 ms,
    cancels; otherwise shows `transcribing`, then runs `voxtype record stop`.

- `bin/voxpress-popup-ui`
  - GTK3 daemon using Unix socket `$XDG_RUNTIME_DIR/voxtype/popup-ui.sock`.
  - Commands: `daemon`, `recording`, `transcribing`, `preview`, `hide`, `ping`.
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

## Settings Schema

Default settings live in `config/settings.example.json`.

Important keys:

- `trigger_key`: default `Pause`.
- `confirm_key`: default `Return`, displayed as Enter.
- `cancel_key`: default `Scroll_Lock`, displayed as Scroll Lock.
- `append_newline`: default true.
- `language_mode`: one of `zh_en`, `zh`, `en`, `auto`.
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

## Validation Commands

Run these after meaningful edits:

```bash
python -m py_compile bin/voxpress-popup-ui bin/voxpress-pause-listener bin/voxpress-indicator bin/voxpress-postprocess-preview
python -m unittest tests/test_voxpress_postprocess.py
bin/voxpress-indicator check
bin/voxpress-popup-ui ping
```

On a live install:

```bash
systemctl --user is-active voxtype.service voxpress-pause-listener.service voxpress-indicator.service
journalctl --user -u voxpress-pause-listener.service -n 20 --no-pager
```

Useful smoke tests:

- Preview confirm: open preview, send configured confirm key, assert stdout
  equals input.
- Preview cancel: open preview, press `Delete`, assert process is still
  running; press configured cancel key, assert stdout is empty.
- Listener key resolution: verify the configured `trigger_key` resolves through
  `xmodmap -pke` on the current X11 session.

## Known Limits

- Wayland support is not implemented. XInput listening and X11 paste behavior
  need replacement there.
- Streaming partial preview is not implemented. Current preview is final
  editable preview after Whisper transcription.
- Voxpress assumes Voxtype is already installed and configured with a model.
- The setup is designed for local desktop usage, not packaged distro install.
