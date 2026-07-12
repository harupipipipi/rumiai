from __future__ import annotations

from typing import Any, Callable

from blocks._common import error, ok
from domain.remote.task_gateway import RemoteTaskGatewayError


def _status_code_for_gateway_error(code: str) -> int:
    normalized = str(code or "").upper()
    if normalized in {"INVALID_INPUT", "INPUT_TOO_LARGE", "UNKNOWN_TARGET_AGENT"}:
        return 400
    if normalized == "NOT_FOUND":
        return 404
    if normalized in {"CONFLICT", "INVALID_STATE", "CANCEL_CONFLICT"}:
        return 409
    return 500


def run_gateway(call: Callable[[], dict[str, Any]]):
    try:
        return ok(call())
    except RemoteTaskGatewayError as exc:
        result = error(str(exc), exc.code)
        result["status_code"] = _status_code_for_gateway_error(exc.code)
        return result
    except Exception as exc:
        result = error("remote task gateway failed: " + str(exc), "REMOTE_GATEWAY_ERROR")
        result["status_code"] = 500
        return result
