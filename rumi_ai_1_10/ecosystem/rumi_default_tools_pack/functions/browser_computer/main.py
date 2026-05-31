from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result

_SEQUENCE_ID_KEYS = (
    "computer_use_haze_sequence_id",
    "computer_use_sequence_id",
    "run_id",
    "request_id",
    "conversation_turn_id",
    "_flow_run_request_id",
    "_flow_execution_id",
)


def run(context, args):
    from ecosystem.defaultspack.domain.host_bridge.computer_router import run_computer_action

    action = str(args.get("action", "browser.session"))
    payload = dict(args.get("payload") or {})
    tool_name = str(args.get("tool_name") or "browser_computer").strip() or "browser_computer"
    payload = _payload_with_sequence_defaults(payload, context, args)
    artifact_root = None
    workspace = context.get("conversation_workspace_dir") if isinstance(context, dict) else None
    if isinstance(workspace, str) and workspace:
        artifact_root = Path(workspace) / "tools" / "computer"
    user_requested = bool(isinstance(context, dict) and context.get("user_requested_computer_use"))
    yolo_mode = _server_approved(context) if isinstance(context, dict) else False
    if user_requested and action == "browser.open_url" and not any(
        key in payload for key in ("persistent", "profile_id", "session_id")
    ):
        payload["persistent"] = False
    payload = _payload_with_context_defaults(action, payload, context)
    result = run_computer_action(
        action,
        payload,
        context if isinstance(context, dict) else None,
        tool_name=tool_name,
        artifact_root=artifact_root,
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
        if isinstance(target_app, str) and target_app.strip():
            payload.setdefault("app", target_app.strip())
        if isinstance(target_title, str) and target_title.strip():
            payload.setdefault("title", target_title.strip())
    return payload


def _payload_with_sequence_defaults(payload, context, args):
    payload = dict(payload or {})
    sequence_id = _sequence_id_from_mapping(payload) or _sequence_id_from_mapping(args)
    if not sequence_id and isinstance(context, dict):
        sequence_id = _sequence_id_from_mapping(context)
    if sequence_id:
        payload.setdefault("computer_use_haze_sequence_id", sequence_id)
    return payload


def _sequence_id_from_mapping(value):
    if not isinstance(value, dict):
        return ""
    for key in _SEQUENCE_ID_KEYS:
        candidate = str(value.get(key) or "").strip()
        if candidate:
            return candidate
    return ""


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _server_approved(context):
    if not isinstance(context, dict):
        return False
    if _truthy(context.get("yolo_mode")):
        return True
    return _truthy(context.get("_tool_server_approved")) or _truthy(
        context.get("_tool_server_approval_token_valid")
    )
