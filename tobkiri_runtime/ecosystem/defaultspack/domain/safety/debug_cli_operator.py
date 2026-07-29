"""Fail-closed verification for one-shot Launcher debug CLI decisions."""

from __future__ import annotations

import hmac
from typing import Any

from domain.host_bridge.viewer_broker_client import ViewerBrokerClient

from .approval import get_approval_request


class DebugCliOperatorError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _detail(request: dict[str, Any], *keys: str) -> str:
    details = request.get("details")
    if not isinstance(details, dict):
        details = {}
    for key in keys:
        value = _text(details.get(key))
        if value:
            return value
    return ""


def verify_debug_cli_decision(
    request_id: str,
    expected_digest: str,
    operator: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(operator, dict):
        raise DebugCliOperatorError("debug_cli_operator is required")
    request = get_approval_request(request_id)
    if not request:
        raise DebugCliOperatorError("approval request not found")
    if _text(request.get("status")) != "pending":
        raise DebugCliOperatorError("approval request is no longer pending")
    actual_digest = _text(request.get("args_hash"))
    if not expected_digest or not hmac.compare_digest(expected_digest, actual_digest):
        raise DebugCliOperatorError("approval request digest changed")

    expected = {
        "kind": "debug_cli_operator",
        "origin": "launcher_debug_cli",
        "scope": "once",
        "request_id": request_id,
        "canonical_arguments_digest": actual_digest,
        "operation": _text(request.get("operation")),
        "permission_id": _detail(request, "permission_id", "approval_permission_id", "request_id")
        or request_id,
        "tool": _detail(request, "function_id", "tool", "action")
        or _text(request.get("operation")),
        "action": _detail(request, "action", "function_id") or _text(request.get("operation")),
        "conversation_owner": _detail(
            request, "conversation_owner", "conversation_id", "profile_id"
        )
        or "local",
    }
    for key, value in expected.items():
        if _text(operator.get(key)) != value:
            raise DebugCliOperatorError(f"debug operator {key} mismatch")
    if int(operator.get("expires_at") or 0) > int(request.get("expires_at") or 0):
        raise DebugCliOperatorError("debug operator outlives approval request")
    target_digest = _detail(request, "target_digest", "snapshot_digest")
    if _text(operator.get("target_digest")) != target_digest:
        raise DebugCliOperatorError("debug operator target digest mismatch")

    broker = ViewerBrokerClient.from_environment()
    if not broker.available():
        raise DebugCliOperatorError("Launcher host broker is unavailable")
    try:
        result = broker.verify_debug_cli_operator(operator)
    except Exception as exc:
        raise DebugCliOperatorError("Launcher rejected debug operator") from exc
    if result.get("ok") is not True or result.get("verified") is not True:
        raise DebugCliOperatorError("Launcher rejected debug operator")
    return request
