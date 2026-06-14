"""Win32 PostMessage helpers for background-ish input attempts."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

from .coords import client_to_screen, make_lparam
from .integrity import can_post_to_hwnd

_IS_WINDOWS = sys.platform == "win32"
_user32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WINDOWS else None
if _user32 is not None:
    _user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.ScreenToClient.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.POINT),
    ]
    _user32.ScreenToClient.restype = wintypes.BOOL

WM_CHAR = 0x0102
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010
WHEEL_DELTA = 120
_SCREEN_COORDINATE_SPACES = {"screen", "desktop", "global"}

VK_CODES: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
}


def _int_point(x: Any, y: Any) -> tuple[int, int]:
    try:
        point_x = int(x)
    except (TypeError, ValueError):
        point_x = 0
    try:
        point_y = int(y)
    except (TypeError, ValueError):
        point_y = 0
    return point_x, point_y


def _coordinate_space(value: str | None) -> str:
    return str(value or "client").strip().lower()


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert a screen point to HWND client coordinates, returning input on failure."""
    point_x, point_y = _int_point(x, y)
    if not _user32 or not hwnd:
        return point_x, point_y
    point = wintypes.POINT(point_x, point_y)
    try:
        ok = _user32.ScreenToClient(
            wintypes.HWND(int(hwnd)),
            ctypes.byref(point),
        )
    except Exception:
        return point_x, point_y
    if not ok:
        return point_x, point_y
    return int(point.x), int(point.y)


def resolve_client_point(
    hwnd: int,
    x: int,
    y: int,
    *,
    coordinate_space: str | None = "client",
    screen_x: int | None = None,
    screen_y: int | None = None,
) -> tuple[int, int, dict[str, Any]]:
    """Return PostMessage-ready client coordinates plus coordinate metadata."""
    input_x, input_y = _int_point(x, y)
    input_space = _coordinate_space(coordinate_space)
    explicit_screen = screen_x is not None or screen_y is not None

    if input_space in _SCREEN_COORDINATE_SPACES or explicit_screen:
        sx, sy = _int_point(
            input_x if screen_x is None else screen_x,
            input_y if screen_y is None else screen_y,
        )
        client_x, client_y = screen_to_client(hwnd, sx, sy)
        return client_x, client_y, {
            "input_space": "screen",
            "screen": {"x": sx, "y": sy},
            "client": {"x": client_x, "y": client_y},
        }

    return input_x, input_y, {
        "input_space": input_space,
        "client": {"x": input_x, "y": input_y},
    }


def resolve_screen_point(
    hwnd: int,
    x: int,
    y: int,
    *,
    coordinate_space: str | None = "client",
    screen_x: int | None = None,
    screen_y: int | None = None,
) -> tuple[int, int, dict[str, Any]]:
    """Return screen coordinates for messages such as WM_MOUSEWHEEL."""
    client_x, client_y, metadata = resolve_client_point(
        hwnd,
        x,
        y,
        coordinate_space=coordinate_space,
        screen_x=screen_x,
        screen_y=screen_y,
    )
    if metadata["input_space"] == "screen":
        screen = metadata["screen"]
        return int(screen["x"]), int(screen["y"]), metadata

    sx, sy = client_to_screen(hwnd, client_x, client_y)
    metadata = {**metadata, "screen": {"x": sx, "y": sy}}
    return sx, sy, metadata


def _post(hwnd: int, message: int, wparam: int = 0, lparam: int = 0) -> bool:
    if not _user32 or not can_post_to_hwnd(hwnd):
        return False
    try:
        return bool(
            _user32.PostMessageW(
                wintypes.HWND(int(hwnd)),
                wintypes.UINT(message),
                wintypes.WPARAM(wparam),
                wintypes.LPARAM(lparam),
            )
        )
    except Exception:
        return False


def post_click(
    hwnd: int,
    x: int,
    y: int,
    button: str = "left",
    *,
    coordinate_space: str | None = "client",
    screen_x: int | None = None,
    screen_y: int | None = None,
) -> bool:
    """Send button down/up messages in client coordinates."""
    button = button.lower()
    down_up = {
        "left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON),
        "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON),
        "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON),
    }.get(button)
    if down_up is None:
        return False
    down, up, flag = down_up
    client_x, client_y, _metadata = resolve_client_point(
        hwnd,
        x,
        y,
        coordinate_space=coordinate_space,
        screen_x=screen_x,
        screen_y=screen_y,
    )
    lparam = make_lparam(client_x, client_y)
    return _post(hwnd, down, flag, lparam) and _post(hwnd, up, 0, lparam)


def post_text(hwnd: int, text: str) -> bool:
    """Send each character as ``WM_CHAR``."""
    if not text:
        return True
    ok = True
    for char in text:
        ok = _post(hwnd, WM_CHAR, ord(char), 0) and ok
    return ok


def virtual_key(key: str) -> int | None:
    normalized = key.strip().lower()
    if not normalized:
        return None
    if len(normalized) == 1:
        return ord(normalized.upper())
    if normalized.startswith("f") and normalized[1:].isdigit():
        number = int(normalized[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    return VK_CODES.get(normalized)


def post_key(hwnd: int, key_combo: str) -> bool:
    """Send a simple key or modifier+key combo via key down/up messages."""
    parts = [part.strip() for part in key_combo.replace("+", " ").split() if part.strip()]
    if not parts:
        return False
    keys = [virtual_key(part) for part in parts]
    if any(key is None for key in keys):
        return False
    vk_codes = [int(key) for key in keys if key is not None]
    ok = True
    for vk in vk_codes:
        ok = _post(hwnd, WM_KEYDOWN, vk, 0) and ok
    for vk in reversed(vk_codes):
        ok = _post(hwnd, WM_KEYUP, vk, 0) and ok
    return ok


def post_scroll(
    hwnd: int,
    x: int,
    y: int,
    direction: str = "down",
    clicks: int = 3,
    *,
    coordinate_space: str | None = "client",
    screen_x: int | None = None,
    screen_y: int | None = None,
) -> bool:
    """Send a ``WM_MOUSEWHEEL`` message."""
    if clicks <= 0:
        return False
    sign = 1 if direction.lower() in {"up", "left"} else -1
    resolved_screen_x, resolved_screen_y, _metadata = resolve_screen_point(
        hwnd,
        x,
        y,
        coordinate_space=coordinate_space,
        screen_x=screen_x,
        screen_y=screen_y,
    )
    wparam = ((sign * WHEEL_DELTA * int(clicks)) & 0xFFFF) << 16
    return _post(hwnd, WM_MOUSEWHEEL, wparam, make_lparam(resolved_screen_x, resolved_screen_y))
