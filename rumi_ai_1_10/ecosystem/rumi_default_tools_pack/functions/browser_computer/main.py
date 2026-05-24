from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    action = str(args.get("action", "browser.session"))
    payload = dict(args.get("payload") or {})
    artifact_root = None
    workspace = context.get("conversation_workspace_dir") if isinstance(context, dict) else None
    if isinstance(workspace, str) and workspace:
        artifact_root = Path(workspace) / "tools" / "computer"
    user_requested = bool(isinstance(context, dict) and context.get("user_requested_computer_use"))
    yolo_mode = _truthy(context.get("yolo_mode")) if isinstance(context, dict) else False
    if user_requested and action == "browser.open_url" and not any(
        key in payload for key in ("persistent", "profile_id", "session_id")
    ):
        payload["persistent"] = False
    payload = _payload_with_context_defaults(action, payload, context)
    result = BrowserComputerController(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=yolo_mode,
    )
    summary = "browser_computer {} completed".format(result.get("action", "action"))
    if result.get("is_error"):
        summary = "browser_computer {} failed".format(result.get("action", "action"))
        if result.get("reason"):
            summary += ": {}".format(result.get("reason"))
    if result.get("path"):
        summary += "; artifact: {}".format(result.get("path"))
    return tool_result(summary, widget={"type": "browser_computer", **result}, is_error=bool(result.get("is_error")))


def _payload_with_context_defaults(action, payload, context):
    payload = dict(payload or {})
    if not isinstance(context, dict):
        return payload
    sequence_id = str(
        context.get("computer_use_haze_sequence_id")
        or context.get("run_id")
        or context.get("request_id")
        or ""
    ).strip()
    if sequence_id and (action.startswith("computer.") or action.startswith("browser.")):
        payload.setdefault("computer_use_haze_sequence_id", sequence_id)
    if action == "browser.open_url":
        target_app = context.get("computer_use_target_app")
        if isinstance(target_app, str) and target_app.strip() and not any(
            payload.get(key) for key in ("app", "application", "browser", "browser_app")
        ):
            payload["app"] = target_app.strip()
        return payload
    if action.startswith("computer.") and action not in {"computer.windows", "computer.apps"}:
        target_app = context.get("computer_use_target_app")
        target_title = context.get("computer_use_target_title")
        target_monitor = context.get("computer_use_target_monitor")
        target_display = context.get("computer_use_target_display")
        if isinstance(target_app, str) and target_app.strip():
            payload.setdefault("app", target_app.strip())
        if isinstance(target_title, str) and target_title.strip():
            payload.setdefault("title", target_title.strip())
        if isinstance(target_monitor, (str, int)) and str(target_monitor).strip():
            payload.setdefault("monitor_id", str(target_monitor).strip())
        if isinstance(target_display, (str, int)) and str(target_display).strip():
            payload.setdefault("display_id", str(target_display).strip())
    return payload


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
