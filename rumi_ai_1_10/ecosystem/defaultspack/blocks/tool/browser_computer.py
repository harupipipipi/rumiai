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
    tool_name = str(input_data.get("tool_name") or "browser_computer")
    permission_denial = _settings_permission_denial(tool_name, input_data, context)
    if permission_denial is not None:
        return permission_denial
    try:
        yolo_mode = _truthy(context.get("yolo_mode")) if isinstance(context, dict) else False
        result = run_computer_action(
            str(action),
            dict(input_data.get("payload") or {}),
            context if isinstance(context, dict) else None,
            tool_name=tool_name,
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


def _settings_permission_denial(tool_name, input_data, context):
    try:
        from domain.tool.permission_checker import PermissionChecker
        from domain.tool.registry import ToolRegistry

        registry = ToolRegistry()
        tool_def = registry.get(tool_name) or {
            "tool_id": tool_name,
            "name": tool_name,
            "tags": ["browser", "computer"],
            "action_type": "desktop",
        }
        decision = PermissionChecker(registry=registry).decide(
            tool_name,
            context=context if isinstance(context, dict) else {},
            arguments=input_data if isinstance(input_data, dict) else {},
            tool_def=tool_def,
        )
    except Exception:
        return None
    if decision.get("action") != "deny":
        return None
    response = error(
        "Tool '{}' blocked by Settings policy".format(tool_name),
        code="PERMISSION_DENIED",
    )
    response["error"]["details"] = {
        "tool_name": tool_name,
        "action": decision.get("action"),
        "matched_by": decision.get("matched_by"),
        "matched_value": decision.get("matched_value"),
        "reason": decision.get("reason") or "blocked_by_policy",
    }
    return response
