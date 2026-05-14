"""Safe Windows HWND helpers for ComputerSeat.

The functions in this module intentionally return empty/``None`` results on
non-Windows hosts or when a Win32 call fails. They are used by drivers that
should degrade into ``ActionResult(executed=False)`` instead of raising.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
import sys
from ctypes import wintypes
from typing import Any

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
else:
    _user32 = None
    _kernel32 = None

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_VM_READ = 0x0010


def _safe_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number else None


def _window_title(hwnd: int) -> str:
    if not _user32:
        return ""
    try:
        length = int(_user32.GetWindowTextLengthW(wintypes.HWND(hwnd)))
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
        return buffer.value
    except Exception:
        return ""


def _window_rect(hwnd: int) -> dict[str, int]:
    if not _user32:
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


def _window_pid(hwnd: int) -> int | None:
    if not _user32:
        return None
    pid = wintypes.DWORD()
    try:
        _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    except Exception:
        return None
    return int(pid.value) if pid.value else None


def _process_name(pid: int | None) -> str:
    if not pid or not _kernel32:
        return ""
    handle = None
    try:
        handle = _kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_VM_READ,
            False,
            wintypes.DWORD(pid),
        )
        if not handle:
            return ""
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        query = getattr(_kernel32, "QueryFullProcessImageNameW", None)
        if not query or not query(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return Path(buffer.value).stem
    except Exception:
        return ""
    finally:
        if handle:
            try:
                _kernel32.CloseHandle(handle)
            except Exception:
                pass


def get_window_info(hwnd: int) -> dict[str, Any] | None:
    """Return a normalized visible-window record for ``hwnd``."""
    if not _user32 or not hwnd:
        return None
    try:
        if not _user32.IsWindow(wintypes.HWND(hwnd)):
            return None
        if not _user32.IsWindowVisible(wintypes.HWND(hwnd)):
            return None
    except Exception:
        return None

    title = _window_title(hwnd)
    if not title:
        return None
    pid = _window_pid(hwnd)
    rect = _window_rect(hwnd)
    return {
        "hwnd": int(hwnd),
        "window_id": int(hwnd),
        "title": title,
        "pid": pid,
        "app": _process_name(pid),
        **rect,
    }


def list_windows() -> list[dict]:
    """List all visible windows with their HWNDs."""
    if not _user32:
        return []
    windows: list[dict] = []

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _collect(hwnd: int, _lparam: int) -> bool:
        info = get_window_info(int(hwnd))
        if info:
            windows.append(info)
        return True

    try:
        _user32.EnumWindows(enum_proc_type(_collect), 0)
    except Exception:
        return []
    return windows


def find_hwnd_by_title(title: str) -> int | None:
    """Find a window handle by its title."""
    if not title:
        return None
    needle = title.casefold()
    for window in list_windows():
        window_title = str(window.get("title") or "")
        if needle in window_title.casefold():
            return _safe_int(window.get("hwnd"))
    return None


def find_hwnd_by_pid(pid: int) -> list[int]:
    """Find all window handles belonging to a PID."""
    pid_int = _safe_int(pid)
    if pid_int is None:
        return []
    handles: list[int] = []
    for window in list_windows():
        if _safe_int(window.get("pid")) != pid_int:
            continue
        hwnd = _safe_int(window.get("hwnd"))
        if hwnd is not None:
            handles.append(hwnd)
    return handles


def resolve_hwnd(
    *,
    hwnd: int | None = None,
    window_id: int | None = None,
    pid: int | None = None,
    title: str | None = None,
) -> int | None:
    """Resolve a ComputerTarget-like set of fields to a HWND."""
    for candidate in (hwnd, window_id):
        value = _safe_int(candidate)
        if value and get_window_info(value):
            return value
    if pid:
        handles = find_hwnd_by_pid(pid)
        if handles:
            return handles[0]
    if title:
        return find_hwnd_by_title(title)
    return None
