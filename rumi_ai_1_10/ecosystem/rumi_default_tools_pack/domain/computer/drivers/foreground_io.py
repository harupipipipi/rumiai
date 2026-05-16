"""Foreground visible-screen automation helpers.

These helpers are intentionally small and strict: callers only get success
after an OS API/command completes without error. Missing platform APIs raise
``ForegroundAutomationUnavailable`` instead of silently pretending an action
ran.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class ForegroundAutomationUnavailable(RuntimeError):
    """Raised when the visible-screen automation backend is unavailable."""


def action_api_available(platform_name: str | None = None) -> bool:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return bool(shutil.which("cliclick") or shutil.which("osascript") or _quartz_importable())
    if platform_name == "win32":
        return _powershell_executable() is not None
    return False


def capture_api_available(platform_name: str | None = None) -> bool:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return shutil.which("screencapture") is not None
    if platform_name == "win32":
        return _powershell_executable() is not None
    return False


def capture_visible_screen(platform_name: str | None = None) -> dict[str, Any]:
    platform_name = platform_name or sys.platform
    output = _new_screenshot_path()
    if platform_name == "darwin":
        executable = shutil.which("screencapture")
        if not executable:
            raise ForegroundAutomationUnavailable("screencapture is required for macOS visible-screen capture")
        _run([executable, "-x", str(output)])
        return _screenshot_payload(output, method="screencapture_cli")
    if platform_name == "win32":
        _windows_screenshot(output)
        return _screenshot_payload(output, method="powershell_copyfromscreen")
    raise ForegroundAutomationUnavailable("Visible-screen capture is supported only on macOS and Windows")


def _new_screenshot_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="rumi-local-visible-"))
    return temp_dir / "screenshot.png"


def move(x: int, y: int, platform_name: str | None = None) -> None:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        _darwin_move(x, y)
        return
    if platform_name == "win32":
        _windows_desktop_action("move", {"x": x, "y": y})
        return
    raise ForegroundAutomationUnavailable("Visible-screen cursor movement is supported only on macOS and Windows")


def click(x: int, y: int, button: str = "left", platform_name: str | None = None) -> None:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        _darwin_click(x, y, button)
        return
    if platform_name == "win32":
        _windows_desktop_action("click", {"x": x, "y": y, "button": button})
        return
    raise ForegroundAutomationUnavailable("Visible-screen clicking is supported only on macOS and Windows")


def type_text(text: str, platform_name: str | None = None) -> None:
    if not text:
        raise ValueError("No text supplied for visible-screen typing")
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        _darwin_type(text)
        return
    if platform_name == "win32":
        _windows_desktop_action("type_text", {"text": text})
        return
    raise ForegroundAutomationUnavailable("Visible-screen typing is supported only on macOS and Windows")


def key(key_combo: str, platform_name: str | None = None) -> None:
    if not key_combo:
        raise ValueError("No key supplied for visible-screen key input")
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        _darwin_key(key_combo)
        return
    if platform_name == "win32":
        _windows_desktop_action("key", {"key": key_combo})
        return
    raise ForegroundAutomationUnavailable("Visible-screen key input is supported only on macOS and Windows")


def scroll(
    x: int = 0,
    y: int = 0,
    direction: str = "down",
    clicks: int = 3,
    platform_name: str | None = None,
) -> None:
    if clicks <= 0:
        raise ValueError("Scroll clicks must be greater than zero")
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        _darwin_scroll(x, y, direction, clicks)
        return
    if platform_name == "win32":
        _windows_desktop_action("scroll", {"x": x, "y": y, "direction": direction, "clicks": clicks})
        return
    raise ForegroundAutomationUnavailable("Visible-screen scrolling is supported only on macOS and Windows")


def _screenshot_payload(path: Path, *, method: str) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"{method} did not produce a screenshot")
    data = path.read_bytes()
    return {
        "path": str(path),
        "data_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
        "coordinate_system": "screen_pixels",
        "method": method,
    }


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)


def _quartz_importable() -> bool:
    try:
        import Quartz  # type: ignore[import]  # noqa: F401

        return True
    except Exception:
        return False


def _darwin_move(x: int, y: int) -> None:
    cliclick = shutil.which("cliclick")
    if cliclick:
        _run([cliclick, f"m:{int(x)},{int(y)}"])
        return
    if _quartz_importable():
        code = (
            "import Quartz\n"
            f"Quartz.CGWarpMouseCursorPosition(({int(x)}, {int(y)}))\n"
            "Quartz.CGAssociateMouseAndMouseCursorPosition(True)\n"
        )
        _run([sys.executable, "-c", code])
        return
    raise ForegroundAutomationUnavailable("computer.move requires cliclick or PyObjC Quartz on macOS")


def _darwin_click(x: int, y: int, button: str) -> None:
    button = str(button or "left").lower()
    cliclick = shutil.which("cliclick")
    if cliclick:
        prefix = "rc" if button in {"right", "secondary"} else "c"
        if button in {"middle"}:
            raise ForegroundAutomationUnavailable("macOS middle-click requires a Quartz backend")
        _run([cliclick, f"{prefix}:{int(x)},{int(y)}"])
        return
    if _quartz_importable():
        button_index = 1 if button in {"right", "secondary"} else 0
        if button == "middle":
            raise ForegroundAutomationUnavailable("macOS middle-click is not supported by the Quartz fallback")
        down_event = "kCGEventRightMouseDown" if button_index == 1 else "kCGEventLeftMouseDown"
        up_event = "kCGEventRightMouseUp" if button_index == 1 else "kCGEventLeftMouseUp"
        code = (
            "import Quartz\n"
            f"point = Quartz.CGPoint({int(x)}, {int(y)})\n"
            f"down = Quartz.CGEventCreateMouseEvent(None, Quartz.{down_event}, point, {button_index})\n"
            f"up = Quartz.CGEventCreateMouseEvent(None, Quartz.{up_event}, point, {button_index})\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)\n"
        )
        _run([sys.executable, "-c", code])
        return
    osascript = shutil.which("osascript")
    if osascript and button in {"left", "primary", ""}:
        _run([osascript, "-e", f'tell application "System Events" to click at {{{int(x)}, {int(y)}}}'])
        return
    raise ForegroundAutomationUnavailable("computer.click requires cliclick, PyObjC Quartz, or osascript on macOS")


def _darwin_type(text: str) -> None:
    osascript = shutil.which("osascript")
    if not osascript:
        raise ForegroundAutomationUnavailable("osascript is required for macOS visible-screen typing")
    script = f'tell application "System Events" to keystroke {json.dumps(text, ensure_ascii=True)}'
    _run([osascript, "-e", script])


def _darwin_key(key_combo: str) -> None:
    osascript = shutil.which("osascript")
    if not osascript:
        raise ForegroundAutomationUnavailable("osascript is required for macOS visible-screen key input")
    key, modifiers = _split_key_combo(key_combo)
    using = _apple_script_modifiers(modifiers)
    key_codes = {
        "return": 36,
        "enter": 36,
        "tab": 48,
        "escape": 53,
        "esc": 53,
        "backspace": 51,
        "delete": 51,
        "del": 51,
        "up": 126,
        "down": 125,
        "left": 123,
        "right": 124,
        "space": 49,
    }
    normalized = key.lower()
    if normalized in key_codes:
        script = f'tell application "System Events" to key code {key_codes[normalized]}{using}'
    else:
        script = f'tell application "System Events" to keystroke {json.dumps(key, ensure_ascii=True)}{using}'
    _run([osascript, "-e", script])


def _darwin_scroll(x: int, y: int, direction: str, clicks: int) -> None:
    direction = str(direction or "down").lower()
    if direction in {"left", "right"} and not _quartz_importable():
        raise ForegroundAutomationUnavailable("Horizontal macOS scrolling requires PyObjC Quartz")
    if _quartz_importable():
        dy = -int(clicks) if direction == "down" else int(clicks) if direction == "up" else 0
        dx = -int(clicks) if direction == "right" else int(clicks) if direction == "left" else 0
        code = (
            "import Quartz\n"
            f"event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, {dy}, {dx})\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)\n"
        )
        _run([sys.executable, "-c", code])
        return
    osascript = shutil.which("osascript")
    if not osascript:
        raise ForegroundAutomationUnavailable("computer.scroll requires PyObjC Quartz or osascript on macOS")
    if x or y:
        try:
            _darwin_move(x, y)
        except Exception:
            pass
    amount = int(clicks) if direction == "down" else -int(clicks)
    _run([osascript, "-e", f'tell application "System Events" to scroll wheel {amount}'])


def _apple_script_modifiers(modifiers: list[str]) -> str:
    names: list[str] = []
    for modifier in modifiers:
        normalized = modifier.strip().lower()
        if normalized in {"command", "cmd", "meta", "super"}:
            names.append("command down")
        elif normalized == "shift":
            names.append("shift down")
        elif normalized in {"option", "alt"}:
            names.append("option down")
        elif normalized in {"control", "ctrl"}:
            names.append("control down")
    return "" if not names else " using {" + ", ".join(dict.fromkeys(names)) + "}"


def _split_key_combo(key_combo: str) -> tuple[str, list[str]]:
    parts = [part.strip() for part in str(key_combo).replace("+", " ").split() if part.strip()]
    if not parts:
        raise ValueError("No key supplied for visible-screen key input")
    return parts[-1], parts[:-1]


def _windows_screenshot(path: Path) -> None:
    escaped = _ps_single(str(path))
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "Add-Type -AssemblyName System.Windows.Forms",
            "Add-Type -AssemblyName System.Drawing",
            _windows_dpi_awareness_script(),
            "$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen",
            "$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height",
            "$graphics = [System.Drawing.Graphics]::FromImage($bitmap)",
            "$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)",
            f"$bitmap.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png)",
            "$graphics.Dispose()",
            "$bitmap.Dispose()",
        ]
    )
    _run_powershell(script)


def _windows_desktop_action(action: str, payload: dict[str, Any]) -> None:
    prelude = [
        "$ErrorActionPreference = 'Stop'",
        "Add-Type -AssemblyName System.Windows.Forms",
        "Add-Type -AssemblyName System.Drawing",
        _windows_dpi_awareness_script(),
    ]
    if action == "move":
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        _run_powershell("\n".join(prelude + [f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})"]))
        return
    if action == "click":
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        button = str(payload.get("button") or "left").lower()
        flags = {
            "left": ("0x0002", "0x0004"),
            "primary": ("0x0002", "0x0004"),
            "right": ("0x0008", "0x0010"),
            "secondary": ("0x0008", "0x0010"),
            "middle": ("0x0020", "0x0040"),
        }.get(button)
        if flags is None:
            raise ValueError(f"Unsupported mouse button: {button}")
        down_flag, up_flag = flags
        script = "\n".join(
            prelude
            + [
                _windows_mouse_type(),
                "$original = [System.Windows.Forms.Cursor]::Position",
                f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})",
                f"[RumiMouse]::mouse_event({down_flag}, 0, 0, 0, [UIntPtr]::Zero)",
                f"[RumiMouse]::mouse_event({up_flag}, 0, 0, 0, [UIntPtr]::Zero)",
                "[System.Windows.Forms.Cursor]::Position = $original",
            ]
        )
        _run_powershell(script)
        return
    if action == "type_text":
        text = _ps_single(_windows_sendkeys_escape_text(str(payload.get("text", ""))))
        _run_powershell("\n".join(prelude + [f"[System.Windows.Forms.SendKeys]::SendWait('{text}')"]))
        return
    if action == "key":
        key_value = _windows_send_key(str(payload.get("key", "ENTER")))
        _run_powershell("\n".join(prelude + [f"[System.Windows.Forms.SendKeys]::SendWait('{key_value}')"]))
        return
    if action == "scroll":
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        direction = str(payload.get("direction") or "down").lower()
        clicks = int(payload.get("clicks", 1))
        if clicks <= 0:
            raise ValueError("Scroll clicks must be greater than zero")
        vertical = direction in {"up", "down"}
        event_flag = "0x0800" if vertical else "0x01000"
        sign = 1 if direction in {"up", "right"} else -1
        wheel_delta = sign * clicks * 120
        script = "\n".join(
            prelude
            + [
                _windows_mouse_type(),
                "$original = [System.Windows.Forms.Cursor]::Position",
                f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})",
                f"[RumiMouse]::mouse_event({event_flag}, 0, 0, {wheel_delta}, [UIntPtr]::Zero)",
                "[System.Windows.Forms.Cursor]::Position = $original",
            ]
        )
        _run_powershell(script)
        return
    raise ValueError(action)


def _windows_dpi_awareness_script() -> str:
    return r'''
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class RumiDpi {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@ -ErrorAction SilentlyContinue
[void][RumiDpi]::SetProcessDPIAware()
'''


def _windows_mouse_type() -> str:
    return """Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class RumiMouse {
  [DllImport("user32.dll")]
  public static extern void mouse_event(uint flags, int dx, int dy, int data, UIntPtr extra);
}
'@"""


def _windows_send_key(key: str) -> str:
    raw = key.strip()
    normalized = raw.lower()
    modifiers: list[str] = []
    if "+" in normalized:
        parts = [part for part in normalized.split("+") if part]
        modifiers.extend(parts[:-1])
        normalized = parts[-1] if parts else normalized
        raw = normalized
    key_map = {
        "enter": "{ENTER}",
        "return": "{ENTER}",
        "escape": "{ESC}",
        "esc": "{ESC}",
        "tab": "{TAB}",
        "backspace": "{BACKSPACE}",
        "delete": "{DELETE}",
        "pageup": "{PGUP}",
        "pgup": "{PGUP}",
        "pagedown": "{PGDN}",
        "pgdn": "{PGDN}",
        "home": "{HOME}",
        "end": "{END}",
        "up": "{UP}",
        "down": "{DOWN}",
        "left": "{LEFT}",
        "right": "{RIGHT}",
        "space": " ",
        "plus": "{+}",
    }
    key_token = key_map.get(normalized)
    if key_token is None:
        key_token = raw if len(raw) == 1 else "{" + raw.upper().replace("{", "").replace("}", "") + "}"
    prefix = ""
    for modifier in modifiers:
        if modifier in {"ctrl", "control", "cmd", "command"}:
            prefix += "^"
        elif modifier == "shift":
            prefix += "+"
        elif modifier in {"alt", "option"}:
            prefix += "%"
    return prefix + key_token


def _windows_sendkeys_escape_text(text: str) -> str:
    pieces: list[str] = []
    for char in text:
        if char == "\r":
            continue
        if char == "\n":
            pieces.append("{ENTER}")
        elif char == "\t":
            pieces.append("{TAB}")
        elif char == "{":
            pieces.append("{{}")
        elif char == "}":
            pieces.append("{}}")
        elif char in "+^%~()[]":
            pieces.append("{" + char + "}")
        else:
            pieces.append(char)
    return "".join(pieces)


def _ps_single(value: str) -> str:
    return value.replace("'", "''")


def _powershell_executable() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def _run_powershell(script: str) -> None:
    executable = _powershell_executable()
    if not executable:
        raise ForegroundAutomationUnavailable("PowerShell is required for Windows visible-screen automation")
    args = [executable, "-NoProfile"]
    if Path(executable).name.lower().startswith("powershell"):
        args.extend(["-ExecutionPolicy", "Bypass"])
    args.extend(["-Command", script])
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=15)
