"""Windows integrity and native availability probes."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

_IS_WINDOWS = sys.platform == "win32"
_user32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WINDOWS else None
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if _IS_WINDOWS else None
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True) if _IS_WINDOWS else None

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_INTEGRITY_LEVEL = 25
_SECURITY_MANDATORY_LOW_RID = 0x1000
_SECURITY_MANDATORY_MEDIUM_RID = 0x2000
_SECURITY_MANDATORY_HIGH_RID = 0x3000
_SECURITY_MANDATORY_SYSTEM_RID = 0x4000


def is_windows() -> bool:
    return _IS_WINDOWS


def has_user32() -> bool:
    return _user32 is not None


def current_process_id() -> int | None:
    if not _kernel32:
        return None


def get_process_integrity_level(pid: int | None) -> str:
    """Return low/medium/high/system for a process, or unknown."""
    if not _kernel32 or not _advapi32 or not pid:
        return "unknown"
    process = token = None
    try:
        process = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(int(pid)))
        if not process:
            return "unknown"
        token_handle = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token_handle)):
            return "unknown"
        token = token_handle
        needed = wintypes.DWORD(0)
        _advapi32.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(needed))
        if needed.value <= 0:
            return "unknown"
        buffer = ctypes.create_string_buffer(needed.value)
        if not _advapi32.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, buffer, needed, ctypes.byref(needed)):
            return "unknown"

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

        sid_and_attrs = ctypes.cast(buffer, ctypes.POINTER(SID_AND_ATTRIBUTES)).contents
        sub_auth_count = ctypes.cast(sid_and_attrs.Sid, ctypes.POINTER(ctypes.c_ubyte))[1]
        get_sub_auth = _advapi32.GetSidSubAuthority
        get_sub_auth.restype = ctypes.POINTER(wintypes.DWORD)
        rid = int(get_sub_auth(sid_and_attrs.Sid, sub_auth_count - 1).contents.value)
        if rid >= _SECURITY_MANDATORY_SYSTEM_RID:
            return "system"
        if rid >= _SECURITY_MANDATORY_HIGH_RID:
            return "high"
        if rid >= _SECURITY_MANDATORY_MEDIUM_RID:
            return "medium"
        if rid >= _SECURITY_MANDATORY_LOW_RID:
            return "low"
        return "unknown"
    except Exception:
        return "unknown"
    finally:
        for handle in (token, process):
            if handle:
                try:
                    _kernel32.CloseHandle(handle)
                except Exception:
                    pass
    try:
        return int(_kernel32.GetCurrentProcessId())
    except Exception:
        return None


def can_post_to_hwnd(hwnd: int | None) -> bool:
    """Return whether basic user32 message APIs can target this HWND."""
    if not _user32 or not hwnd:
        return False
    try:
        return bool(_user32.IsWindow(wintypes.HWND(int(hwnd))))
    except Exception:
        return False


def describe_environment() -> dict[str, Any]:
    """Return a compact native capability summary for diagnostics."""
    return {
        "platform": sys.platform,
        "is_windows": _IS_WINDOWS,
        "user32": _user32 is not None,
        "current_process_id": current_process_id(),
        "current_integrity_level": get_process_integrity_level(current_process_id()),
    }
