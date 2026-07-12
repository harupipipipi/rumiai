from __future__ import annotations

from typing import Any


def ok(data: Any = None) -> dict[str, Any]:
    return {"status": "ok", "data": data}


def error(message: str, code: str = "ERROR", *, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": str(message)}
    if details is not None:
        payload["details"] = details
    return {"status": "error", "error": payload}


def normalize_output(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("status") in {"ok", "error"}:
        return value
    return ok(value)


def normalize_exception(exc: BaseException, *, code: str = "INTERNAL_ERROR") -> dict[str, Any]:
    return error(str(exc), code)
