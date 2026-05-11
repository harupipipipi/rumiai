"""CGEvent helpers for macOS.

Wraps pyobjc Quartz to post mouse/keyboard events directly to a PID
via CGEventPostToPid. Degrades gracefully when pyobjc is unavailable.
"""

from __future__ import annotations

import sys

_CG_AVAILABLE = False

if sys.platform == "darwin":
    try:
        from Quartz import (  # type: ignore[import]
            CGEventCreateMouseEvent,
            CGEventCreateKeyboardEvent,
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            CGEventPostToPid,
            CGEventSetIntegerValueField,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGEventScrollWheel,
            kCGHIDEventTap,
            kCGScrollEventUnitLine,
        )

        _CG_AVAILABLE = True
    except ImportError:
        pass


def post_click_to_pid(pid: int, x: int, y: int, button: str = "left") -> bool:
    """Post a click event to a specific PID."""
    if sys.platform != "darwin" or not _CG_AVAILABLE:
        return False
    try:
        point = (float(x), float(y))
        if button == "right":
            down_type = kCGEventRightMouseDown
            up_type = kCGEventRightMouseUp
        else:
            down_type = kCGEventLeftMouseDown
            up_type = kCGEventLeftMouseUp

        down_event = CGEventCreateMouseEvent(None, down_type, point, 0)
        up_event = CGEventCreateMouseEvent(None, up_type, point, 0)
        CGEventPostToPid(pid, down_event)
        CGEventPostToPid(pid, up_event)
        return True
    except Exception:
        return False


def post_key_to_pid(pid: int, text: str = "", key_combo: str = "") -> bool:
    """Post keyboard events to a specific PID."""
    if sys.platform != "darwin" or not _CG_AVAILABLE:
        return False
    try:
        if text:
            for ch in text:
                down = CGEventCreateKeyboardEvent(None, 0, True)
                up = CGEventCreateKeyboardEvent(None, 0, False)
                from Quartz import CGEventKeyboardSetUnicodeString  # type: ignore[import]

                CGEventKeyboardSetUnicodeString(down, len(ch), ch)
                CGEventKeyboardSetUnicodeString(up, len(ch), ch)
                CGEventPostToPid(pid, down)
                CGEventPostToPid(pid, up)
            return True
        if key_combo:
            # Simplified: post a single keydown/keyup for the combo
            down = CGEventCreateKeyboardEvent(None, 0, True)
            up = CGEventCreateKeyboardEvent(None, 0, False)
            CGEventPostToPid(pid, down)
            CGEventPostToPid(pid, up)
            return True
        return False
    except Exception:
        return False


def post_scroll_to_pid(
    pid: int, x: int, y: int, direction: str, clicks: int
) -> bool:
    """Post a scroll event to a specific PID."""
    if sys.platform != "darwin" or not _CG_AVAILABLE:
        return False
    try:
        dy = -clicks if direction == "down" else clicks if direction == "up" else 0
        dx = -clicks if direction == "right" else clicks if direction == "left" else 0
        event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 2, dy, dx)
        CGEventPostToPid(pid, event)
        return True
    except Exception:
        return False


def cgevent_smoke_test() -> dict:
    """Check if CGEvent APIs are available."""
    notes: list[str] = []
    if sys.platform != "darwin":
        notes.append("Not macOS")
        return {"available": False, "notes": notes}
    if not _CG_AVAILABLE:
        notes.append("pyobjc Quartz not importable")
        return {"available": False, "notes": notes}
    notes.append("CGEvent APIs available")
    return {"available": True, "notes": notes}
