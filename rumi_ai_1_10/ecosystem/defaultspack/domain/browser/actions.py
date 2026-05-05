from __future__ import annotations

from typing import Any


_BROWSER_ACTIONS = {
    "profile_list": "browser.profile.list",
    "profiles": "browser.profile.list",
    "profile_get": "browser.profile.get",
    "profile_create": "browser.profile.create",
    "profile_update": "browser.profile.update",
    "profile_delete": "browser.profile.delete",
    "profile_set_active": "browser.profile.set_active",
    "start": "browser.session.start",
    "stop": "browser.session.stop",
    "restart": "browser.session.restart",
    "health": "browser.session.health",
    "session": "browser.session.health",
    "sessions": "browser.session.list",
    "list_sessions": "browser.session.list",
    "tabs": "browser.tab.list",
    "tab_list": "browser.tab.list",
    "list_tabs": "browser.tab.list",
    "open": "browser.tab.open",
    "open_url": "browser.tab.open",
    "open_tab": "browser.tab.open",
    "focus": "browser.tab.focus",
    "focus_tab": "browser.tab.focus",
    "close": "browser.tab.close",
    "close_tab": "browser.tab.close",
    "navigate": "browser.tab.navigate",
    "snapshot": "browser.tab.snapshot",
    "screenshot": "browser.tab.screenshot",
    "click_ref": "browser.ref.click",
    "type_ref": "browser.ref.type",
    "key_ref": "browser.ref.key",
    "scroll_ref": "browser.ref.scroll",
}

_DESKTOP_ACTIONS = {
    "move": "computer.move",
    "cursor_move": "computer.move",
    "mouse_move": "computer.move",
    "click": "computer.click",
    "type": "computer.type",
    "key": "computer.key",
    "scroll": "computer.scroll",
}

_INLINE_KEYS = {
    "url",
    "profile_id",
    "session_id",
    "tab_id",
    "ref",
    "ref_id",
    "x",
    "y",
    "text",
    "key",
    "amount",
    "dry_run",
    "approval_token",
}


def map_browser_use_action(arguments: dict[str, Any] | None) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    payload = dict(arguments.get("payload") or {})
    for key in _INLINE_KEYS:
        if key in arguments:
            payload[key] = arguments.get(key)
    raw_action = str(arguments.get("action") or "session").strip()
    action_key = raw_action.lower()
    if action_key in _DESKTOP_ACTIONS and (payload.get("ref") or payload.get("ref_id")):
        canonical = "browser.ref.{}".format(_DESKTOP_ACTIONS[action_key].split(".", 1)[1])
    elif action_key in _BROWSER_ACTIONS:
        canonical = _BROWSER_ACTIONS[action_key]
    else:
        canonical = _DESKTOP_ACTIONS.get(action_key, raw_action)
    if canonical == "browser.tab.open" and "url" not in payload and arguments.get("url"):
        payload["url"] = arguments.get("url")
    return {
        "tool": "browser_use",
        "legacy_action": raw_action,
        "action": canonical,
        "payload": payload,
        "requires_browser_v2": canonical.startswith("browser."),
        "requires_computer_use": canonical.startswith("computer."),
    }


def map_computer_use_action(arguments: dict[str, Any] | None) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    payload = dict(arguments.get("payload") or {})
    for key in ("x", "y", "text", "key", "amount", "dry_run", "approval_token"):
        if key in arguments:
            payload[key] = arguments.get(key)
    raw_action = str(arguments.get("action") or "screenshot").strip()
    canonical = {
        "": "computer.screenshot",
        "screenshot": "computer.screenshot",
        **_DESKTOP_ACTIONS,
    }.get(raw_action.lower(), raw_action)
    return {
        "tool": "computer_use",
        "legacy_action": raw_action,
        "action": canonical,
        "payload": payload,
        "requires_computer_use": canonical.startswith("computer."),
    }
