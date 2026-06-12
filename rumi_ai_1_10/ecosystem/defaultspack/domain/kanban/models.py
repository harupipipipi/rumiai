from __future__ import annotations

import json
import time
import uuid
from typing import Any

DEFAULT_COLUMNS = ("Backlog", "Doing", "Review", "Done")
SCOPE_TYPES = {"conversation", "workspace", "company", "global"}


class KanbanError(RuntimeError):
    code = "KANBAN_ERROR"
    http_status = 400


class KanbanValidationError(KanbanError, ValueError):
    code = "INVALID_INPUT"
    http_status = 400


class KanbanNotFoundError(KanbanError, KeyError):
    code = "NOT_FOUND"
    http_status = 404


def gen_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex


def now_ms() -> int:
    return int(time.time() * 1000)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except Exception:
        return fallback
    if isinstance(fallback, list):
        return parsed if isinstance(parsed, list) else fallback
    if isinstance(fallback, dict):
        return parsed if isinstance(parsed, dict) else fallback
    return parsed


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        values = [str(item).strip() for item in value]
    else:
        values = []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def clean_list(value: Any) -> list[Any]:
    return [item for item in value] if isinstance(value, list) else []


def normalize_scope(scope_type: str, scope_id: str) -> tuple[str, str]:
    scope_type = str(scope_type or "global").strip().lower()
    scope_id = str(scope_id or "default").strip()
    if scope_type not in SCOPE_TYPES:
        raise KanbanValidationError("invalid scope_type: " + scope_type)
    if not scope_id:
        raise KanbanValidationError("scope_id is required")
    return scope_type, scope_id


def is_done_column(title: str) -> bool:
    return str(title or "").strip().lower() in {"done", "complete", "completed", "closed"}
