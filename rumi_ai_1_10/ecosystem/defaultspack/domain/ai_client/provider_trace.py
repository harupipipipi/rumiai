from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from domain.chat.store import ChatStore


TRACE_SCHEMA_VERSION = "rumi.provider_trace.v1"
_SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|authorization|bearer|token|credential|password|secret)", re.IGNORECASE)
_DATA_IMAGE_RE = re.compile(r"^data:image/([^;,]+);base64,(.*)$", re.IGNORECASE | re.DOTALL)


def write_provider_trace(
    *,
    conversation_id: str,
    request_id: str,
    provider: str,
    model: str,
    api_family: str,
    ir_schema_version: str,
    capability_summary: dict[str, Any],
    planning_metadata: dict[str, Any],
    dropped_features: list[Any],
    bridge_actions: list[Any],
    warnings: list[Any],
    compiled_payload: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None,
    store: ChatStore | None = None,
) -> dict[str, Any]:
    chat_store = store or ChatStore()
    trace_dir = chat_store.conversation_workspace_dir(conversation_id) / "provider_traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    safe_request_id = _safe_name(request_id or str(int(time.time() * 1000)))
    trace_path = trace_dir / f"{safe_request_id}.json"
    now = int(time.time() * 1000)
    payload = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "request_id": request_id,
        "conversation_id": conversation_id,
        "provider": provider,
        "model": model,
        "api_family": api_family,
        "ir_schema_version": ir_schema_version,
        "capability_summary": redact_sensitive_value(capability_summary),
        "planning_metadata": redact_sensitive_value(planning_metadata),
        "dropped_features": redact_sensitive_value(dropped_features),
        "bridge_actions": redact_sensitive_value(bridge_actions),
        "warnings": redact_sensitive_value(warnings),
        "compiled_payload": redact_sensitive_value(compiled_payload or {}),
        "response_summary": redact_sensitive_value(response_summary or {}),
        "timestamps": {"created_at": now, "updated_at": now},
    }
    trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "request_id": request_id,
        "provider": provider,
        "api_family": api_family,
        "trace_path": str(trace_path),
        "dropped_features": payload["dropped_features"],
        "warnings": payload["warnings"],
    }


def redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, str):
        match = _DATA_IMAGE_RE.match(value)
        if match:
            return f"data:image/{match.group(1)};base64,[REDACTED:{len(match.group(2))} chars]"
        if _SENSITIVE_KEY_RE.search(value) and len(value) > 24:
            return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if callable(value):
        return "[callable:{}]".format(getattr(value, "__name__", value.__class__.__name__))
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "")).strip("._")
    return cleaned[:120] or "provider-trace"
