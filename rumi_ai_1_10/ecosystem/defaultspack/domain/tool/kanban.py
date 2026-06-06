from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_COLUMNS = ("Backlog", "Doing", "Review", "Done")
DONE_COLUMN_TITLES = {"done", "complete", "completed", "closed"}


def _now_ms() -> int:
    return int(time.time() * 1000)


class KanbanController:
    """Small per-workspace Kanban/task-board store used by the tool runtime."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def run(self, arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or {}
        action = str(arguments.get("action") or "list").strip().lower()
        path = self._path(context)
        board = self._read(path)

        if action in {"configure", "configure_columns", "set_columns", "columns"}:
            board["columns"] = _normalize_columns(arguments.get("columns"))
            first_column_id = board["columns"][0]["id"]
            valid_column_ids = {column["id"] for column in board["columns"]}
            for card in board["cards"]:
                if card.get("column_id") not in valid_column_ids:
                    card["column_id"] = first_column_id
                    card["updated_at"] = _now_ms()
            _compact_positions(board["cards"], board["columns"])
            self._write(path, board)
            return self._result("configure", board, changed={"columns": board["columns"]})

        if action in {"create", "add"}:
            title = str(arguments.get("title") or arguments.get("task") or "").strip()
            if not title:
                raise ValueError("'title' is required for kanban.create")
            column_id = _resolve_column_id(arguments, board["columns"]) or board["columns"][0]["id"]
            now = _now_ms()
            card = {
                "id": str(uuid.uuid4()),
                "title": title,
                "column_id": column_id,
                "position": 0,
                "created_at": now,
                "updated_at": now,
                "notes": str(arguments.get("notes") or arguments.get("description") or ""),
                "priority": str(arguments.get("priority") or "normal"),
            }
            _copy_optional_card_fields(card, arguments)
            board["cards"].append(card)
            _place_card(board["cards"], card["id"], column_id, arguments.get("position"), board["columns"])
            self._write(path, board)
            return self._result("create", board, changed=card)

        if action in {"update", "edit"}:
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            for key in ("title", "notes", "priority", "assignee", "due_at"):
                if key in arguments and arguments[key] is not None:
                    card[key] = str(arguments[key])
            if "description" in arguments and "notes" not in arguments and arguments["description"] is not None:
                card["notes"] = str(arguments["description"])
            _copy_optional_card_fields(card, arguments)
            next_column_id = _resolve_column_id(arguments, board["columns"])
            if next_column_id is not None or "position" in arguments:
                _place_card(
                    board["cards"],
                    str(card["id"]),
                    next_column_id or str(card.get("column_id") or board["columns"][0]["id"]),
                    arguments.get("position"),
                    board["columns"],
                )
            card["updated_at"] = _now_ms()
            _compact_positions(board["cards"], board["columns"])
            self._write(path, board)
            return self._result("update", board, changed=card)

        if action == "move":
            card = _find_card(board["cards"], _card_id(arguments))
            if card is None:
                raise ValueError("card_id not found")
            column_id = _resolve_column_id(arguments, board["columns"], required=True)
            _place_card(board["cards"], str(card["id"]), column_id, arguments.get("position"), board["columns"])
            card["updated_at"] = _now_ms()
            self._write(path, board)
            return self._result("move", board, changed=card)

        if action in {"delete", "remove"}:
            card_id = _card_id(arguments)
            next_cards = [card for card in board["cards"] if card.get("id") != card_id]
            if len(next_cards) == len(board["cards"]):
                raise ValueError("card_id not found")
            board["cards"] = next_cards
            _compact_positions(board["cards"], board["columns"])
            self._write(path, board)
            return self._result("delete", board, changed={"id": card_id})

        if action == "clear":
            removed = len(board["cards"])
            board["cards"] = []
            self._write(path, board)
            return self._result("clear", board, changed={"cleared": removed})

        if action in {"list", "show"}:
            return self._result("list", board)

        raise ValueError(f"Unsupported kanban action: {action}")

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
        return root / "kanban.json"

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
        if changed and changed.get("title"):
            summary = f"{action}: {changed['title']}; {summary}"
        return {
            "action": action,
            "summary": summary,
            "columns": columns,
            "cards": cards,
            "changed": changed,
        }


def tool_kanban(arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = KanbanController().run(arguments, context if isinstance(context, dict) else {})
    return {
        "result": result.get("summary", "kanban updated"),
        "is_error": False,
        "widget": {"type": "kanban", **result},
    }


def _default_columns() -> list[dict[str, Any]]:
    return [
        {"id": _slugify(title), "title": title, "position": index, "done": _is_done_column_title(title)}
        for index, title in enumerate(DEFAULT_COLUMNS)
    ]


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
        if candidate == column["id"] or candidate.lower() == str(column.get("title") or "").strip().lower():
            return str(column["id"])
    raise ValueError(f"Unknown kanban column: {candidate}")


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
