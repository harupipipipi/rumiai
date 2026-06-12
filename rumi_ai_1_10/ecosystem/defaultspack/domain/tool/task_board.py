from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from domain.kanban.models import gen_id, now_ms
from domain.kanban.service import KanbanService
from domain.kanban.store import KanbanStore


DEFAULT_COLUMNS = ("Backlog", "Doing", "Review", "Done")
DONE_COLUMN_TITLES = {"done", "complete", "completed", "closed"}


def _now_ms() -> int:
    return int(time.time() * 1000)


class TaskBoardController:
    """Task Board tool adapter backed by the first-class Kanban workspace store."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def run(self, arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or {}
        action = str(arguments.get("action") or "list").strip().lower()
        service = self._service(context)
        snapshot = self._snapshot(service, arguments, context)
        self._import_legacy_if_needed(service, snapshot, context)
        snapshot = service.get_board(snapshot["board"]["board_id"])
        board = _task_board_from_snapshot(snapshot)

        if action in {"configure", "configure_columns", "set_columns", "columns"}:
            columns = _normalize_columns(arguments.get("columns"))
            self._replace_columns(service, snapshot, columns)
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("configure", board, changed={"columns": board["columns"]})

        if action in {"create", "add"}:
            title = str(arguments.get("title") or arguments.get("task") or "").strip()
            if not title:
                raise ValueError("'title' is required for task_board.create")
            column_id = _kanban_column_id(
                board,
                _resolve_column_id(arguments, board["columns"]) or board["columns"][0]["id"],
            )
            payload = _card_create_payload(arguments, context, column_id)
            payload["title"] = title
            card = service.create_card(snapshot["board"]["board_id"], payload)
            if arguments.get("position") is not None:
                service.move_card(card["card_id"], {"column_id": card["column_id"], "position": arguments.get("position")})
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("create", board, changed=_find_card(board["cards"], card["card_id"]))

        if action in {"update", "edit"}:
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            updates = _card_update_payload(card, arguments)
            if updates:
                service.update_card(str(card["id"]), updates)
            next_column_id = _resolve_column_id(arguments, board["columns"])
            if next_column_id is not None or "position" in arguments:
                service.move_card(
                    str(card["id"]),
                    {
                        "column_id": _kanban_column_id(board, next_column_id or str(card.get("column_id") or board["columns"][0]["id"])),
                        "position": arguments.get("position"),
                    },
                )
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("update", board, changed=_find_card(board["cards"], str(card["id"])))

        if action in {"block", "unblock"}:
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            if action == "block":
                dependencies = _without_self(
                    _string_list(
                        arguments.get("depends_on")
                        if "depends_on" in arguments
                        else arguments.get("dependencies")
                    ),
                    str(card["id"]),
                )
                blockers = _string_list(
                    arguments.get("blocked_by")
                    if "blocked_by" in arguments
                    else arguments.get("blockers")
                )
                if blockers:
                    blockers = _without_self(blockers, str(card["id"]))
                elif dependencies:
                    blockers = list(dependencies)
                if dependencies:
                    updates = {"depends_on": dependencies}
                else:
                    updates = {}
                updates["blocked_by"] = blockers
                updates["metadata"] = _metadata_with_task_board_field(
                    card,
                    "blocker_reason",
                    str(arguments.get("blocker_reason") or arguments.get("reason") or ""),
                )
            else:
                updates = {
                    "blocked_by": [],
                    "metadata": _metadata_with_task_board_field(card, "blocker_reason", ""),
                }
            service.update_card(str(card["id"]), updates)
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result(action, board, changed=_find_card(board["cards"], str(card["id"])))

        if action in {"subtask_add", "add_subtask"}:
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            title = str(arguments.get("title") or arguments.get("task") or "").strip()
            if not title:
                raise ValueError("'title' is required for task_board.subtask_add")
            subtask = {
                "id": str(arguments.get("subtask_id") or uuid.uuid4()),
                "title": title,
                "done": False,
                "status": "todo",
                "created_at": _now_ms(),
                "updated_at": _now_ms(),
            }
            if arguments.get("assignee") is not None:
                subtask["assignee"] = str(arguments.get("assignee"))
            subtasks = _normalize_subtasks(card.get("subtasks")) + [subtask]
            service.update_card(str(card["id"]), {"checklist": subtasks})
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("subtask_add", board, changed=_find_card(board["cards"], str(card["id"])))

        if action in {"subtask_update", "subtask_complete", "subtask_remove", "remove_subtask"}:
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            subtasks = _normalize_subtasks(card.get("subtasks"))
            subtask_id = str(arguments.get("subtask_id") or arguments.get("task_id") or "").strip()
            subtask = _find_subtask(subtasks, subtask_id)
            if subtask is None:
                raise ValueError("subtask_id not found")
            if action in {"subtask_remove", "remove_subtask"}:
                subtasks = [item for item in subtasks if item.get("id") != subtask_id]
            else:
                for key in ("title", "assignee", "notes"):
                    if key in arguments and arguments[key] is not None:
                        subtask[key] = str(arguments[key])
                if action == "subtask_complete":
                    subtask["done"] = True
                    subtask["status"] = "done"
                    subtask["completed_at"] = _now_ms()
                elif "done" in arguments:
                    subtask["done"] = bool(arguments.get("done"))
                    subtask["status"] = "done" if subtask["done"] else str(arguments.get("status") or "todo")
                elif "status" in arguments and arguments["status"] is not None:
                    subtask["status"] = str(arguments["status"])
                    subtask["done"] = subtask["status"].lower() in {"done", "complete", "completed"}
                subtask["updated_at"] = _now_ms()
            service.update_card(str(card["id"]), {"checklist": subtasks})
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result(action, board, changed=_find_card(board["cards"], str(card["id"])))

        if action == "move":
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            column_id = _resolve_column_id(arguments, board["columns"], required=True)
            service.move_card(
                str(card["id"]),
                {"column_id": _kanban_column_id(board, column_id), "position": arguments.get("position")},
            )
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("move", board, changed=_find_card(board["cards"], str(card["id"])))

        if action in {"delete", "remove"}:
            card_id = _card_id(arguments)
            if _find_card(board["cards"], card_id) is None:
                raise ValueError("card_id not found")
            service.delete_card(card_id)
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("delete", board, changed={"id": card_id})

        if action == "clear":
            removed = len(board["cards"])
            for card in list(board["cards"]):
                service.delete_card(str(card["id"]))
            board = _task_board_from_snapshot(service.get_board(snapshot["board"]["board_id"]))
            return self._result("clear", board, changed={"cleared": removed})

        if action in {"list", "show"}:
            return self._result("list", board)

        raise ValueError(f"Unsupported task board action: {action}")

    def _service(self, context: dict[str, Any]) -> KanbanService:
        if self._root is not None:
            self._root.mkdir(parents=True, exist_ok=True)
            return KanbanService(KanbanStore(self._root / "kanban.db"))
        if not any(context.get(key) for key in ("workspace_id", "conversation_id", "company_id")):
            workspace = context.get("conversation_workspace_dir") or context.get("workspace_dir")
            if isinstance(workspace, str) and workspace:
                root = Path(workspace)
                root.mkdir(parents=True, exist_ok=True)
                return KanbanService(KanbanStore(root / "task_board_kanban.db"))
        return KanbanService()

    def _snapshot(
        self,
        service: KanbanService,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        board_id = str(arguments.get("board_id") or arguments.get("kanban_board_id") or "").strip()
        if board_id:
            return service.get_board(board_id)
        scope_type, scope_id = _scope(arguments, context)
        title = str(arguments.get("board_title") or "").strip() or None
        return service.bootstrap_board({"scope_type": scope_type, "scope_id": scope_id, "title": title})

    def _import_legacy_if_needed(
        self,
        service: KanbanService,
        snapshot: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        path = self._path(context)
        if not path.exists() or snapshot.get("cards"):
            return
        board = snapshot.get("board") if isinstance(snapshot.get("board"), dict) else {}
        metadata = dict(board.get("metadata") if isinstance(board.get("metadata"), dict) else {})
        if metadata.get("task_board_json_imported"):
            return
        legacy = self._read(path)
        if not legacy["cards"] and not legacy["columns"]:
            metadata["task_board_json_imported"] = str(path)
            service.update_board(str(board.get("board_id") or ""), {"metadata": metadata})
            return
        self._replace_columns(service, snapshot, legacy["columns"])
        imported_snapshot = _task_board_from_snapshot(service.get_board(str(board.get("board_id") or "")))
        column_map = {
            str(column.get("id") or ""): _kanban_column_id(imported_snapshot, str(column.get("id") or ""))
            for column in imported_snapshot["columns"]
        }
        id_map: dict[str, str] = {}
        imported_cards: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for card in _sorted_cards(legacy["cards"], legacy["columns"]):
            column_id = column_map.get(str(card.get("column_id") or "")) or imported_snapshot["columns"][0]["kanban_column_id"]
            payload = _card_create_payload({**card, "description": card.get("notes")}, context, column_id)
            payload["title"] = str(card.get("title") or "Untitled card")
            payload["depends_on"] = []
            payload["blocked_by"] = []
            payload_metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {})
            task_board_metadata = dict(payload_metadata.get("task_board") if isinstance(payload_metadata.get("task_board"), dict) else {})
            task_board_metadata["legacy_task_board_id"] = str(card.get("id") or "")
            payload_metadata["task_board"] = task_board_metadata
            payload["metadata"] = payload_metadata
            created = service.create_card(str(board.get("board_id") or ""), payload)
            if card.get("id"):
                id_map[str(card.get("id"))] = str(created["card_id"])
            imported_cards.append((card, created))
            if card.get("position") is not None:
                service.move_card(created["card_id"], {"column_id": created["column_id"], "position": card.get("position")})
        for legacy_card, created in imported_cards:
            relation_updates: dict[str, Any] = {}
            depends_on = [id_map.get(value, value) for value in _string_list(legacy_card.get("depends_on"))]
            blocked_by = [id_map.get(value, value) for value in _string_list(legacy_card.get("blocked_by"))]
            if depends_on:
                relation_updates["depends_on"] = _without_self(depends_on, str(created["card_id"]))
            if blocked_by:
                relation_updates["blocked_by"] = _without_self(blocked_by, str(created["card_id"]))
            if relation_updates:
                service.update_card(str(created["card_id"]), relation_updates)
        metadata["task_board_json_imported"] = str(path)
        service.update_board(str(board.get("board_id") or ""), {"metadata": metadata})

    @staticmethod
    def _replace_columns(
        service: KanbanService,
        snapshot: dict[str, Any],
        columns: list[dict[str, Any]],
    ) -> None:
        store = service.store
        board_id = str(snapshot["board"]["board_id"])
        old_columns = list(snapshot.get("columns") or [])
        old_cards = list(snapshot.get("cards") or [])
        old_slug_by_column = {
            str(column.get("column_id") or ""): _slugify(str(column.get("title") or ""))
            for column in old_columns
        }
        desired = _normalize_columns(columns)
        new_column_ids = [gen_id("kcol_") for _ in desired]
        slug_to_new_id = {
            str(column.get("id") or ""): new_column_ids[index]
            for index, column in enumerate(desired)
        }
        first_column_id = new_column_ids[0]
        created = now_ms()
        with store.tx() as conn:
            conn.execute("DELETE FROM kanban_columns WHERE board_id = ?", (board_id,))
            for index, column in enumerate(desired):
                conn.execute(
                    """
                    INSERT INTO kanban_columns(column_id, board_id, title, position, done, wip_limit, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        new_column_ids[index],
                        board_id,
                        str(column.get("title") or f"Column {index + 1}"),
                        index,
                        1 if column.get("done") else 0,
                        created,
                        created,
                    ),
                )
            for card in old_cards:
                old_slug = old_slug_by_column.get(str(card.get("column_id") or ""), "")
                target_column_id = slug_to_new_id.get(old_slug, first_column_id)
                conn.execute(
                    "UPDATE kanban_cards SET column_id = ?, updated_at = ? WHERE card_id = ?",
                    (target_column_id, created, str(card.get("card_id") or "")),
                )
            for column_id in new_column_ids:
                store._compact_cards_tx(conn, board_id, column_id)
            store._event_tx(conn, board_id, None, "task_board.columns_configured", {"columns": desired})

    def _path(self, context: dict[str, Any]) -> Path:
        if self._root is not None:
            root = self._root
        else:
            workspace = context.get("conversation_workspace_dir") or context.get("workspace_dir")
            if isinstance(workspace, str) and workspace:
                root = Path(workspace)
            else:
                root = Path(__file__).resolve().parents[2] / "user_data" / "shared"
        root.mkdir(parents=True, exist_ok=True)
        return root / "task_board.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"columns": _default_columns(), "cards": []}
        if not isinstance(value, dict):
            return {"columns": _default_columns(), "cards": []}
        return {
            "columns": _normalize_columns(value.get("columns")),
            "cards": _normalize_cards(value.get("cards")),
        }

    @staticmethod
    def _write(path: Path, board: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "updated_at": _now_ms(),
            "columns": board["columns"],
            "cards": board["cards"],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _result(action: str, board: dict[str, Any], changed: dict[str, Any] | None = None) -> dict[str, Any]:
        columns = _columns_with_cards(board)
        cards = _sorted_cards(board["cards"], board["columns"])
        done_ids = {
            column["id"]
            for column in board["columns"]
            if bool(column.get("done"))
        }
        open_count = len([card for card in cards if card.get("column_id") not in done_ids])
        summary = f"{len(cards)} cards across {len(board['columns'])} columns ({open_count} open)"
        relations = _relation_summary(cards)
        if relations["dependency_counts"]["cards_blocked"]:
            summary += f"; {relations['dependency_counts']['cards_blocked']} blocked"
        if relations["dependency_counts"]["total_dependencies"]:
            summary += f"; {relations['dependency_counts']['total_dependencies']} dependencies"
        if changed and changed.get("title"):
            summary = f"{action}: {changed['title']}; {summary}"
        return {
            "action": action,
            "summary": summary,
            "board_id": board.get("board_id"),
            "kanban_board_id": board.get("kanban_board_id"),
            "scope_type": board.get("scope_type"),
            "scope_id": board.get("scope_id"),
            "metadata": board.get("metadata") if isinstance(board.get("metadata"), dict) else {},
            "columns": columns,
            "cards": cards,
            "kanban": board.get("kanban"),
            "blocked_cards": relations["blocked_cards"],
            "dependency_counts": relations["dependency_counts"],
            "changed": changed,
        }


def tool_task_board(arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = TaskBoardController().run(arguments, context if isinstance(context, dict) else {})
    return {
        "result": result.get("summary", "task board updated"),
        "is_error": False,
        "widget": {"type": "task_board", **result},
    }


def _default_columns() -> list[dict[str, Any]]:
    return [
        {"id": _slugify(title), "title": title, "position": index, "done": _is_done_column_title(title)}
        for index, title in enumerate(DEFAULT_COLUMNS)
    ]


def _scope(arguments: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    explicit_scope = arguments.get("scope") if isinstance(arguments.get("scope"), dict) else {}
    scope_type = str(arguments.get("scope_type") or explicit_scope.get("type") or explicit_scope.get("scope_type") or "").strip().lower()
    scope_id = str(arguments.get("scope_id") or explicit_scope.get("id") or explicit_scope.get("scope_id") or "").strip()
    if scope_type and scope_id:
        return scope_type, scope_id
    workspace_id = str(arguments.get("workspace_id") or context.get("workspace_id") or "").strip()
    if workspace_id:
        return "workspace", workspace_id
    conversation_id = str(arguments.get("conversation_id") or context.get("conversation_id") or "").strip()
    if conversation_id:
        return "conversation", conversation_id
    company_id = str(arguments.get("company_id") or context.get("company_id") or "").strip()
    if company_id:
        return "company", company_id
    workspace = context.get("conversation_workspace_dir") or context.get("workspace_dir")
    if isinstance(workspace, str) and workspace.strip():
        try:
            return "workspace", str(Path(workspace).resolve())
        except Exception:
            return "workspace", workspace.strip()
    return "global", "default"


def _task_board_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    board_info = dict(snapshot.get("board") if isinstance(snapshot.get("board"), dict) else {})
    raw_columns = list(snapshot.get("columns") if isinstance(snapshot.get("columns"), list) else [])
    raw_cards = list(snapshot.get("cards") if isinstance(snapshot.get("cards"), list) else [])
    columns: list[dict[str, Any]] = []
    column_ids: dict[str, str] = {}
    seen_slugs: set[str] = set()
    for index, column in enumerate(sorted(raw_columns, key=lambda item: _int_or_default(item.get("position"), 0))):
        title = str(column.get("title") or f"Column {index + 1}").strip()
        compat_id = _unique_id(_slugify(title) or str(column.get("column_id") or f"column-{index + 1}"), seen_slugs)
        kanban_column_id = str(column.get("column_id") or compat_id)
        column_ids[kanban_column_id] = compat_id
        columns.append(
            {
                "id": compat_id,
                "title": title,
                "position": _int_or_default(column.get("position"), index),
                "done": bool(column.get("done")),
                "kanban_column_id": kanban_column_id,
                "wip_limit": column.get("wip_limit"),
                "cards": [],
            }
        )
    if not columns:
        columns = _default_columns()
        for column in columns:
            column["kanban_column_id"] = column["id"]
    fallback_column_id = columns[0]["id"]
    cards = [
        _task_card_from_kanban(card, column_ids.get(str(card.get("column_id") or ""), fallback_column_id))
        for card in raw_cards
        if isinstance(card, dict)
    ]
    board = {
        "board_id": board_info.get("board_id"),
        "kanban_board_id": board_info.get("board_id"),
        "scope_type": board_info.get("scope_type"),
        "scope_id": board_info.get("scope_id"),
        "title": board_info.get("title"),
        "metadata": board_info.get("metadata") if isinstance(board_info.get("metadata"), dict) else {},
        "columns": columns,
        "cards": _normalize_cards(cards),
        "kanban": {
            "board": board_info,
            "columns": raw_columns,
            "cards": raw_cards,
        },
    }
    board["columns"] = _columns_with_cards(board)
    return board


def _task_card_from_kanban(card: dict[str, Any], column_id: str) -> dict[str, Any]:
    metadata = dict(card.get("metadata") if isinstance(card.get("metadata"), dict) else {})
    task_board_meta = dict(metadata.get("task_board") if isinstance(metadata.get("task_board"), dict) else {})
    description = str(card.get("description") or "")
    checklist = _normalize_subtasks(card.get("checklist"))
    return {
        "id": str(card.get("card_id") or ""),
        "card_id": str(card.get("card_id") or ""),
        "kanban_card_id": str(card.get("card_id") or ""),
        "board_id": str(card.get("board_id") or ""),
        "kanban_board_id": str(card.get("board_id") or ""),
        "title": str(card.get("title") or ""),
        "column_id": column_id,
        "kanban_column_id": str(card.get("column_id") or ""),
        "position": _int_or_default(card.get("position"), 0),
        "created_at": _int_or_default(card.get("created_at"), _now_ms()),
        "updated_at": _int_or_default(card.get("updated_at"), _now_ms()),
        "notes": description,
        "description": description,
        "priority": str(card.get("priority") or "normal"),
        "assignee": card.get("assignee"),
        "due_at": card.get("due_at"),
        "labels": _string_list(card.get("labels")),
        "metadata": metadata,
        "depends_on": _without_self(_string_list(card.get("depends_on")), str(card.get("card_id") or "")),
        "blocked_by": _without_self(_string_list(card.get("blocked_by")), str(card.get("card_id") or "")),
        "blocker_reason": str(task_board_meta.get("blocker_reason") or metadata.get("blocker_reason") or ""),
        "subtasks": checklist,
        "checklist": checklist,
        "source_type": str(card.get("source_type") or "manual"),
        "source_id": card.get("source_id"),
        "conversation_id": card.get("conversation_id"),
        "workspace_id": card.get("workspace_id"),
        "company_id": card.get("company_id"),
        "agent_run_id": card.get("agent_run_id"),
        "agent_session_id": card.get("agent_session_id"),
        "agent_status": card.get("agent_status"),
        "branch": card.get("branch"),
        "pr_url": card.get("pr_url"),
    }


def _kanban_column_id(board: dict[str, Any], compat_id: str) -> str:
    candidate = str(compat_id or "").strip()
    for column in board.get("columns", []):
        if candidate == column.get("id") or candidate == column.get("kanban_column_id"):
            return str(column.get("kanban_column_id") or column.get("id") or candidate)
    raise ValueError(f"Unknown task board column: {candidate}")


def _card_create_payload(arguments: dict[str, Any], context: dict[str, Any], column_id: str) -> dict[str, Any]:
    metadata = dict(arguments.get("metadata") if isinstance(arguments.get("metadata"), dict) else {})
    task_board_meta = dict(metadata.get("task_board") if isinstance(metadata.get("task_board"), dict) else {})
    if "blocker_reason" in arguments or "reason" in arguments:
        task_board_meta["blocker_reason"] = str(arguments.get("blocker_reason") or arguments.get("reason") or "")
    if task_board_meta:
        metadata["task_board"] = task_board_meta
    return {
        "column_id": column_id,
        "position": arguments.get("position"),
        "description": str(arguments.get("notes") if arguments.get("notes") is not None else arguments.get("description") or ""),
        "priority": str(arguments.get("priority") or "normal"),
        "assignee": str(arguments.get("assignee")) if arguments.get("assignee") is not None else None,
        "due_at": str(arguments.get("due_at")) if arguments.get("due_at") is not None else None,
        "labels": arguments.get("labels"),
        "checklist": _normalize_subtasks(arguments.get("subtasks")),
        "depends_on": _without_self(
            _string_list(arguments.get("depends_on") if "depends_on" in arguments else arguments.get("dependencies")),
            str(arguments.get("card_id") or arguments.get("id") or ""),
        ),
        "blocked_by": _without_self(
            _string_list(arguments.get("blocked_by") if "blocked_by" in arguments else arguments.get("blockers")),
            str(arguments.get("card_id") or arguments.get("id") or ""),
        ),
        "metadata": metadata,
        "source_type": str(arguments.get("source_type") or "task_board"),
        "source_id": str(arguments.get("source_id")) if arguments.get("source_id") is not None else None,
        "conversation_id": _optional_context_string(arguments, context, "conversation_id"),
        "workspace_id": _optional_context_string(arguments, context, "workspace_id"),
        "company_id": _optional_context_string(arguments, context, "company_id"),
    }


def _card_update_payload(card: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "title" in arguments and arguments["title"] is not None:
        updates["title"] = str(arguments["title"])
    if "notes" in arguments and arguments["notes"] is not None:
        updates["description"] = str(arguments["notes"])
    if "description" in arguments and "notes" not in arguments and arguments["description"] is not None:
        updates["description"] = str(arguments["description"])
    for key in ("priority", "assignee", "due_at", "agent_run_id", "agent_session_id", "agent_status", "branch", "pr_url"):
        if key in arguments and arguments[key] is not None:
            updates[key] = str(arguments[key])
    if "labels" in arguments:
        updates["labels"] = _string_list(arguments.get("labels"))
    if "metadata" in arguments and isinstance(arguments.get("metadata"), dict):
        updates["metadata"] = arguments["metadata"]
        agent_session = arguments["metadata"].get("agent_session")
        if isinstance(agent_session, dict):
            session_id = str(agent_session.get("session_id") or "").strip()
            status = str(agent_session.get("status") or agent_session.get("terminal_state") or "").strip()
            if session_id and "agent_session_id" not in updates:
                updates["agent_session_id"] = session_id
            if status and "agent_status" not in updates:
                updates["agent_status"] = status
    if "depends_on" in arguments or "dependencies" in arguments:
        updates["depends_on"] = _without_self(
            _string_list(arguments.get("depends_on") if "depends_on" in arguments else arguments.get("dependencies")),
            str(card.get("id") or ""),
        )
    if "blocked_by" in arguments or "blockers" in arguments:
        updates["blocked_by"] = _without_self(
            _string_list(arguments.get("blocked_by") if "blocked_by" in arguments else arguments.get("blockers")),
            str(card.get("id") or ""),
        )
    if "blocker_reason" in arguments or "reason" in arguments:
        updates["metadata"] = _metadata_with_task_board_field(
            card,
            "blocker_reason",
            str(arguments.get("blocker_reason") or arguments.get("reason") or ""),
        )
    if "subtasks" in arguments:
        updates["checklist"] = _normalize_subtasks(arguments.get("subtasks"))
    return updates


def _metadata_with_task_board_field(card: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    metadata = dict(card.get("metadata") if isinstance(card.get("metadata"), dict) else {})
    task_board = dict(metadata.get("task_board") if isinstance(metadata.get("task_board"), dict) else {})
    task_board[key] = value
    metadata["task_board"] = task_board
    if key == "blocker_reason":
        metadata["blocker_reason"] = value
    return metadata


def _optional_context_string(arguments: dict[str, Any], context: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key) if arguments.get(key) is not None else context.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_columns(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        return _default_columns()
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or item.get("id") or "").strip()
            column_id = str(item.get("id") or item.get("column_id") or "").strip()
            has_explicit_done = item.get("done") is not None or item.get("is_done") is not None
            is_done = bool(
                item.get("done")
                if item.get("done") is not None
                else item.get("is_done")
            )
        else:
            title = str(item or "").strip()
            column_id = ""
            has_explicit_done = False
            is_done = False
        if not title:
            title = f"Column {index + 1}"
        if not has_explicit_done:
            is_done = _is_done_column_title(title)
        column_id = _unique_id(_slugify(column_id or title) or f"column-{index + 1}", seen)
        columns.append({"id": column_id, "title": title, "position": index, "done": is_done})
    return columns or _default_columns()


def _normalize_cards(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cards: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        card = dict(item)
        card_id = str(card.get("id") or "").strip()
        title = str(card.get("title") or "").strip()
        if not card_id or not title:
            continue
        card["id"] = card_id
        card["title"] = title
        card["column_id"] = str(card.get("column_id") or "backlog").strip()
        card["position"] = _int_or_default(card.get("position"), index)
        card["created_at"] = _int_or_default(card.get("created_at"), _now_ms())
        card["updated_at"] = _int_or_default(card.get("updated_at"), card["created_at"])
        card["depends_on"] = _without_self(_string_list(card.get("depends_on")), card["id"])
        card["blocked_by"] = _without_self(_string_list(card.get("blocked_by")), card["id"])
        card["blocker_reason"] = str(card.get("blocker_reason") or "")
        card["subtasks"] = _normalize_subtasks(card.get("subtasks"))
        cards.append(card)
    return cards


def _resolve_column_id(arguments: dict[str, Any], columns: list[dict[str, Any]], *, required: bool = False) -> str | None:
    raw = (
        arguments.get("column_id")
        or arguments.get("target_column_id")
        or arguments.get("column")
        or arguments.get("status")
    )
    if raw is None:
        if required:
            raise ValueError("column_id is required")
        return None
    candidate = str(raw).strip()
    for column in columns:
        if (
            candidate == column["id"]
            or candidate == str(column.get("kanban_column_id") or "")
            or candidate.lower() == str(column.get("title") or "").strip().lower()
        ):
            return str(column["id"])
    raise ValueError(f"Unknown task board column: {candidate}")


def _card_id(arguments: dict[str, Any]) -> str:
    return str(arguments.get("card_id") or arguments.get("id") or "").strip()


def _find_card(cards: list[dict[str, Any]], card_id: str) -> dict[str, Any] | None:
    if not card_id:
        return None
    for card in cards:
        if card.get("id") == card_id:
            return card
    return None


def _place_card(
    cards: list[dict[str, Any]],
    card_id: str,
    column_id: str,
    position: Any,
    columns: list[dict[str, Any]],
) -> None:
    target = _find_card(cards, card_id)
    if target is None:
        return
    target["column_id"] = column_id
    siblings = [card for card in cards if card.get("id") != card_id and card.get("column_id") == column_id]
    siblings = _sorted_cards(siblings, columns)
    target_position = len(siblings) if position is None else max(0, min(_int_or_default(position, len(siblings)), len(siblings)))
    ordered = [*siblings[:target_position], target, *siblings[target_position:]]
    for index, card in enumerate(ordered):
        card["position"] = index
    _compact_positions(cards, columns)


def _compact_positions(cards: list[dict[str, Any]], columns: list[dict[str, Any]]) -> None:
    valid_column_ids = {column["id"] for column in columns}
    fallback_column_id = columns[0]["id"]
    for card in cards:
        if card.get("column_id") not in valid_column_ids:
            card["column_id"] = fallback_column_id
    for column in columns:
        column_cards = _sorted_cards([card for card in cards if card.get("column_id") == column["id"]], columns)
        for index, card in enumerate(column_cards):
            card["position"] = index


def _columns_with_cards(board: dict[str, Any]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for column in sorted(board["columns"], key=lambda item: _int_or_default(item.get("position"), 0)):
        columns.append(
            {
                **column,
                "cards": _sorted_cards(
                    [card for card in board["cards"] if card.get("column_id") == column["id"]],
                    board["columns"],
                ),
            }
        )
    return columns


def _sorted_cards(cards: list[dict[str, Any]], columns: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    column_positions = {
        str(column.get("id") or ""): _int_or_default(column.get("position"), 0)
        for column in (columns or [])
    }
    return sorted(
        cards,
        key=lambda card: (
            column_positions.get(str(card.get("column_id") or ""), len(column_positions)),
            _int_or_default(card.get("position"), 0),
            _int_or_default(card.get("created_at"), 0),
            str(card.get("id") or ""),
        ),
    )


def _copy_optional_card_fields(card: dict[str, Any], arguments: dict[str, Any]) -> None:
    labels = arguments.get("labels")
    if isinstance(labels, list):
        card["labels"] = [str(label) for label in labels if str(label).strip()]
    elif isinstance(labels, str):
        card["labels"] = [label.strip()] if label.strip() else []
    metadata = arguments.get("metadata")
    if isinstance(metadata, dict):
        card["metadata"] = metadata
    if "depends_on" in arguments or "dependencies" in arguments:
        card["depends_on"] = _without_self(
            _string_list(arguments.get("depends_on") if "depends_on" in arguments else arguments.get("dependencies")),
            str(card.get("id") or ""),
        )
    if "blocked_by" in arguments or "blockers" in arguments:
        card["blocked_by"] = _without_self(
            _string_list(arguments.get("blocked_by") if "blocked_by" in arguments else arguments.get("blockers")),
            str(card.get("id") or ""),
        )
    if "blocker_reason" in arguments or "reason" in arguments:
        card["blocker_reason"] = str(arguments.get("blocker_reason") or arguments.get("reason") or "")
    if "subtasks" in arguments:
        card["subtasks"] = _normalize_subtasks(arguments.get("subtasks"))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _without_self(values: list[str], card_id: str) -> list[str]:
    return [value for value in values if value and value != card_id]


def _normalize_subtasks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    subtasks: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            title = item.strip()
            if not title:
                continue
            subtask = {"id": str(uuid.uuid4()), "title": title}
        elif isinstance(item, dict):
            subtask = dict(item)
            title = str(subtask.get("title") or subtask.get("task") or "").strip()
            if not title:
                continue
            subtask["title"] = title
            subtask["id"] = str(subtask.get("id") or subtask.get("subtask_id") or uuid.uuid4())
        else:
            continue
        done = bool(subtask.get("done")) or str(subtask.get("status") or "").lower() in {"done", "complete", "completed"}
        subtask["done"] = done
        subtask["status"] = "done" if done else str(subtask.get("status") or "todo")
        subtask["position"] = _int_or_default(subtask.get("position"), index)
        subtask["created_at"] = _int_or_default(subtask.get("created_at"), _now_ms())
        subtask["updated_at"] = _int_or_default(subtask.get("updated_at"), subtask["created_at"])
        subtasks.append(subtask)
    return sorted(subtasks, key=lambda item: (_int_or_default(item.get("position"), 0), str(item.get("id") or "")))


def _find_subtask(subtasks: list[dict[str, Any]], subtask_id: str) -> dict[str, Any] | None:
    if not subtask_id:
        return None
    for subtask in subtasks:
        if subtask.get("id") == subtask_id:
            return subtask
    return None


def _relation_summary(cards: list[dict[str, Any]]) -> dict[str, Any]:
    blocked_cards = []
    cards_with_dependencies = 0
    total_dependencies = 0
    total_blockers = 0
    open_subtasks = 0
    completed_subtasks = 0
    for card in cards:
        depends_on = _string_list(card.get("depends_on"))
        blocked_by = _string_list(card.get("blocked_by"))
        subtasks = _normalize_subtasks(card.get("subtasks"))
        if depends_on:
            cards_with_dependencies += 1
            total_dependencies += len(depends_on)
        if blocked_by or str(card.get("blocker_reason") or "").strip():
            total_blockers += len(blocked_by)
            blocked_cards.append(
                {
                    "id": card.get("id"),
                    "title": card.get("title"),
                    "blocked_by": blocked_by,
                    "blocker_reason": str(card.get("blocker_reason") or ""),
                }
            )
        for subtask in subtasks:
            if subtask.get("done"):
                completed_subtasks += 1
            else:
                open_subtasks += 1
    return {
        "blocked_cards": blocked_cards,
        "dependency_counts": {
            "cards_with_dependencies": cards_with_dependencies,
            "cards_blocked": len(blocked_cards),
            "total_dependencies": total_dependencies,
            "total_blockers": total_blockers,
            "open_subtasks": open_subtasks,
            "completed_subtasks": completed_subtasks,
        },
    }


def _is_done_column_title(value: str) -> bool:
    return _slugify(value) in DONE_COLUMN_TITLES


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    return slug.strip("-")


def _unique_id(value: str, seen: set[str]) -> str:
    candidate = value
    suffix = 2
    while candidate in seen:
        candidate = f"{value}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
