"""Optional Windows UI Automation helpers.

The implementation prefers ``pywinauto`` when it is installed. The dependency
is optional; callers receive empty trees or ``False`` when UIA is unavailable.
"""

from __future__ import annotations

import sys
from typing import Any

_ELEMENTS: dict[str, Any] = {}


def _pywinauto_modules() -> tuple[Any, Any] | tuple[None, None]:
    if sys.platform != "win32":
        return None, None
    try:
        from pywinauto import Desktop  # type: ignore
        from pywinauto.controls.uiawrapper import UIAWrapper  # type: ignore
    except Exception:
        return None, None
    return Desktop, UIAWrapper


def is_uia_available() -> bool:
    desktop, _wrapper = _pywinauto_modules()
    return desktop is not None


def _element_record(element: Any, element_id: str) -> dict[str, Any]:
    try:
        rect = element.rectangle()
        frame = {
            "x": int(rect.left),
            "y": int(rect.top),
            "width": max(0, int(rect.right - rect.left)),
            "height": max(0, int(rect.bottom - rect.top)),
        }
    except Exception:
        frame = {}
    try:
        role = str(element.friendly_class_name())
    except Exception:
        role = ""
    try:
        title = str(element.window_text())
    except Exception:
        title = ""
    try:
        enabled = bool(element.is_enabled())
    except Exception:
        enabled = True
    return {
        "id": element_id,
        "role": role,
        "title": title,
        "enabled": enabled,
        "frame": frame,
        "actions": _supported_actions(element),
    }


def _supported_actions(element: Any) -> list[str]:
    actions: list[str] = []
    for name, action in (
        ("invoke", "invoke"),
        ("set_value", "set_edit_text"),
        ("scroll", "scroll"),
    ):
        if hasattr(element, name):
            actions.append(action)
    return actions


def _walk(element: Any, prefix: str, depth: int, max_depth: int) -> dict[str, Any]:
    element_id = prefix
    _ELEMENTS[element_id] = element
    record = _element_record(element, element_id)
    if depth >= max_depth:
        return record
    children: list[dict[str, Any]] = []
    try:
        child_elements = element.children()
    except Exception:
        child_elements = []
    for index, child in enumerate(child_elements[:80]):
        children.append(_walk(child, f"{prefix}.{index}", depth + 1, max_depth))
    if children:
        record["children"] = children
    return record


def uia_get_tree(hwnd: int, *, max_depth: int = 3) -> dict:
    """Get the UIA element tree for a window handle."""
    if sys.platform != "win32":
        return {}
    desktop, _wrapper = _pywinauto_modules()
    if desktop is None or not hwnd:
        return {}
    try:
        window = desktop(backend="uia").window(handle=int(hwnd))
        _ELEMENTS.clear()
        return _walk(window.wrapper_object(), "root", 0, max_depth)
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _flatten(node: dict[str, Any]) -> list[dict[str, Any]]:
    items = [node] if node else []
    for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
        if isinstance(child, dict):
            items.extend(_flatten(child))
    return items


def _contains(frame: dict[str, Any], point: tuple[int, int]) -> bool:
    try:
        x = float(frame.get("x", 0))
        y = float(frame.get("y", 0))
        width = float(frame.get("width", 0))
        height = float(frame.get("height", 0))
        px, py = point
        return x <= px <= x + width and y <= py <= y + height
    except Exception:
        return False


def uia_find_candidates(
    hwnd: int,
    *,
    point: tuple[int, int] | None = None,
    role: str | None = None,
    title: str | None = None,
    intent: str | None = None,
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """Find cached UIA element records by point or simple text intent."""
    tree = uia_get_tree(hwnd, max_depth=max_depth)
    candidates: list[dict[str, Any]] = []
    intent_tokens = {part for part in (intent or "").casefold().split() if len(part) > 1}
    for element in _flatten(tree):
        if role and role.casefold() not in str(element.get("role") or "").casefold():
            continue
        haystack = " ".join(str(element.get(key) or "") for key in ("title", "role", "id")).casefold()
        if title and title.casefold() not in haystack:
            continue
        if point is not None and not _contains(element.get("frame") or {}, point):
            continue
        score = 0.0
        if point is not None:
            score += 10.0
        if intent_tokens:
            matches = sum(1 for token in intent_tokens if token in haystack)
            if matches == 0:
                continue
            score += float(matches)
        if "invoke" in element.get("actions", []):
            score += 2.0
        item = dict(element)
        item["score"] = score
        candidates.append(item)
    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    return candidates


def uia_invoke(element_id: str) -> bool:
    """Invoke a UIA element's default action."""
    if sys.platform != "win32":
        return False
    element = _ELEMENTS.get(element_id)
    if element is None:
        return False
    for method_name in ("invoke", "click_input"):
        method = getattr(element, method_name, None)
        if not method:
            continue
        try:
            method()
            return True
        except Exception:
            continue
    return False


def uia_set_value(element_id: str, value: str) -> bool:
    """Set the value of a UIA element."""
    if sys.platform != "win32":
        return False
    element = _ELEMENTS.get(element_id)
    if element is None:
        return False
    for method_name in ("set_edit_text", "set_text"):
        method = getattr(element, method_name, None)
        if not method:
            continue
        try:
            method(value)
            return True
        except Exception:
            continue
    return False


def uia_scroll(element_id: str, direction: str = "down", amount: int = 3) -> bool:
    """Scroll a UIA element if the wrapper exposes a scroll method."""
    if sys.platform != "win32":
        return False
    element = _ELEMENTS.get(element_id)
    if element is None:
        return False
    method = getattr(element, "scroll", None)
    if not method:
        return False
    try:
        if direction in {"up", "down"}:
            method("up" if direction == "up" else "down", amount)
        else:
            method("left" if direction == "left" else "right", amount)
        return True
    except Exception:
        return False
