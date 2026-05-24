from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from domain.chat.store import ChatStore


TRACE_SCHEMA_VERSION = "rumi.provider_trace.v2"
_SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|authorization|bearer|token|credential|password|secret)", re.IGNORECASE)
_DATA_IMAGE_RE = re.compile(r"^data:image/([^;,]+);base64,(.*)$", re.IGNORECASE | re.DOTALL)
TRACE_MODE_ENV = "RUMI_DEFAULTSPACK_PROVIDER_TRACE"
TRACE_DEFAULT_MODE = "summary"
TRACE_FULL_MODE = "full"
TRACE_OFF_MODE = "off"
TRACE_MAX_STRING_LENGTH = 4096
TRACE_MAX_COLLECTION_ITEMS = 32


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
    trace_mode = provider_trace_mode()
    if trace_mode == TRACE_OFF_MODE:
        return {
            "request_id": request_id,
            "provider": provider,
            "api_family": api_family,
            "trace_mode": trace_mode,
        }
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
        "trace_mode": trace_mode,
        "ir_schema_version": ir_schema_version,
        "capability_summary": redact_sensitive_value(capability_summary),
        "planning_metadata": redact_sensitive_value(planning_metadata),
        "dropped_features": redact_sensitive_value(dropped_features),
        "bridge_actions": redact_sensitive_value(bridge_actions),
        "warnings": redact_sensitive_value(warnings),
        "compiled_payload": _compiled_payload_for_trace(compiled_payload or {}, trace_mode=trace_mode),
        "response_summary": redact_sensitive_value(response_summary or {}),
        "timestamps": {"created_at": now, "updated_at": now},
    }
    trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "request_id": request_id,
        "provider": provider,
        "api_family": api_family,
        "trace_mode": trace_mode,
        "trace_path": str(trace_path),
        "dropped_features": payload["dropped_features"],
        "warnings": payload["warnings"],
    }


def provider_trace_mode() -> str:
    value = str(os.environ.get(TRACE_MODE_ENV, TRACE_DEFAULT_MODE) or TRACE_DEFAULT_MODE).strip().lower()
    if value in {TRACE_FULL_MODE, TRACE_OFF_MODE}:
        return value
    return TRACE_DEFAULT_MODE


def _compiled_payload_for_trace(compiled_payload: dict[str, Any], *, trace_mode: str) -> dict[str, Any]:
    if trace_mode == TRACE_FULL_MODE:
        return sanitize_trace_value(compiled_payload)
    return summarize_compiled_payload(compiled_payload)


def summarize_compiled_payload(compiled_payload: dict[str, Any]) -> dict[str, Any]:
    payload = compiled_payload if isinstance(compiled_payload, dict) else {}
    messages = payload.get("legacy_messages")
    tools = payload.get("tools")
    params = payload.get("params")
    return {
        "mode": TRACE_DEFAULT_MODE,
        "legacy_messages": _summarize_legacy_messages(messages),
        "tools": _summarize_tools(tools),
        "params": _summarize_params(params),
    }


def sanitize_trace_value(value: Any, *, max_string_length: int = TRACE_MAX_STRING_LENGTH, max_collection_items: int = TRACE_MAX_COLLECTION_ITEMS) -> Any:
    if isinstance(value, dict):
        redacted = {}
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            if index >= max_collection_items:
                redacted["__truncated_items__"] = len(items) - max_collection_items
                break
            if _SENSITIVE_KEY_RE.search(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = sanitize_trace_value(
                    item,
                    max_string_length=max_string_length,
                    max_collection_items=max_collection_items,
                )
        return redacted
    if isinstance(value, list):
        redacted = [
            sanitize_trace_value(
                item,
                max_string_length=max_string_length,
                max_collection_items=max_collection_items,
            )
            for item in value[:max_collection_items]
        ]
        if len(value) > max_collection_items:
            redacted.append(f"[TRUNCATED {len(value) - max_collection_items} items]")
        return redacted
    if isinstance(value, tuple):
        return sanitize_trace_value(
            list(value),
            max_string_length=max_string_length,
            max_collection_items=max_collection_items,
        )
    if isinstance(value, str):
        match = _DATA_IMAGE_RE.match(value)
        if match:
            return f"data:image/{match.group(1)};base64,[REDACTED:{len(match.group(2))} chars]"
        if _SENSITIVE_KEY_RE.search(value) and len(value) > 24:
            return "[REDACTED]"
        if len(value) > max_string_length:
            return f"{value[:max_string_length]}...[TRUNCATED {len(value) - max_string_length} chars]"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if callable(value):
        return "[callable:{}]".format(getattr(value, "__name__", value.__class__.__name__))
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


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


def _summarize_legacy_messages(messages: Any) -> dict[str, Any]:
    role_counts: dict[str, int] = {}
    summary = {
        "count": 0,
        "role_counts": role_counts,
        "approx_text_chars": 0,
        "tool_call_count": 0,
    }
    if not isinstance(messages, list):
        return summary
    summary["count"] = len(messages)
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
        summary["approx_text_chars"] += _approx_text_size(message.get("content"))
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            summary["tool_call_count"] += len(tool_calls)
    return summary


def _summarize_tools(tools: Any) -> dict[str, Any]:
    if not isinstance(tools, list):
        return {"count": 0, "names": []}
    names: list[str] = []
    for tool in tools:
        name = ""
        if isinstance(tool, dict):
            name = str(tool.get("name") or tool.get("function", {}).get("name") or "").strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= TRACE_MAX_COLLECTION_ITEMS:
            break
    return {"count": len(tools), "names": names}


def _summarize_params(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {"count": 0, "keys": []}
    keys = [str(key) for key in list(params.keys())[:TRACE_MAX_COLLECTION_ITEMS]]
    summary: dict[str, Any] = {"count": len(params), "keys": keys}
    if len(params) > TRACE_MAX_COLLECTION_ITEMS:
        summary["truncated_keys"] = len(params) - TRACE_MAX_COLLECTION_ITEMS
    return summary


def _approx_text_size(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_approx_text_size(item) for item in value[:TRACE_MAX_COLLECTION_ITEMS])
    if isinstance(value, dict):
        total = 0
        for item in list(value.values())[:TRACE_MAX_COLLECTION_ITEMS]:
            total += _approx_text_size(item)
        return total
    return 0


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "")).strip("._")
    return cleaned[:120] or "provider-trace"
