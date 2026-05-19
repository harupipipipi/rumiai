from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.memory2.memos import MemoStore


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
            return ok({"folders": store.list_folders(include_archived=bool(data.get("include_archived")))})
        if action == "get":
            folder = store.get_folder(_folder_key(data))
            if folder is None:
                return error("memo folder not found", "NOT_FOUND")
            return ok(folder)
        if action == "create":
            return ok(
                store.create_folder(
                    str(data.get("name") or data.get("title") or ""),
                    folder_id=str(data.get("id") or data.get("folder_id") or "").strip() or None,
                    slug=str(data.get("slug") or "").strip() or None,
                    description=str(data.get("description") or ""),
                    metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                )
            )
        if action == "update":
            folder = store.update_folder(_folder_key(data), data.get("updates") if isinstance(data.get("updates"), dict) else data)
            if folder is None:
                return error("memo folder not found", "NOT_FOUND")
            return ok(folder)
        if action == "delete":
            return ok({"deleted": store.delete_folder(_folder_key(data))})
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")
    except Exception as exc:
        return error("memo folder operation failed: " + str(exc), "MEMO_FOLDER_ERROR")
    return error("unsupported memo folder action", "INVALID_INPUT")


def tool_upsert_folder(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    data = arguments if isinstance(arguments, dict) else {}
    store = MemoStore()
    try:
        key = _folder_key(data)
        existing = store.get_folder(key) if key else None
        if existing is not None:
            folder = store.update_folder(key, data)
        else:
            folder = store.create_folder(
                str(data.get("name") or data.get("title") or key or ""),
                folder_id=str(data.get("id") or data.get("folder_id") or "").strip() or None,
                slug=str(data.get("slug") or key or "").strip() or None,
                description=str(data.get("description") or ""),
                metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            )
    except Exception as exc:
        return {"result": "memo folder upsert failed: " + str(exc), "is_error": True, "widget": {"type": "memo", "error": str(exc)}}
    return {"result": "memo folder upserted", "is_error": False, "widget": {"type": "memo", "folder": folder}}


def _folder_key(data: dict[str, Any]) -> str:
    return str(data.get("folder_id") or data.get("id") or data.get("slug") or "").strip()
