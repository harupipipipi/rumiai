from __future__ import annotations

import hashlib
from typing import Any

from domain.safety.audit import record_execution


def opaque_fingerprint(value: Any) -> str:
    raw = str(value or "").encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:12]


def record_share_event(
    operation: str,
    *,
    target_id: Any = None,
    mode: str | None = None,
    result: str = "ok",
    message_count: int | None = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "target_fingerprint": opaque_fingerprint(target_id),
        "result": str(result)[:40],
    }
    if mode:
        arguments["mode"] = str(mode)[:40]
    if message_count is not None:
        arguments["message_count"] = max(0, int(message_count))
    entry = record_execution(
        f"conversation_share.{operation}",
        "medium" if operation in {"link_create", "import", "revoke"} else "low",
        arguments,
        privacy="content_and_identifiers_excluded",
    )
    return {
        "operation": operation,
        "timestamp": entry["timestamp"],
        "result": str(result)[:40],
        **({"mode": str(mode)[:40]} if mode else {}),
    }
