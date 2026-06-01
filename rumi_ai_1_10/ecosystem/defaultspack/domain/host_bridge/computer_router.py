from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from .viewer_broker_client import ViewerBrokerClient


def should_route_to_viewer(action: str) -> bool:
    if os.environ.get("RUMI_COMPUTER_HOST_INTERNAL") == "1":
        return False
    if not str(action or "").startswith("computer."):
        return False
    force_viewer = str(os.environ.get("RUMI_COMPUTER_ROUTE_VIEWER", "") or "").strip().lower()
    if force_viewer in {"1", "true", "yes", "on"}:
        return True
    if platform.system() == "Darwin":
        return True
    return ViewerBrokerClient.from_environment().available()


def run_computer_action(
    action: str,
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    tool_name: str = "computer_use",
    artifact_root: Path | None = None,
    yolo_mode: bool = False,
) -> dict[str, Any]:
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    payload = dict(payload or {})
    if not _approval_token_present(payload):
        approval_token = _approval_token_from_context(context, tool_name, action)
        if approval_token:
            payload["approval_token"] = approval_token
    if should_route_to_viewer(action):
        client = ViewerBrokerClient.from_environment()
        if client.available():
            try:
                result = client.run_computer(action, payload, context=context, artifact_root=artifact_root)
                if _requires_approval(result):
                    return _approval_required_response(tool_name, action, payload, result)
                return result
            except Exception as exc:
                return {
                    "action": action,
                    "is_error": True,
                    "reason": f"Rumi Viewer host broker is unavailable: {exc}",
                    "recovery": {
                        "kind": "open_rumi_viewer",
                        "note": "Open Rumi Viewer and make sure its host broker connection is available.",
                    },
                    "permission_subject": "Rumi Viewer",
                }
        return {
            "action": action,
            "is_error": True,
            "reason": "Rumi Viewer is required for this computer control route.",
            "recovery": {
                "kind": "open_rumi_viewer",
                "note": "Open Rumi Viewer and make sure its host broker connection is available.",
            },
            "permission_subject": "Rumi Viewer",
        }
    return BrowserComputerController(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=yolo_mode,
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


def _requires_approval(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    return bool(result.get("requires_approval") or result.get("approval_required"))


def _approval_required_response(
    tool_name: str,
    action: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    if str(result.get("approval_request_id") or result.get("request_id") or "").strip():
        return result
    from domain.safety import approval

    request = approval.create_approval_request(
        str(action or tool_name or "computer_use"),
        "high",
        payload,
        details={
            "tool_name": str(tool_name or "computer_use"),
            "action": str(action or tool_name or "computer_use"),
            "payload": dict(payload or {}),
            "permission_subject": "Rumi Viewer",
        },
    )
    wrapped = dict(result)
    wrapped.update(
        {
            "action": str(action or tool_name or "computer_use"),
            "tool_name": str(tool_name or "computer_use"),
            "operation": str(action or tool_name or "computer_use"),
            "payload": dict(payload or {}),
            "requires_approval": True,
            "approval_required": True,
            "approval_request_id": request["request_id"],
            "request_id": request["request_id"],
            "risk_level": request.get("risk_level", "high"),
            "args_hash": request.get("args_hash"),
            "expires_at": request.get("expires_at"),
            "display_summary": request.get("display_summary") or str(action or tool_name or "computer_use"),
            "permission_subject": "Rumi Viewer",
        }
    )
    if not wrapped.get("message") and wrapped.get("approval_hint"):
        wrapped["message"] = wrapped.get("approval_hint")
    return wrapped
