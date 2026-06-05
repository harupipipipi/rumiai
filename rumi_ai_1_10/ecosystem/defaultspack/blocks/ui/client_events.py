from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.safety.audit import append_record


def _string(value: Any, *, max_length: int = 400) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_length]


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key)[:120]: _json_safe(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, list):
        return [_json_safe(item, depth=depth + 1) for item in value[:40]]
    if isinstance(value, tuple):
        return [_json_safe(item, depth=depth + 1) for item in value[:40]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    method = str(data.get("_method") or "POST").upper()
    if method != "POST":
        return error("unsupported method", "METHOD_NOT_ALLOWED")

    message = _string(data.get("message"), max_length=600)
    if not message:
        return error("message is required", "INVALID_INPUT")

    record = append_record(
        {
            "event": "client_diagnostic",
            "operation": "ui.client_diagnostic",
            "risk": "low",
            "decision": "recorded",
            "source": _string(data.get("source"), max_length=80) or "webapp",
            "category": _string(data.get("category"), max_length=80) or "frontend",
            "level": _string(data.get("level"), max_length=24) or "error",
            "message": message,
            "fingerprint": _string(data.get("fingerprint"), max_length=160),
            "conversation_id": _string(data.get("conversation_id"), max_length=120),
            "details": _json_safe(data.get("detail")),
        }
    )
    return ok({"recorded": True, "diagnostic_id": record["id"]})
