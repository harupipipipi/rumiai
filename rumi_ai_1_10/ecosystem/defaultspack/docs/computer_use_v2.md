# Computer Use v2

Computer Use v2 is the final OS interaction layer. Browser-specific work should prefer Browser v2; screen-level fallback, desktop apps, active windows, clipboard, hotkeys, and external send flows use `computer_use`.

## Actions

The existing screenshot / move / click / type / key / scroll actions remain compatible. PR56 adds:

| action | purpose |
|---|---|
| `computer.health` | platform and controller readiness |
| `computer.permissions` | macOS / Windows preflight |
| `computer.displays.list` | display geometry and scale metadata |
| `computer.active_window` | foreground app/window metadata |
| `computer.windows.list` | visible window list |
| `computer.window.focus` | focus a known app/window |
| `computer.window.bounds` | window bounds |
| `computer.hotkey` | chorded key input |
| `computer.clipboard.read` | clipboard inspection |
| `computer.clipboard.write` | clipboard mutation |
| `computer.app.open` | open an app |
| `computer.app.focus` | focus an app |

## Permission Preflight

macOS preflight reports:

```text
screen_recording
accessibility
automation_system_events
screencapture_available
osascript_available
quartz_available
cliclick_available
```

Windows preflight reports:

```text
powershell_available
pwsh_available
forms_available
drawing_available
desktop_session_active
screen_locked
dpi_scale
```

The screenshot result includes display, DPI, and active-window metadata when available. Tests mock platform-specific calls so CI does not require desktop permissions.

## Risk Levels

Actions are classified before execution:

| risk | examples |
|---|---|
| low | screen read, pointer move |
| medium | click, type, hotkey, clipboard read/write |
| high | file upload, external send, credential input |
| irreversible | payment, delete |

High-risk actions can require central approval even when a client supplies `approved: true`; only server-side approval decisions are trusted.
