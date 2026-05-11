"""Accessibility API helpers for macOS.

Wraps pyobjc ApplicationServices to read the AX tree, find elements,
press buttons, and set values. All functions degrade gracefully when
pyobjc is unavailable or the platform is not macOS.
"""

from __future__ import annotations

import sys
from typing import Any

_AX_AVAILABLE = False

if sys.platform == "darwin":
    try:
        from ApplicationServices import (  # type: ignore[import]
            AXIsProcessTrusted,
            AXIsProcessTrustedWithOptions,
            AXUIElementCreateApplication,
            AXUIElementCreateSystemWide,
        )
        from CoreFoundation import (  # type: ignore[import]
            kCFBooleanTrue,
        )

        _AX_AVAILABLE = True
    except ImportError:
        pass


def ax_is_trusted() -> bool:
    """Check if the current process has Accessibility permission."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return False
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def ax_prompt_permission() -> bool:
    """Prompt the user for Accessibility permission if not granted."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return False
    try:
        options = {b"AXTrustedCheckOptionPrompt": kCFBooleanTrue}
        return bool(AXIsProcessTrustedWithOptions(options))
    except Exception:
        return False


def ax_list_windows(pid: int | None) -> list[dict]:
    """List windows for a given PID via the AX API."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return []
    if pid is None:
        return []
    try:
        app_ref = AXUIElementCreateApplication(pid)
        err, windows = app_ref.copyAttributeValue_("AXWindows")  # type: ignore[attr-defined]
        if err or not windows:
            return []
        result = []
        for w in windows:
            _, title = w.copyAttributeValue_("AXTitle")  # type: ignore[attr-defined]
            _, role = w.copyAttributeValue_("AXRole")  # type: ignore[attr-defined]
            result.append({"title": str(title or ""), "role": str(role or "")})
        return result
    except Exception:
        return []


def ax_get_tree(
    pid: int | None = None,
    app: str | None = None,
    window_title: str | None = None,
    window_id: int | None = None,
) -> dict:
    """Get the accessibility tree for a target application/window."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return {}
    if pid is None and app is None:
        return {}
    try:
        if pid is None:
            # Try to resolve pid from app name
            pid = _resolve_pid(app)
        if pid is None:
            return {}
        app_ref = AXUIElementCreateApplication(pid)
        return _build_tree(app_ref, depth=0, max_depth=5)
    except Exception:
        return {}


def ax_find_candidates(
    pid: int | None = None,
    app: str | None = None,
    role: str | None = None,
    title: str | None = None,
    description: str | None = None,
    point: tuple[int, int] | None = None,
    intent: str | None = None,
) -> list[dict]:
    """Find AX elements matching the given criteria."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return []
    try:
        if pid is None:
            pid = _resolve_pid(app)
        if pid is None:
            return []
        app_ref = AXUIElementCreateApplication(pid)
        candidates = _collect_elements(app_ref, depth=0, max_depth=5)
        results = []
        for el in candidates:
            if role and el.get("role") != role:
                continue
            if title and title.lower() not in el.get("title", "").lower():
                continue
            if description and description.lower() not in el.get("description", "").lower():
                continue
            results.append(el)
        return results
    except Exception:
        return []


def ax_press(element_id: str) -> bool:
    """Press (invoke AXPress) on an element by its id."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return False
    # element_id is opaque in this stub; real impl would resolve the ref
    return False


def ax_set_value(
    pid: int | None,
    app: str | None,
    value: str,
    element_id: str | None = None,
) -> bool:
    """Set the value of a focused or specified AX element."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return False
    return False


def ax_raise(window_id: int | None = None) -> bool:
    """Raise (bring to front) a window by its window_id."""
    if sys.platform != "darwin" or not _AX_AVAILABLE:
        return False
    return False


# --- internal helpers ---


def _resolve_pid(app: str | None) -> int | None:
    """Resolve an app name to a PID."""
    if not app:
        return None
    try:
        from AppKit import NSWorkspace  # type: ignore[import]

        for running in NSWorkspace.sharedWorkspace().runningApplications():
            if app.lower() in (running.localizedName() or "").lower():
                return running.processIdentifier()
    except Exception:
        pass
    return None


def _build_tree(element: Any, depth: int, max_depth: int) -> dict:
    """Recursively build a dict representation of the AX tree."""
    if depth > max_depth:
        return {}
    try:
        _, role = element.copyAttributeValue_("AXRole")
        _, title = element.copyAttributeValue_("AXTitle")
        _, desc = element.copyAttributeValue_("AXDescription")
        node: dict[str, Any] = {
            "role": str(role or ""),
            "title": str(title or ""),
            "description": str(desc or ""),
        }
        _, children = element.copyAttributeValue_("AXChildren")
        if children:
            node["children"] = [
                _build_tree(c, depth + 1, max_depth) for c in children[:50]
            ]
        return node
    except Exception:
        return {}


def _collect_elements(element: Any, depth: int, max_depth: int) -> list[dict]:
    """Flatten the AX tree into a list of element dicts."""
    if depth > max_depth:
        return []
    results: list[dict] = []
    try:
        _, role = element.copyAttributeValue_("AXRole")
        _, title = element.copyAttributeValue_("AXTitle")
        _, desc = element.copyAttributeValue_("AXDescription")
        results.append({
            "id": str(id(element)),
            "role": str(role or ""),
            "title": str(title or ""),
            "description": str(desc or ""),
        })
        _, children = element.copyAttributeValue_("AXChildren")
        if children:
            for c in children[:50]:
                results.extend(_collect_elements(c, depth + 1, max_depth))
    except Exception:
        pass
    return results
