from __future__ import annotations

from typing import Any

from blocks._common import error
from blocks.memory import memo_folders, memo_notes


def run(input_data: dict[str, Any], context: Any = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    resource = str(data.get("resource") or data.get("type") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()
    if resource in {"folder", "folders", "memo_folder", "memo_folders"}:
        return memo_folders.run(data, context)
    if resource in {"note", "notes", "memo_note", "memo_notes"}:
        return memo_notes.run(data, context)
    if action in {"create_folder", "list_folders", "get_folder", "update_folder", "delete_folder"}:
        next_data = dict(data)
        next_data["action"] = action.removesuffix("_folder").replace("list_folders", "list")
        return memo_folders.run(next_data, context)
    if action in {"create_note", "add_note", "write_note", "list_notes", "search_notes", "get_note", "update_note", "delete_note"}:
        next_data = dict(data)
        next_data["action"] = (
            action.removesuffix("_note")
            .removesuffix("_notes")
            .replace("add", "create")
            .replace("write", "create")
        )
        return memo_notes.run(next_data, context)
    return error("resource must be folders or notes", "INVALID_INPUT")
