"""Server-side approval helpers for coding blocks."""

from __future__ import annotations

from typing import Any

from domain.safety.audit import record_approval, record_denial


def _approval_module():
    from domain.safety import approval

    return approval


def _token_from_input(input_data: dict[str, Any] | None) -> str:
    if not isinstance(input_data, dict):
        return ""
    token = str(input_data.get("approval_token") or "").strip()
    if token:
        return token
    headers = input_data.get("_headers")
    if isinstance(headers, dict):
        return str(headers.get("X-Rumi-Approval") or headers.get("x-rumi-approval") or "").strip()
    return ""


def is_server_approved(context=None, operation: str | None = None, input_data: dict[str, Any] | None = None):
    """Return True only for trusted server context or a valid signed approval token."""
    if isinstance(context, dict) and bool(context.get("_tool_server_approved")):
        return True
    if not operation:
        return False
    token = _token_from_input(input_data)
    if not token:
        return False
    approval = _approval_module()
    verification = approval.verify_execution_token(token, operation, approval.hash_arguments(input_data))
    if verification.valid:
        record_approval(operation, verification.request_id, "token_accepted")
        return True
    record_denial(
        operation,
        "high",
        verification.code or "APPROVAL_INVALID",
        input_data or {},
        request_id=verification.request_id,
    )
    return False


def approval_error(operation: str, input_data: dict[str, Any] | None) -> dict[str, str] | None:
    token = _token_from_input(input_data)
    if not token:
        return None
    approval = _approval_module()
    verification = approval.verify_execution_token(
        token,
        operation,
        approval.hash_arguments(input_data),
        consume=False,
    )
    if verification.valid:
        return None
    return {
        "code": verification.code or "APPROVAL_INVALID",
        "message": verification.message or "approval token is invalid",
    }


def approval_invalid_response(operation: str, input_data: dict[str, Any] | None, error_func):
    invalid = approval_error(operation, input_data)
    if invalid is None:
        return None
    result = error_func(invalid["message"], code=invalid["code"])
    result["_http_status"] = 403
    return result


def approval_required(operation, risk_level="high", args: dict[str, Any] | None = None, **details):
    request = _approval_module().create_approval_request(
        operation,
        risk_level,
        args or details,
        details=details,
    )
    payload = {
        "approval_required": True,
        "risk_level": risk_level,
        "operation": operation,
        "approval_request_id": request["request_id"],
        "args_hash": request["args_hash"],
        "expires_at": request["expires_at"],
        "display_summary": request["display_summary"],
    }
    payload.update(details)
    record_approval(operation, request["request_id"], "requested", risk_level=risk_level)
    return payload
