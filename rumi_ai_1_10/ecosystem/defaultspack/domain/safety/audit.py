from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


_LOCK = threading.RLock()
_SECRET_KEYS = ("api_key", "authorization", "token", "secret", "password", "cookie")


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def audit_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_AUDIT_PATH")
    if override:
        return Path(override)
    return _pack_root() / "user_data" / "audit" / "local_actions.jsonl"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in _SECRET_KEYS):
                redacted[key_text] = "***"
            else:
                redacted[key_text] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


def append_record(record: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "id": "aud_" + uuid.uuid4().hex,
        "timestamp": _now_iso(),
        **record,
    }
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(redact(entry), ensure_ascii=False, sort_keys=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return entry


def record_attempt(
    operation: str,
    risk: str,
    arguments: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return append_record(
        {
            "event": "attempt",
            "operation": operation,
            "risk": risk,
            "decision": "pending",
            "arguments": arguments or {},
            **extra,
        }
    )

def record_approval(operation: str, request_id: str, decision: str, **extra: Any) -> dict[str, Any]:
    return append_record(
        {
            "event": "approval",
            "operation": operation,
            "request_id": request_id,
            "decision": decision,
            **extra,
        }
    )


def record_execution(
    operation: str,
    risk: str,
    arguments: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return append_record(
        {
            "event": "execution",
            "operation": operation,
            "risk": risk,
            "decision": "executed",
            "arguments": arguments or {},
            **extra,
        }
    )


def record_denial(
    operation: str,
    risk: str,
    reason: str,
    arguments: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return append_record(
        {
            "event": "denial",
            "operation": operation,
            "risk": risk,
            "decision": "denied",
            "reason": reason,
            "arguments": arguments or {},
            **extra,
        }
    )


def record_failure(
    operation: str,
    risk: str,
    reason: str,
    arguments: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return append_record(
        {
            "event": "failure",
            "operation": operation,
            "risk": risk,
            "decision": "failed",
            "reason": reason,
            "arguments": arguments or {},
            **extra,
        }
    )
