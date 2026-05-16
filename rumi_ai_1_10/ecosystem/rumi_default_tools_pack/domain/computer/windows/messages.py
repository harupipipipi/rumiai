"""Win32 PostMessage helpers for background-ish input attempts."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

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
WM_MOUSEHWHEEL = 0x020E

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002
MK_MBUTTON = 0x0010
WHEEL_DELTA = 120

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


def post_click(hwnd: int, x: int, y: int, button: str = "left") -> bool:
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
    lparam = make_lparam(x, y)
    return _post(hwnd, down, flag, lparam) and _post(hwnd, up, 0, lparam)


def post_text(hwnd: int, text: str) -> bool:
    """Send each character as ``WM_CHAR``."""
    if not text:
        return False
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


def post_scroll(hwnd: int, x: int, y: int, direction: str = "down", clicks: int = 3) -> bool:
    """Send a mouse wheel message."""
    if clicks <= 0:
        return False
    normalized = direction.lower()
    if normalized in {"up", "down"}:
        message = WM_MOUSEWHEEL
        sign = 1 if normalized == "up" else -1
    elif normalized in {"left", "right"}:
        message = WM_MOUSEHWHEEL
        sign = 1 if normalized == "right" else -1
    else:
        return False
    screen_x, screen_y = client_to_screen(hwnd, x, y)
    wparam = ((sign * WHEEL_DELTA * int(clicks)) & 0xFFFF) << 16
    return _post(hwnd, message, wparam, make_lparam(screen_x, screen_y))
