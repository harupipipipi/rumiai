from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

from .viewer_broker_client import ViewerBrokerClient


def should_route_to_viewer(action: str) -> bool:
    if os.environ.get("RUMI_COMPUTER_HOST_INTERNAL") == "1":
        return False
    if platform.system() != "Darwin":
        return False
    return str(action or "").startswith("computer.")


def run_computer_action(
    action: str,
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    tool_name: str = "computer_use",
    tool_arguments: dict[str, Any] | None = None,
    artifact_root: Path | None = None,
    yolo_mode: bool = False,
) -> dict[str, Any]:
    normalized_action = str(action or "")
    normalized_payload = dict(payload or {})
    normalized_context = dict(context or {}) if isinstance(context, dict) else {}
    if not _approval_token_present(normalized_payload):
        approval_token = _approval_token_from_context(normalized_context, tool_name, normalized_action)
        if approval_token:
            normalized_payload["approval_token"] = approval_token
    effective_yolo_mode = bool(yolo_mode) or bool(normalized_context.get("_tool_server_approved"))
    if should_route_to_viewer(normalized_action):
        client = ViewerBrokerClient.from_environment()
        if client.available():
            try:
                result = client.run_computer(
                    normalized_action,
                    normalized_payload,
                    context=normalized_context,
                    artifact_root=artifact_root,
                )
                if not isinstance(result, dict):
                    return {"action": normalized_action, "result": result}
                if _is_request_approval_needed(result):
                    return _approval_required_response(
                        tool_name,
                        str(result.get("action") or normalized_action),
                        normalized_payload,
                        result,
                        normalized_context,
                    )
                return dict(result)
            except Exception as exc:
                return {
                    "action": normalized_action,
                    "is_error": True,
                    "reason": f"Rumi Viewer host broker is unavailable: {exc}",
                    "recovery": {
                        "kind": "open_rumi_viewer",
                        "note": "Open Rumi Viewer and grant macOS permissions there.",
                    },
                    "permission_subject": "Rumi Viewer",
                }
        return {
            "action": normalized_action,
            "is_error": True,
            "reason": "Rumi Viewer is required for computer control on macOS.",
            "recovery": {
                "kind": "open_rumi_viewer",
                "note": "Open Rumi Viewer and grant macOS permissions there.",
            },
            "permission_subject": "Rumi Viewer",
        }
    return _run_local_controller(
        normalized_action,
        normalized_payload,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        artifact_root=artifact_root,
        yolo_mode=effective_yolo_mode,
        context=normalized_context,
    )


def _run_local_controller(
    action: str,
    payload: dict[str, Any],
    *,
    tool_name: str,
    tool_arguments: dict[str, Any] | None,
    artifact_root: Path | None,
    yolo_mode: bool,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    result = BrowserComputerController(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=yolo_mode,
    )
    if not isinstance(result, dict):
        return {"action": action, "result": result}
    if _is_request_approval_needed(result):
        return _approval_required_response(
            tool_name,
            str(result.get("action") or action),
            payload,
            result,
            context,
        )
    return dict(result)


def _approval_token_present(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(str(payload.get("approval_token") or "").strip())


def _approval_token_from_context(
    context: dict[str, Any] | None,
    tool_name: str,
    action: str,
) -> str:
    if not isinstance(context, dict):
        return ""
    tokens = context.get("tool_approval_tokens")
    if not isinstance(tokens, dict):
        return ""
    for key in (str(tool_name or "").strip(), str(action or "").strip()):
        token = str(tokens.get(key) or "").strip()
        if token:
            return token
    return ""


def _context_value(context: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(context, dict):
        return ""
    for key in keys:
        value = str(context.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_request_approval_needed(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    if not bool(result.get("requires_approval") or result.get("approval_required")):
        return False
    return not str(result.get("approval_request_id") or result.get("request_id") or "").strip()


def _approval_required_response(
    tool_name: str,
    action: str,
    payload: dict[str, Any],
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if str(result.get("approval_request_id") or result.get("request_id") or "").strip():
        return result
    from domain.safety import approval

    safe_tool_name = str(tool_name or "computer_use").strip() or "computer_use"
    safe_action = str(action or safe_tool_name)
    request_arguments = _request_arguments(safe_tool_name, safe_action, payload)
    pack_id = _context_value(context, "owner_pack", "pack_id", "_source_pack_id") or "defaultspack"
    conversation_id = _context_value(context, "conversation_id", "conversation_turn_id")
    request = approval.create_approval_request(
        safe_action,
        "high",
        request_arguments,
        details={
            "tool_name": safe_tool_name,
            "action": safe_action,
            "function_id": safe_action,
            "payload": dict(payload or {}),
            "pack_id": pack_id,
            "conversation_id": conversation_id,
            "permission_subject": "Rumi Viewer",
        },
    )
    wrapped = dict(result)
    wrapped.update(
        {
            "action": safe_action,
            "tool_name": safe_tool_name,
            "operation": safe_action,
            "payload": dict(payload or {}),
            "requires_approval": True,
            "approval_required": True,
            "approval_request_id": request["request_id"],
            "request_id": request["request_id"],
            "risk_level": request.get("risk_level", "high"),
            "args_hash": request.get("args_hash"),
            "expires_at": request.get("expires_at"),
            "display_summary": request.get("display_summary") or safe_action,
            "permission_subject": "Rumi Viewer",
        }
    )
    if not wrapped.get("message") and wrapped.get("approval_hint"):
        wrapped["message"] = wrapped.get("approval_hint")
    warning = result.get("approval_warning")
    if isinstance(warning, str) and warning.strip():
        wrapped["approval_warning"] = warning
    expires_in = result.get("approval_expires_in_seconds")
    if expires_in is not None:
        wrapped["approval_expires_in_seconds"] = expires_in
    return wrapped


def _request_arguments(tool_name: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "browser_computer":
        return {"action": action, "payload": dict(payload or {})}
    return {"action": action, **dict(payload or {})}


sys.modules.setdefault("domain.host_bridge.computer_router", sys.modules[__name__])
sys.modules.setdefault("ecosystem.defaultspack.domain.host_bridge.computer_router", sys.modules[__name__])
