from __future__ import annotations

from typing import Any


def normalize_context(context: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(context or {})
    normalized.setdefault("principal_id", "defaultspack")
    normalized.setdefault("pack_id", "defaultspack")
    return normalized


def principal_from_context(
    context: dict[str, Any] | None,
    *,
    default: str = "defaultspack",
) -> str:
    for key in ("principal_id", "pack_id", "_source_pack_id"):
        value = (context or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default
