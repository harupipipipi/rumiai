from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.external.source_store import ExternalSourceStore


def run(input_data, context):
    del context
    data = input_data or {}
    method = str(data.get("_method") or "GET").upper()
    store = ExternalSourceStore()
    if method == "GET":
        return ok({"sources": store.list_sources()})
    if method not in {"POST", "PUT"}:
        return error("unsupported method", "METHOD_NOT_ALLOWED")

    provider, source_type, source_id = _source_identity(data)
    if not provider or not source_type or not source_id:
        return error("provider, source_type, and source_id are required", "INVALID_INPUT")
    enabled = _optional_bool(data.get("enabled"))
    allow_reply = _optional_bool(data.get("allow_reply"))
    allow_push = _optional_bool(data.get("allow_push"))
    label = str(data.get("label")) if "label" in data else None
    result = store.update_source(
        provider,
        source_type,
        source_id,
        enabled=enabled,
        allow_reply=allow_reply,
        allow_push=allow_push,
        label=label,
    )
    if not result.get("success"):
        return error(str(result.get("error") or "failed to update external source"), "EXTERNAL_SOURCE_UPDATE_FAILED")
    return ok({key: value for key, value in result.items() if key != "error"})


def _source_identity(data: dict[str, Any]) -> tuple[str, str, str]:
    key = str(data.get("key") or "").strip()
    if key:
        parts = key.split(":", 2)
        if len(parts) == 3:
            return parts[0].strip(), parts[1].strip(), parts[2].strip()
    return (
        str(data.get("provider") or "").strip(),
        str(data.get("source_type") or "").strip(),
        str(data.get("source_id") or "").strip(),
    )


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return None
