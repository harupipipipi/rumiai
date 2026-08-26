from __future__ import annotations

import re
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
    action = str(args.get("action", "browser.session"))
    payload = dict(args.get("payload") or {})
    tool_name = str(args.get("tool_name") or "browser_computer").strip() or "browser_computer"
    payload = _payload_with_sequence_defaults(payload, context, args)
    tool_arguments = args.get("tool_arguments")
    if not isinstance(tool_arguments, dict) or not tool_arguments:
        tool_arguments = _tool_arguments_from_run_args(args)
    artifact_root = None
    workspace = context.get("conversation_workspace_dir") if isinstance(context, dict) else None
    if isinstance(workspace, str) and workspace:
        artifact_root = Path(workspace) / "tools" / "computer"
    user_requested = bool(isinstance(context, dict) and context.get("user_requested_computer_use"))
    yolo_mode = _truthy(context.get("yolo_mode"))
    if user_requested and action == "browser.open_url" and not any(
        key in payload for key in ("persistent", "profile_id", "session_id")
    ):
        payload["persistent"] = False
    payload = _payload_with_context_defaults(action, payload, context)
    payload = _payload_with_open_url_defaults(action, payload, args)
    sequence_id = _sequence_id_from_mapping(payload)
    try:
        run_computer_action = _run_computer_action()
        result = run_computer_action(
            action,
            payload,
            context if isinstance(context, dict) else None,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            artifact_root=artifact_root,
            yolo_mode=yolo_mode,
        )
        summary = "{} {} completed".format(tool_name, result.get("action", "action"))
        prompt = _result_prompt(result)
        if result.get("requires_approval") or result.get("approval_required"):
            summary = prompt or "{} {} requires approval".format(tool_name, result.get("action", "action"))
        elif result.get("is_error"):
            summary = "{} {} failed".format(tool_name, result.get("action", "action"))
            if prompt:
                summary += ": {}".format(prompt)
        if result.get("path"):
            summary += "; artifact: {}".format(result.get("path"))
        return tool_result(summary, widget={"type": tool_name, **result}, is_error=bool(result.get("is_error")))
    finally:
        _end_haze_sequence(sequence_id)


def _run_computer_action():
    try:
        from ecosystem.defaultspack.domain.host_bridge.computer_router import run_computer_action
    except ImportError:
        from domain.host_bridge.computer_router import run_computer_action
    return run_computer_action


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
        physical_clicks = _truthy(context.get("computer_use_physical_clicks"))
        if isinstance(target_app, str) and target_app.strip():
            payload.setdefault("app", target_app.strip())
        if isinstance(target_title, str) and target_title.strip():
            payload.setdefault("title", target_title.strip())
        if physical_clicks and action == "computer.click" and "physical" not in payload:
            payload["physical"] = True
    return payload


_URL_IN_TEXT_RE = re.compile(r"(?:https?://|file://|www\.)[^\s\"'<>]+")


def _payload_with_open_url_defaults(action, payload, args):
    payload = dict(payload or {})
    if action != "browser.open_url" or payload.get("url"):
        return payload
    for key in ("value", "text", "target", "href", "link", "url_contains", "title", "title_contains"):
        candidate = _url_from_text(str(payload.get(key) or ""))
        if candidate:
            payload["url"] = candidate
            return payload
    tool_arguments = args.get("tool_arguments") if isinstance(args, dict) else None
    if isinstance(tool_arguments, dict):
        for key in ("value", "text", "target", "href", "link", "url_contains", "title", "title_contains", "action"):
            candidate = _url_from_text(str(tool_arguments.get(key) or ""))
            if candidate:
                payload["url"] = candidate
                return payload
    return payload


def _url_from_text(value):
    if not isinstance(value, str):
        return ""
    match = _URL_IN_TEXT_RE.search(value.strip())
    if not match:
        return ""
    url = match.group(0).rstrip(".,;)")
    if url.startswith("www."):
        return "https://" + url
    return url


def _tool_arguments_from_run_args(args):
    if not isinstance(args, dict):
        return {}
    return {
        key: value
        for key, value in args.items()
        if key not in {"tool_name", "tool_arguments"}
    }


def _result_prompt(result):
    if not isinstance(result, dict):
        return ""
    for key in ("user_prompt", "message", "reason", "approval_hint"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    recovery = result.get("recovery")
    if isinstance(recovery, dict):
        for key in ("prompt", "note"):
            value = recovery.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


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


def _end_haze_sequence(sequence_id):
    sequence_id = str(sequence_id or "").strip()
    if not sequence_id:
        return
    try:
        try:
            from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import ComputerUseEdgeHazeManager
        except ImportError:
            from domain.computer.mac.edge_haze import ComputerUseEdgeHazeManager

        pack_root = Path(__file__).resolve().parents[2]
        ComputerUseEdgeHazeManager.from_pack_root(pack_root).end_sequence(sequence_id)
    except Exception:
        return


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
