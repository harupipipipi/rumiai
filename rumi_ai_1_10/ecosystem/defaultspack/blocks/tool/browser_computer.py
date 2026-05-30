import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.host_bridge.computer_router import run_computer_action


def run(input_data, context=None):
    action = input_data.get("action")
    if not action:
        return error("'action' is required", code="INVALID_INPUT")
    try:
        yolo_mode = _truthy(context.get("yolo_mode")) if isinstance(context, dict) else False
        result = run_computer_action(
            str(action),
            dict(input_data.get("payload") or {}),
            context if isinstance(context, dict) else None,
            tool_name="browser_computer",
            artifact_root=_artifact_root(context),
            yolo_mode=yolo_mode,
        )
    except Exception as exc:
        return error(str(exc), code="BROWSER_COMPUTER_FAILED")
    return ok(result)


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _artifact_root(context):
    if not isinstance(context, dict):
        return None
    workspace = context.get("conversation_workspace_dir")
    if not isinstance(workspace, str) or not workspace:
        return None
    return Path(workspace) / "tools" / "computer"
