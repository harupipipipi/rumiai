from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.memory2.memos import DEFAULT_PERSONALIZATION_FOLDER_ID, MemoStore


def run(input_data: dict[str, Any], context: Any = None) -> dict[str, Any]:
    del context
    data = input_data if isinstance(input_data, dict) else {}
    method = str(data.get("_method") or data.get("method") or "").upper()
    action = str(data.get("action") or "").strip().lower()
    if not action:
        action = {
            "GET": "list",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }.get(method, "list")

    store = MemoStore()
    try:
        if action == "list":
            return ok(
                {
                    "notes": store.list_notes(
                        folder_id=_folder_key(data) or None,
                        limit=_limit(data, 50),
                        include_archived=bool(data.get("include_archived")),
                    )
                }
            )
        if action == "search":
            return ok(
                {
                    "results": store.search_notes(
                        str(data.get("query") or data.get("q") or ""),
                        folder_id=_folder_key(data) or None,
                        limit=_limit(data, 20),
                    )
                }
            )
        if action == "get":
            note = store.get_note(_note_key(data))
            if note is None:
                return error("memo note not found", "NOT_FOUND")
            return ok(note)
        if action in {"create", "add", "write"}:
            return ok(
                store.create_note(
                    str(data.get("content") or data.get("text") or ""),
                    title=str(data.get("title") or ""),
                    folder_id=_folder_key(data) or DEFAULT_PERSONALIZATION_FOLDER_ID,
                    metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                    source=str(data.get("source") or "manual"),
                    note_id=str(data.get("id") or data.get("note_id") or "").strip() or None,
                )
            )
        if action == "update":
            note = store.update_note(_note_key(data), data.get("updates") if isinstance(data.get("updates"), dict) else data)
            if note is None:
                return error("memo note not found", "NOT_FOUND")
            return ok(note)
        if action == "delete":
            return ok({"deleted": store.delete_note(_note_key(data))})
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error("memo note operation failed: " + str(exc), "MEMO_NOTE_ERROR")
    return error("unsupported memo note action", "INVALID_INPUT")


def tool_create_note(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = run({"action": "create", **_normalize_note_arguments(arguments or {})}, context or {})
    return _tool_result(result, success_summary="memo note created")


def tool_upsert_note(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    data = _normalize_note_arguments(arguments if isinstance(arguments, dict) else {})
    note_key = _note_key(data)
    action = "update" if note_key and MemoStore().get_note(note_key) is not None else "create"
    result = run({"action": action, **data}, context or {})
    return _tool_result(result, success_summary="memo note upserted")


def tool_get_note(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = run({"action": "get", **(arguments or {})}, context or {})
    return _tool_result(result, success_summary="memo note loaded")


def tool_search_notes(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = run({"action": "search", **(arguments or {})}, context or {})
    return _tool_result(result, success_summary="memo search completed")


def tool_list_notes(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = run({"action": "list", **(arguments or {})}, context or {})
    return _tool_result(result, success_summary="memo notes listed")


def _tool_result(result: dict[str, Any], *, success_summary: str) -> dict[str, Any]:
    if result.get("status") != "ok":
        err = result.get("error") if isinstance(result.get("error"), dict) else {}
        return {
            "result": str(err.get("message") or "memo tool failed"),
            "is_error": True,
            "widget": {"type": "memo", "response": result},
        }
    return {
        "result": success_summary,
        "is_error": False,
        "widget": {"type": "memo", **(result.get("data") if isinstance(result.get("data"), dict) else {"data": result.get("data")})},
    }


def _folder_key(data: dict[str, Any]) -> str:
    return str(data.get("folder_id") or data.get("folder") or data.get("folder_slug") or "").strip()


def _normalize_note_arguments(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data or {})
    folder_key = _folder_key(normalized)
    if "/" not in folder_key:
        return normalized
    parts = [part.strip() for part in folder_key.split("/") if part.strip()]
    if len(parts) < 2:
        return normalized
    normalized["folder_id"] = parts[0]
    if not str(normalized.get("title") or "").strip() and not str(normalized.get("note_id") or normalized.get("id") or "").strip():
        normalized["title"] = parts[-1]
    metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
    normalized["metadata"] = {**metadata, "requested_memo_path": folder_key}
    return normalized


def _note_key(data: dict[str, Any]) -> str:
    return str(data.get("note_id") or data.get("id") or "").strip()


def _limit(data: dict[str, Any], default: int) -> int:
    try:
        return max(1, min(int(data.get("limit", default) or default), 200))
    except (TypeError, ValueError):
        return default
