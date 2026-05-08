from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions.browser_computer.main import run as _run_browser_computer


def run(context, args):
    raw = dict(args or {})
    payload = dict(raw.get("payload") or {})
    action_map = {
        "": "computer.screenshot",
        "screenshot": "computer.screenshot",
        "move": "computer.move",
        "cursor_move": "computer.move",
        "mouse_move": "computer.move",
        "click": "computer.click",
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
        "x",
        "y",
        "text",
        "key",
        "modifier",
        "modifiers",
        "amount",
        "target",
        "app",
        "title",
        "coordinate_space",
        "physical",
        "focus",
        "dry_run",
        "approval_token",
    ):
        if key in raw:
            payload[key] = raw.get(key)
    return _run_browser_computer(context, {"action": action, "payload": payload})
