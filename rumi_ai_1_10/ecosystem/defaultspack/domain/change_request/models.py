from __future__ import annotations

import time
import uuid
from typing import Any


SCHEMA_VERSION = 1
STATUS_VALUES = {"open", "closed", "archived"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_change_request_id() -> str:
    return "cr_" + uuid.uuid4().hex


def sanitize_change_request_id(value: Any) -> str:
    text = str(value or "").strip()
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if not text or any(ch not in allowed for ch in text):
        raise ValueError("change request id is invalid")
    return text


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    record = dict(raw or {})
    record["id"] = sanitize_change_request_id(record.get("id"))
    record["title"] = str(record.get("title") or "Untitled review")
    record["description"] = str(record.get("description") or "")
    record["status"] = str(record.get("status") or "open")
    if record["status"] not in STATUS_VALUES:
        record["status"] = "open"
    record["workspace_root"] = str(record.get("workspace_root") or "")
    record["workspace_id"] = record.get("workspace_id") or None
    record["created_at"] = str(record.get("created_at") or utc_now())
    record["updated_at"] = str(record.get("updated_at") or record["created_at"])
    record["initial_snapshot"] = (
        record.get("initial_snapshot") if isinstance(record.get("initial_snapshot"), dict) else {}
    )
    record["latest_snapshot"] = (
        record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
    )
    history = record.get("snapshot_history")
    record["snapshot_history"] = history if isinstance(history, list) else []
    metadata = record.get("metadata")
    record["metadata"] = metadata if isinstance(metadata, dict) else {}
    return record
