"""CGEvent helpers for macOS.

Wraps pyobjc Quartz to post mouse/keyboard events directly to a PID
via CGEventPostToPid. Degrades gracefully when pyobjc is unavailable.
"""

from __future__ import annotations

import sys

_CG_AVAILABLE = False
kCGEventFlagMaskAlternate = 1 << 19
kCGEventFlagMaskCommand = 1 << 20
kCGEventFlagMaskControl = 1 << 18
kCGEventFlagMaskShift = 1 << 17

if sys.platform == "darwin":
    try:
        from Quartz import (  # type: ignore[import]
            CGEventCreateMouseEvent,
            CGEventCreateKeyboardEvent,
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            CGEventPostToPid,
            CGEventSetFlags,
            CGEventSetIntegerValueField,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGEventScrollWheel,
            kCGEventFlagMaskAlternate,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskShift,
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
            key_code, flags = _key_combo_parts(key_combo)
            if key_code is None:
                return False
            down = CGEventCreateKeyboardEvent(None, key_code, True)
            up = CGEventCreateKeyboardEvent(None, key_code, False)
            CGEventSetFlags(down, flags)
            CGEventSetFlags(up, flags)
            CGEventPostToPid(pid, down)
            CGEventPostToPid(pid, up)
            return True
        return False
    except Exception:
        return False


def _key_combo_parts(key_combo: str) -> tuple[int | None, int]:
    parts = [part.strip().lower() for part in str(key_combo or "").split("+") if part.strip()]
    if not parts:
        return None, 0
    key = parts[-1]
    modifiers = parts[:-1]
    flags = 0
    for modifier in modifiers:
        if modifier in {"cmd", "command", "meta"}:
            flags |= int(kCGEventFlagMaskCommand)
        elif modifier in {"ctrl", "control"}:
            flags |= int(kCGEventFlagMaskControl)
        elif modifier in {"alt", "option"}:
            flags |= int(kCGEventFlagMaskAlternate)
        elif modifier == "shift":
            flags |= int(kCGEventFlagMaskShift)
        else:
            return None, 0
    return _key_code(key), flags


def _key_code(key: str) -> int | None:
    codes = {
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
        "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
        "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
        "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
        "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "return": 36,
        "enter": 36, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
        ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49,
        "`": 50, "delete": 51, "backspace": 51, "escape": 53, "esc": 53,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
        "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
        "f11": 103, "f12": 111, "f13": 105, "f14": 107, "f15": 113,
        "f16": 106, "f17": 64, "f18": 79, "f19": 80, "f20": 90,
    }
    if key in codes:
        return codes[key]
    return None


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
