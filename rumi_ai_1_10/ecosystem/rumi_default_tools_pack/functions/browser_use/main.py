from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions.browser_computer.main import run as _run_browser_computer


def run(context, args):
    raw = dict(args or {})
    payload = dict(raw.get("payload") or {})
    action_map = {
        "": "browser.session",
        "session": "browser.session",
        "open_url": "browser.open_url",
        "open": "browser.open_url",
        "screenshot": "computer.screenshot",
        "move": "computer.move",
        "cursor_move": "computer.move",
        "mouse_move": "computer.move",
        "click": "computer.click",
        "context": "computer.context",
        "app_context": "computer.context",
        "state": "computer.context",
        "apps": "computer.apps",
        "applications": "computer.apps",
        "open_apps": "computer.apps",
        "list_apps": "computer.apps",
        "select_app": "computer.select_app",
        "app": "computer.select_app",
        "show_app": "computer.show_app",
        "focus_app": "computer.show_app",
        "activate_app": "computer.show_app",
        "main_app": "computer.show_app",
        "show": "computer.show_app",
        "select_window": "computer.select_window",
        "window": "computer.select_window",
        "windows": "computer.windows",
        "list_windows": "computer.windows",
        "type": "computer.type",
        "key": "computer.key",
        "scroll": "computer.scroll",
    }
    action = action_map.get(str(raw.get("action") or "").strip(), str(raw.get("action") or "").strip())
    for key in (
        "url",
        "url_contains",
        "x",
        "y",
        "text",
        "key",
        "modifier",
        "modifiers",
        "amount",
        "target",
        "scope",
        "app",
        "application",
        "name",
        "title",
        "title_contains",
        "window",
        "window_index",
        "tab_index",
        "button",
        "include_screenshot",
        "coordinate_space",
        "physical",
        "focus",
        "open",
        "launch",
        "limit",
        "include_installed",
        "include_installed_apps",
        "mode",
        "method",
        "driver",
        "dry_run",
        "approval_token",
    ):
        if key in raw:
            payload[key] = raw.get(key)
    return _run_browser_computer(context, {"action": action, "payload": payload})
