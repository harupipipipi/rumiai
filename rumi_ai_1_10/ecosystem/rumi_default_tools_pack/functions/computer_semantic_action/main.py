from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import RUMI_ROOT  # noqa: F401 - imported for sys.path setup

try:
    from ecosystem.defaultspack.domain.host_bridge.computer_router import run_computer_action
except ImportError:  # pragma: no cover - direct function execution fallback
    from domain.host_bridge.computer_router import run_computer_action


def run(context, args):
    """Run semantic desktop actions through the approval-aware computer router."""
    a = args or {}
    payload = {
        "app": a.get("app"),
        "pid": a.get("pid"),
        "window_id": a.get("window_id"),
        "intent": a.get("intent", ""),
    }
    if a.get("element_id"):
        payload["element_id"] = a["element_id"]
    elif a.get("point"):
        payload["point"] = a["point"]
    if a.get("approval_token"):
        payload["approval_token"] = a["approval_token"]

    return run_computer_action(
        "computer.semantic_action",
        payload,
        context if isinstance(context, dict) else None,
        tool_name="computer_semantic_action",
        tool_arguments=dict(a),
        yolo_mode=_truthy(context.get("yolo_mode")) if isinstance(context, dict) else False,
    )


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
