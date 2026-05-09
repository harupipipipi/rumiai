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
    user_approved_actions = {
        "browser.open_url",
        "computer.move",
        "computer.click",
        "computer.type",
        "computer.key",
        "computer.scroll",
    }
    user_requested = bool(isinstance(context, dict) and context.get("user_requested_computer_use"))
    yolo_mode = bool(context.get("yolo_mode")) if isinstance(context, dict) else False
    if user_requested and action == "browser.open_url" and not any(
        key in payload for key in ("persistent", "profile_id", "session_id")
    ):
        payload["persistent"] = False
    payload = _payload_with_context_defaults(action, payload, context)
    result = BrowserComputerController(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=yolo_mode or (user_requested and action in user_approved_actions),
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
    if action.startswith("computer.") and action not in {"computer.windows", "computer.apps"}:
        target_app = context.get("computer_use_target_app")
        target_title = context.get("computer_use_target_title")
        if isinstance(target_app, str) and target_app.strip():
            payload.setdefault("app", target_app.strip())
        if isinstance(target_title, str) and target_title.strip():
            payload.setdefault("title", target_title.strip())
    if context.get("computer_use_allow_foreground_fallback") is True:
        payload.setdefault("allow_foreground_fallback", True)
        payload.setdefault("allow_user_input_overlap", True)
    if context.get("computer_use_background_preferred") is True and action in {"computer.type", "computer.key"}:
        payload.setdefault("background", True)
        payload.setdefault("driver", "auto")
    if context.get("computer_use_background_required") is True:
        payload.setdefault("allow_foreground_fallback", False)
    if (
        context.get("user_requested_computer_use") is True
        and action == "computer.click"
        and context.get("computer_use_background_required") is not True
    ):
        payload.setdefault("physical", True)
    return payload
