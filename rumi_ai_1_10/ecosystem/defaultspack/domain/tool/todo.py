from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


class TodoController:
    """Small per-conversation todo store used by the chat tool runtime."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def run(self, arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or {}
        action = str(arguments.get("action") or "list").strip().lower()
        path = self._path(context)
        todos = self._read(path)

        if action in {"add", "create"}:
            title = str(arguments.get("title") or arguments.get("task") or "").strip()
            if not title:
                raise ValueError("'title' is required for todo.add")
            todo = {
                "id": str(uuid.uuid4()),
                "title": title,
                "status": str(arguments.get("status") or "todo"),
                "priority": str(arguments.get("priority") or "normal"),
                "created_at": _now_ms(),
                "updated_at": _now_ms(),
                "notes": str(arguments.get("notes") or ""),
            }
            todos.append(todo)
            self._write(path, todos)
            return self._result("add", todos, changed=todo)

        if action in {"complete", "done"}:
            todo = self._find(todos, str(arguments.get("todo_id") or arguments.get("id") or ""))
            if todo is None:
                raise ValueError("todo_id not found")
            todo["status"] = "done"
            todo["updated_at"] = _now_ms()
            self._write(path, todos)
            return self._result("complete", todos, changed=todo)

        if action in {"update", "edit"}:
            todo = self._find(todos, str(arguments.get("todo_id") or arguments.get("id") or ""))
            if todo is None:
                raise ValueError("todo_id not found")
            for key in ("title", "status", "priority", "notes"):
                if key in arguments and arguments[key] is not None:
                    todo[key] = str(arguments[key])
            todo["updated_at"] = _now_ms()
            self._write(path, todos)
            return self._result("update", todos, changed=todo)

        if action in {"remove", "delete"}:
            todo_id = str(arguments.get("todo_id") or arguments.get("id") or "")
            next_todos = [todo for todo in todos if todo.get("id") != todo_id]
            if len(next_todos) == len(todos):
                raise ValueError("todo_id not found")
            self._write(path, next_todos)
            return self._result("remove", next_todos, changed={"id": todo_id})

        if action == "clear":
            self._write(path, [])
            return self._result("clear", [], changed={"cleared": len(todos)})

        if action in {"list", "show"}:
            return self._result("list", todos)

        raise ValueError(f"Unsupported todo action: {action}")

    def _path(self, context: dict[str, Any]) -> Path:
        if self._root is not None:
            root = self._root
        else:
            workspace = context.get("conversation_workspace_dir")
            if isinstance(workspace, str) and workspace:
                root = Path(workspace)
            else:
                root = Path(__file__).resolve().parents[2] / "user_data" / "shared"
        root.mkdir(parents=True, exist_ok=True)
        return root / "todos.json"

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(value, dict):
            value = value.get("todos", [])
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _write(path: Path, todos: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "updated_at": _now_ms(), "todos": todos}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _find(todos: list[dict[str, Any]], todo_id: str) -> dict[str, Any] | None:
        if not todo_id:
            return None
        for todo in todos:
            if todo.get("id") == todo_id:
                return todo
        return None

    @staticmethod
    def _result(action: str, todos: list[dict[str, Any]], changed: dict[str, Any] | None = None) -> dict[str, Any]:
        open_count = len([todo for todo in todos if todo.get("status") != "done"])
        summary = f"{len(todos)} todos ({open_count} open)"
        if changed and changed.get("title"):
            summary = f"{action}: {changed['title']}; {summary}"
        return {
            "action": action,
            "summary": summary,
            "todos": todos,
            "changed": changed,
        }
