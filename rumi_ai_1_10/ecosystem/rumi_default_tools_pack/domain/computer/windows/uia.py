"""Windows UI Automation API stubs.

These functions will wrap the Windows UIA COM interface when implemented.
On non-Windows platforms they return empty/False immediately.
"""

from __future__ import annotations

import sys


def uia_get_tree(hwnd: int) -> dict:
    """Get the UIA element tree for a window handle."""
    if sys.platform != "win32":
        return {}
    return {}


def uia_invoke(element_id: str) -> bool:
    """Invoke a UIA element's default action."""
    if sys.platform != "win32":
        return False
    return False


def uia_set_value(element_id: str, value: str) -> bool:
    """Set the value of a UIA element."""
    if sys.platform != "win32":
        return False
    return False
