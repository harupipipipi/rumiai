"""Windows HWND management stubs.

Provides window enumeration and lookup by title/PID.
On non-Windows platforms, returns empty results.
"""

from __future__ import annotations

import sys


def list_windows() -> list[dict]:
    """List all visible windows with their HWNDs."""
    if sys.platform != "win32":
        return []
    return []


def find_hwnd_by_title(title: str) -> int | None:
    """Find a window handle by its title."""
    if sys.platform != "win32":
        return None
    return None


def find_hwnd_by_pid(pid: int) -> list[int]:
    """Find all window handles belonging to a PID."""
    if sys.platform != "win32":
        return []
    return []
