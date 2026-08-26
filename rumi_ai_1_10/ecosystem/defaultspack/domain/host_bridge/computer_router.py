from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
from ..tool_policy.internal_context import tool_server_approval_context_is_internal

from .computer_host import ComputerHost, LocalControllerComputerHost, ViewerBrokerComputerHost
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
    controller_cls: type[Any] | None = None,
    computer_host: ComputerHost | None = None,
) -> dict[str, Any]:
    normalized_action = str(action or "")
    normalized_payload = dict(payload or {})
    normalized_context = dict(context or {}) if isinstance(context, dict) else {}
    if not _approval_token_present(normalized_payload):
        approval_token = _approval_token_from_context(normalized_context, tool_name, normalized_action)
        if approval_token:
            normalized_payload["approval_token"] = approval_token
    effective_yolo_mode = bool(yolo_mode) or _context_has_server_approval(normalized_context)
    host = computer_host or _default_computer_host(
        normalized_action,
        controller_cls=controller_cls,
    )
    return _run_computer_host(
        host,
        normalized_action,
        normalized_payload,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        artifact_root=artifact_root,
        yolo_mode=effective_yolo_mode,
        context=normalized_context,
    )


def _default_computer_host(
    action: str,
    *,
    controller_cls: type[Any] | None = None,
) -> ComputerHost:
    if should_route_to_viewer(action):
        return ViewerBrokerComputerHost(ViewerBrokerClient.from_environment())
    return LocalControllerComputerHost(controller_cls or BrowserComputerController)


def _run_computer_host(
    host: ComputerHost,
    action: str,
    payload: dict[str, Any],
    *,
    tool_name: str,
    tool_arguments: dict[str, Any] | None,
    artifact_root: Path | None,
    yolo_mode: bool,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    del tool_arguments
    result = host.run(
        action,
        payload,
        context=context,
        artifact_root=artifact_root,
        yolo_mode=yolo_mode,
    )
    if not isinstance(result, dict):
        return {"action": action, "result": result}
    if _is_request_approval_needed(result):
        approval_payload = result.get("payload") if isinstance(result.get("payload"), dict) else payload
        return _approval_required_response(
            tool_name,
            str(result.get("action") or action),
            dict(approval_payload),
            result,
            context,
        )
    return dict(result)


def _run_local_controller(
    action: str,
    payload: dict[str, Any],
    *,
    tool_name: str,
    tool_arguments: dict[str, Any] | None,
    artifact_root: Path | None,
    yolo_mode: bool,
    context: dict[str, Any] | None,
    controller_cls: type[Any] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for callers that still target the local controller."""
    return _run_computer_host(
        LocalControllerComputerHost(controller_cls or BrowserComputerController),
        action,
        payload,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        artifact_root=artifact_root,
        yolo_mode=yolo_mode,
        context=context,
    )


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


def _context_has_server_approval(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    return tool_server_approval_context_is_internal(context) or _context_has_verified_server_approval_token(context)


def _context_has_verified_server_approval_token(context: dict[str, Any]) -> bool:
    token = str(context.get("_tool_server_approval_token") or "").strip()
    operation = str(context.get("_tool_server_approval_operation") or "").strip()
    args_hash = str(context.get("_tool_server_approval_args_hash") or "").strip()
    if not token or not operation or not args_hash:
        return False
    pack_id = str(context.get("_tool_server_approval_pack_id") or "").strip()
    conversation_id = str(context.get("_tool_server_approval_conversation_id") or "").strip()
    for approval in _approval_modules():
        try:
            verification = approval.verify_execution_token(
                token,
                operation,
                args_hash,
                consume=False,
                pack_id=pack_id,
                conversation_id=conversation_id,
            )
        except Exception:
            continue
        if bool(getattr(verification, "valid", False)):
            return True
    return False


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
    approval = _approval_module()

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
    wrapped.pop("approval_token", None)
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


def _approval_module():
    from ..safety import approval

    return approval


def _approval_modules() -> list[Any]:
    modules: list[Any] = []
    for import_name in (
        "ecosystem.defaultspack.domain.safety.approval",
        "domain.safety.approval",
    ):
        try:
            module = __import__(import_name, fromlist=["approval"])
        except Exception:
            continue
        if module not in modules:
            modules.append(module)
    if not modules:
        try:
            modules.append(_approval_module())
        except Exception:
            pass
    return modules


sys.modules.setdefault("domain.host_bridge.computer_router", sys.modules[__name__])
sys.modules.setdefault("ecosystem.defaultspack.domain.host_bridge.computer_router", sys.modules[__name__])
for _parent_name in ("domain.host_bridge", "ecosystem.defaultspack.domain.host_bridge"):
    _parent = sys.modules.get(_parent_name)
    if _parent is not None:
        setattr(_parent, "computer_router", sys.modules[__name__])
