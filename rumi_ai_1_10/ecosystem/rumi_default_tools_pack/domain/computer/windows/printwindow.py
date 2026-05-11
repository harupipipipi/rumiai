"""Windows PrintWindow capture stub.

Captures a window via the Win32 PrintWindow API.
On non-Windows platforms, returns unavailable.
"""

from __future__ import annotations

import sys


def capture_window_via_printwindow(hwnd: int) -> dict:
    """Capture a window screenshot via PrintWindow API."""
    if sys.platform != "win32":
        return {
            "path": "",
            "data_url": "",
            "coordinate_system": "window_pixels",
            "method": "unavailable",
            "error": "Not Windows",
        }
    return {
        "path": "",
        "data_url": "",
        "coordinate_system": "window_pixels",
        "method": "unavailable",
        "error": "PrintWindow not yet implemented",
    }
