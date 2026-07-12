"""Coordinate helpers for Win32 window messages."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_IS_WINDOWS = sys.platform == "win32"
_user32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WINDOWS else None


def make_lparam(x: int, y: int) -> int:
    """Pack signed 16-bit x/y coordinates into a Win32 LPARAM."""
    return (int(y) & 0xFFFF) << 16 | (int(x) & 0xFFFF)


def unpack_lparam(lparam: int) -> tuple[int, int]:
    """Unpack signed 16-bit x/y coordinates from a Win32 LPARAM."""
    x = int(lparam) & 0xFFFF
    y = (int(lparam) >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    return x, y


def get_window_rect(hwnd: int) -> dict[str, int]:
    """Return screen-coordinate bounds for a window."""
    if not _user32 or not hwnd:
        return {}
    rect = wintypes.RECT()
    try:
        if not _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return {}
    except Exception:
        return {}
    return {
        "x": int(rect.left),
        "y": int(rect.top),
        "width": max(0, int(rect.right - rect.left)),
        "height": max(0, int(rect.bottom - rect.top)),
    }


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert a screen point to client coordinates, returning input on failure."""
    if not _user32 or not hwnd:
        return int(x), int(y)
    point = wintypes.POINT(int(x), int(y))
    try:
        if not _user32.ScreenToClient(wintypes.HWND(hwnd), ctypes.byref(point)):
            return int(x), int(y)
    except Exception:
        return int(x), int(y)
    return int(point.x), int(point.y)

def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert a client point to screen coordinates, returning input on failure."""
    if not _user32 or not hwnd:
        return int(x), int(y)
    point = wintypes.POINT(int(x), int(y))
    try:
        if not _user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(point)):
            return int(x), int(y)
    except Exception:
        return int(x), int(y)
    return int(point.x), int(point.y)
