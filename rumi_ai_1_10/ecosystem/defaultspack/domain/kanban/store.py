from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from core_runtime.runtime_state import run_migrations, sqlite_wal_connection

from .models import (
    DEFAULT_COLUMNS,
    KanbanNotFoundError,
    KanbanValidationError,
    clean_list,
    gen_id,
    is_done_column,
    json_dumps,
    json_loads,
    normalize_scope,
    now_ms,
    string_list,
)


def default_db_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_KANBAN_DB_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "kanban" / "kanban.db"


class KanbanStore:
    _instance: "KanbanStore | None" = None
    _class_lock = threading.RLock()

    def __new__(cls, db_path: str | Path | None = None):
        if db_path is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                return cls._instance
        inst = super().__new__(cls)
        inst._initialized = False
        return inst

    def __init__(self, db_path: str | Path | None = None) -> None:
        target = Path(db_path) if db_path is not None else default_db_path()
        if getattr(self, "_initialized", False) and getattr(self, "db_path", None) == target:
            return
        self.db_path = target
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._migrate_lock = threading.RLock()
        _ = self.conn
        self._initialized = True

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite_wal_connection(self.db_path)
            with self._migrate_lock:
                run_migrations(conn, [(1, self._migration_1)], table_name="kanban_migrations")
            self._local.conn = conn
        return conn

    @staticmethod
    def _migration_1(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kanban_boards(
              board_id TEXT PRIMARY KEY,
              scope_type TEXT NOT NULL,
              scope_id TEXT NOT NULL,
              title TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              UNIQUE(scope_type, scope_id)
            );
            CREATE TABLE IF NOT EXISTS kanban_columns(
              column_id TEXT PRIMARY KEY,
              board_id TEXT NOT NULL,
              title TEXT NOT NULL,
              position INTEGER NOT NULL,
              done INTEGER NOT NULL DEFAULT 0,
              wip_limit INTEGER,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kanban_cards(
              card_id TEXT PRIMARY KEY,
              board_id TEXT NOT NULL,
              column_id TEXT NOT NULL,
              position INTEGER NOT NULL,
              title TEXT NOT NULL,
              description TEXT,
              priority TEXT NOT NULL DEFAULT 'normal',
              assignee TEXT,
              due_at TEXT,
              source_type TEXT NOT NULL DEFAULT 'manual',
              source_id TEXT,
              conversation_id TEXT,
              workspace_id TEXT,
              company_id TEXT,
              agent_run_id TEXT,
              agent_session_id TEXT,
              agent_status TEXT,
              branch TEXT,
              pr_url TEXT,
              labels_json TEXT NOT NULL DEFAULT '[]',
              checklist_json TEXT NOT NULL DEFAULT '[]',
              depends_on_json TEXT NOT NULL DEFAULT '[]',
              blocked_by_json TEXT NOT NULL DEFAULT '[]',
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              archived_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS kanban_events(
              event_id TEXT PRIMARY KEY,
              board_id TEXT NOT NULL,
              card_id TEXT,
              event_type TEXT NOT NULL,
              actor_type TEXT NOT NULL DEFAULT 'user',
              actor_id TEXT,
              payload_json TEXT NOT NULL DEFAULT '{}',
              created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_kanban_boards_scope ON kanban_boards(scope_type, scope_id);
            CREATE INDEX IF NOT EXISTS idx_kanban_columns_board ON kanban_columns(board_id, position);
            CREATE INDEX IF NOT EXISTS idx_kanban_cards_board ON kanban_cards(board_id, archived_at, position);
            CREATE INDEX IF NOT EXISTS idx_kanban_cards_column ON kanban_cards(column_id, archived_at, position);
            CREATE INDEX IF NOT EXISTS idx_kanban_events_board ON kanban_events(board_id, created_at);
            """
        )

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            conn = self.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def get_or_create_board(self, scope_type: str, scope_id: str, *, title: str | None = None) -> dict[str, Any]:
        scope_type, scope_id = normalize_scope(scope_type, scope_id)
        now = now_ms()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO kanban_boards(board_id, scope_type, scope_id, title, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, '{}')
                ON CONFLICT(scope_type, scope_id) DO NOTHING
                """,
                (gen_id("kb_"), scope_type, scope_id, title or f"Kanban: {scope_id}", now, now),
            )
            row = conn.execute(
                "SELECT * FROM kanban_boards WHERE scope_type = ? AND scope_id = ?",
                (scope_type, scope_id),
            ).fetchone()
        if row is None:
            raise KanbanValidationError("failed to create board")
        board = self._board(row)
        self.ensure_default_columns(board["board_id"])
        return board

    def get_board(self, board_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM kanban_boards WHERE board_id = ?", (str(board_id),)).fetchone()
        return self._board(row) if row else None

    def get_board_by_scope(self, scope_type: str, scope_id: str) -> dict[str, Any] | None:
        scope_type, scope_id = normalize_scope(scope_type, scope_id)
        row = self.conn.execute(
            "SELECT * FROM kanban_boards WHERE scope_type = ? AND scope_id = ?",
            (scope_type, scope_id),
        ).fetchone()
        return self._board(row) if row else None

    def require_board(self, board_id: str) -> dict[str, Any]:
        board = self.get_board(board_id)
        if board is None:
            raise KanbanNotFoundError("board not found: " + str(board_id))
        return board

    def list_boards(self, *, scope_type: str | None = None, scope_id: str | None = None) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if scope_type:
            where.append("scope_type = ?")
            params.append(str(scope_type).strip().lower())
        if scope_id:
            where.append("scope_id = ?")
            params.append(str(scope_id).strip())
        query = "SELECT * FROM kanban_boards"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY updated_at DESC"
        return [self._board(row) for row in self.conn.execute(query, params).fetchall()]

    def update_board(self, board_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        board = self.require_board(board_id)
        title = str(updates.get("title") or board["title"]).strip()
        metadata = updates.get("metadata") if isinstance(updates.get("metadata"), dict) else board["metadata"]
        with self.tx() as conn:
            conn.execute(
                "UPDATE kanban_boards SET title = ?, metadata_json = ?, updated_at = ? WHERE board_id = ?",
                (title, json_dumps(metadata), now_ms(), board["board_id"]),
            )
            self._event_tx(conn, board["board_id"], None, "board.updated", {"updates": updates})
        return self.require_board(board_id)

    def ensure_default_columns(self, board_id: str) -> list[dict[str, Any]]:
        columns = self.list_columns(board_id)
        if columns:
            return columns
        now = now_ms()
        with self.tx() as conn:
            for position, title in enumerate(DEFAULT_COLUMNS):
                conn.execute(
                    """
                    INSERT INTO kanban_columns(column_id, board_id, title, position, done, wip_limit, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (gen_id("kcol_"), board_id, title, position, 1 if is_done_column(title) else 0, now, now),
                )
            self._event_tx(conn, board_id, None, "board.bootstrap", {})
        return self.list_columns(board_id)

    def list_columns(self, board_id: str) -> list[dict[str, Any]]:
        return [
            self._column(row)
            for row in self.conn.execute(
                "SELECT * FROM kanban_columns WHERE board_id = ? ORDER BY position ASC, created_at ASC",
                (str(board_id),),
            ).fetchall()
        ]

    def create_column(self, board_id: str, title: str, *, position: int | None = None, done: bool | None = None) -> dict[str, Any]:
        self.require_board(board_id)
        title = str(title or "").strip()
        if not title:
            raise KanbanValidationError("title is required")
        columns = self.list_columns(board_id)
        position = len(columns) if position is None else max(0, min(int(position), len(columns)))
        now = now_ms()
        column_id = gen_id("kcol_")
        with self.tx() as conn:
            conn.execute("UPDATE kanban_columns SET position = position + 1 WHERE board_id = ? AND position >= ?", (board_id, position))
            conn.execute(
                """
                INSERT INTO kanban_columns(column_id, board_id, title, position, done, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (column_id, board_id, title, position, 1 if (is_done_column(title) if done is None else done) else 0, now, now),
            )
            self._compact_columns_tx(conn, board_id)
            self._event_tx(conn, board_id, None, "column.created", {"column_id": column_id})
        return self.require_column(column_id)

    def require_column(self, column_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM kanban_columns WHERE column_id = ?", (str(column_id),)).fetchone()
        if row is None:
            raise KanbanNotFoundError("column not found: " + str(column_id))
        return self._column(row)

    def update_column(self, column_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        column = self.require_column(column_id)
        title = str(updates.get("title") or column["title"]).strip()
        done = bool(updates["done"]) if "done" in updates else bool(column["done"])
        position = updates.get("position")
        with self.tx() as conn:
            conn.execute(
                "UPDATE kanban_columns SET title = ?, done = ?, wip_limit = ?, updated_at = ? WHERE column_id = ?",
                (title, 1 if done else 0, updates.get("wip_limit", column.get("wip_limit")), now_ms(), column_id),
            )
            if position is not None:
                self._move_column_tx(conn, column, int(position))
            self._event_tx(conn, column["board_id"], None, "column.updated", {"column_id": column_id, "updates": updates})
        return self.require_column(column_id)

    def delete_column(self, column_id: str) -> dict[str, Any]:
        column = self.require_column(column_id)
        columns = [item for item in self.list_columns(column["board_id"]) if item["column_id"] != column_id]
        if not columns:
            raise KanbanValidationError("cannot delete the last column")
        target = columns[0]
        with self.tx() as conn:
            conn.execute("UPDATE kanban_cards SET column_id = ?, updated_at = ? WHERE column_id = ?", (target["column_id"], now_ms(), column_id))
            conn.execute("DELETE FROM kanban_columns WHERE column_id = ?", (column_id,))
            self._compact_columns_tx(conn, column["board_id"])
            self._compact_cards_tx(conn, column["board_id"], target["column_id"])
            self._event_tx(conn, column["board_id"], None, "column.deleted", {"column_id": column_id})
        return column

    def create_card(self, board_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.require_board(board_id)
        title = str(payload.get("title") or "").strip()
        if not title:
            raise KanbanValidationError("title is required")
        column = self._resolve_column(board_id, payload.get("column_id") or payload.get("column"))
        card_id = gen_id("kcard_")
        now = now_ms()
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO kanban_cards(
                  card_id, board_id, column_id, position, title, description, priority, assignee, due_at,
                  source_type, source_id, conversation_id, workspace_id, company_id, agent_run_id,
                  agent_session_id, agent_status, branch, pr_url, labels_json, checklist_json,
                  depends_on_json, blocked_by_json, metadata_json, created_at, updated_at, archived_at
                ) VALUES (?, ?, ?, 999999, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    card_id,
                    board_id,
                    column["column_id"],
                    title,
                    _text(payload.get("description") if payload.get("description") is not None else payload.get("notes")),
                    str(payload.get("priority") or "normal"),
                    _text(payload.get("assignee")),
                    _text(payload.get("due_at")),
                    str(payload.get("source_type") or "manual"),
                    _text(payload.get("source_id")),
                    _text(payload.get("conversation_id")),
                    _text(payload.get("workspace_id")),
                    _text(payload.get("company_id")),
                    _text(payload.get("agent_run_id")),
                    _text(payload.get("agent_session_id")),
                    _text(payload.get("agent_status")),
                    _text(payload.get("branch")),
                    _text(payload.get("pr_url")),
                    json_dumps(string_list(payload.get("labels"))),
                    json_dumps(clean_list(payload.get("checklist"))),
                    json_dumps(string_list(payload.get("depends_on"))),
                    json_dumps(string_list(payload.get("blocked_by"))),
                    json_dumps(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                    now,
                    now,
                ),
            )
            self._place_card_tx(conn, card_id, column["column_id"], payload.get("position"), payload.get("before_card_id"), payload.get("after_card_id"))
            self._event_tx(conn, board_id, card_id, "card.created", {"card_id": card_id, "title": title})
        return self.require_card(card_id)

    def require_card(self, card_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM kanban_cards WHERE card_id = ?", (str(card_id),)).fetchone()
        if row is None:
            raise KanbanNotFoundError("card not found: " + str(card_id))
        return self._card(row)

    def update_card(self, card_id: str, updates: dict[str, Any], *, event_type: str = "card.updated") -> dict[str, Any]:
        card = self.require_card(card_id)
        merged = {**card, **updates}
        if "notes" in updates and "description" not in updates:
            merged["description"] = updates["notes"]
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE kanban_cards SET title = ?, description = ?, priority = ?, assignee = ?, due_at = ?,
                  source_type = ?, source_id = ?, conversation_id = ?, workspace_id = ?, company_id = ?,
                  agent_run_id = ?, agent_session_id = ?, agent_status = ?, branch = ?, pr_url = ?,
                  labels_json = ?, checklist_json = ?, depends_on_json = ?, blocked_by_json = ?,
                  metadata_json = ?, updated_at = ?, archived_at = ? WHERE card_id = ?
                """,
                (
                    str(merged.get("title") or "").strip(),
                    _text(merged.get("description")),
                    str(merged.get("priority") or "normal"),
                    _text(merged.get("assignee")),
                    _text(merged.get("due_at")),
                    str(merged.get("source_type") or "manual"),
                    _text(merged.get("source_id")),
                    _text(merged.get("conversation_id")),
                    _text(merged.get("workspace_id")),
                    _text(merged.get("company_id")),
                    _text(merged.get("agent_run_id")),
                    _text(merged.get("agent_session_id")),
                    _text(merged.get("agent_status")),
                    _text(merged.get("branch")),
                    _text(merged.get("pr_url")),
                    json_dumps(string_list(merged.get("labels"))),
                    json_dumps(clean_list(merged.get("checklist"))),
                    json_dumps(string_list(merged.get("depends_on"))),
                    json_dumps(string_list(merged.get("blocked_by"))),
                    json_dumps(merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}),
                    now_ms(),
                    merged.get("archived_at"),
                    card_id,
                ),
            )
            self._event_tx(conn, card["board_id"], card_id, event_type, {"updates": updates})
        return self.require_card(card_id)

    def move_card(self, card_id: str, payload: dict[str, Any], *, event_type: str = "card.moved") -> dict[str, Any]:
        card = self.require_card(card_id)
        column = self._resolve_column(card["board_id"], payload.get("column_id") or payload.get("target_column_id") or payload.get("column") or payload.get("status") or card["column_id"])
        with self.tx() as conn:
            self._place_card_tx(conn, card_id, column["column_id"], payload.get("position"), payload.get("before_card_id"), payload.get("after_card_id"))
            conn.execute("UPDATE kanban_cards SET updated_at = ? WHERE card_id = ?", (now_ms(), card_id))
            self._event_tx(conn, card["board_id"], card_id, event_type, {"from_column_id": card["column_id"], "to_column_id": column["column_id"]})
        return self.require_card(card_id)

    def delete_card(self, card_id: str) -> dict[str, Any]:
        card = self.require_card(card_id)
        with self.tx() as conn:
            conn.execute("DELETE FROM kanban_cards WHERE card_id = ?", (card_id,))
            self._compact_cards_tx(conn, card["board_id"], card["column_id"])
            self._event_tx(conn, card["board_id"], card_id, "card.deleted", {"card_id": card_id})
        return card

    def list_cards(self, board_id: str) -> list[dict[str, Any]]:
        return [
            self._card(row)
            for row in self.conn.execute(
                "SELECT * FROM kanban_cards WHERE board_id = ? AND archived_at IS NULL ORDER BY column_id, position, created_at",
                (str(board_id),),
            ).fetchall()
        ]

    def add_event(self, board_id: str, event_type: str, payload: dict[str, Any] | None = None, *, card_id: str | None = None) -> dict[str, Any]:
        self.require_board(board_id)
        with self.tx() as conn:
            event_id = self._event_tx(conn, board_id, card_id, event_type, payload or {})
        return self.require_event(event_id)

    def require_event(self, event_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM kanban_events WHERE event_id = ?", (str(event_id),)).fetchone()
        if row is None:
            raise KanbanNotFoundError("event not found: " + str(event_id))
        return self._event(row)

    def list_events(self, board_id: str, *, since: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        query = "SELECT * FROM kanban_events WHERE board_id = ?"
        params: list[Any] = [str(board_id)]
        if since is not None:
            query += " AND created_at > ?"
            params.append(int(since))
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        return [self._event(row) for row in self.conn.execute(query, params).fetchall()]

    def delete_event(self, event_id: str) -> dict[str, Any]:
        event = self.require_event(event_id)
        with self.tx() as conn:
            conn.execute("DELETE FROM kanban_events WHERE event_id = ?", (event_id,))
        return event

    def board_snapshot(self, board_id: str, *, include_events: bool = True) -> dict[str, Any]:
        board = self.require_board(board_id)
        columns = self.list_columns(board_id)
        order = {column["column_id"]: column["position"] for column in columns}
        cards = sorted(self.list_cards(board_id), key=lambda card: (order.get(card["column_id"], 9999), card["position"], card["created_at"]))
        result = {"board": board, "columns": columns, "cards": cards}
        if include_events:
            result["events"] = self.list_events(board_id)
        return result

    def _resolve_column(self, board_id: str, value: Any | None) -> dict[str, Any]:
        columns = self.list_columns(board_id)
        if not columns:
            raise KanbanValidationError("board has no columns")
        if value in (None, ""):
            return columns[0]
        candidate = str(value).strip()
        for column in columns:
            if candidate == column["column_id"] or candidate.lower() == column["title"].lower():
                return column
        raise KanbanValidationError("unknown column: " + candidate)

    def _place_card_tx(self, conn: sqlite3.Connection, card_id: str, column_id: str, position: Any, before: Any, after: Any) -> None:
        card = conn.execute("SELECT * FROM kanban_cards WHERE card_id = ?", (card_id,)).fetchone()
        rows = conn.execute(
            "SELECT card_id FROM kanban_cards WHERE board_id = ? AND column_id = ? AND archived_at IS NULL AND card_id != ? ORDER BY position, created_at",
            (card["board_id"], column_id, card_id),
        ).fetchall()
        ids = [row["card_id"] for row in rows]
        target = len(ids)
        if before and str(before) in ids:
            target = ids.index(str(before))
        elif after and str(after) in ids:
            target = ids.index(str(after)) + 1
        elif position is not None:
            target = max(0, min(int(position), len(ids)))
        ids.insert(target, card_id)
        now = now_ms()
        conn.execute("UPDATE kanban_cards SET column_id = ?, updated_at = ? WHERE card_id = ?", (column_id, now, card_id))
        for index, current_id in enumerate(ids):
            conn.execute("UPDATE kanban_cards SET position = ?, updated_at = ? WHERE card_id = ?", (index, now, current_id))
        if card["column_id"] != column_id:
            self._compact_cards_tx(conn, card["board_id"], card["column_id"])

    def _compact_cards_tx(self, conn: sqlite3.Connection, board_id: str, column_id: str) -> None:
        rows = conn.execute(
            "SELECT card_id FROM kanban_cards WHERE board_id = ? AND column_id = ? AND archived_at IS NULL ORDER BY position, created_at",
            (board_id, column_id),
        ).fetchall()
        for index, row in enumerate(rows):
            conn.execute("UPDATE kanban_cards SET position = ? WHERE card_id = ?", (index, row["card_id"]))

    def _compact_columns_tx(self, conn: sqlite3.Connection, board_id: str) -> None:
        rows = conn.execute("SELECT column_id FROM kanban_columns WHERE board_id = ? ORDER BY position, created_at", (board_id,)).fetchall()
        for index, row in enumerate(rows):
            conn.execute("UPDATE kanban_columns SET position = ? WHERE column_id = ?", (index, row["column_id"]))

    def _move_column_tx(self, conn: sqlite3.Connection, column: dict[str, Any], position: int) -> None:
        ids = [
            row["column_id"]
            for row in conn.execute(
                "SELECT column_id FROM kanban_columns WHERE board_id = ? AND column_id != ? ORDER BY position, created_at",
                (column["board_id"], column["column_id"]),
            ).fetchall()
        ]
        ids.insert(max(0, min(position, len(ids))), column["column_id"])
        for index, column_id in enumerate(ids):
            conn.execute("UPDATE kanban_columns SET position = ?, updated_at = ? WHERE column_id = ?", (index, now_ms(), column_id))

    def _event_tx(self, conn: sqlite3.Connection, board_id: str, card_id: str | None, event_type: str, payload: dict[str, Any]) -> str:
        event_id = gen_id("kevt_")
        conn.execute(
            "INSERT INTO kanban_events(event_id, board_id, card_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, board_id, card_id, event_type, json_dumps(payload), now_ms()),
        )
        return event_id

    @staticmethod
    def _board(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json_loads(data.pop("metadata_json", "{}"), {})
        return data

    @staticmethod
    def _column(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["done"] = bool(data["done"])
        return data

    @staticmethod
    def _card(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["labels"] = json_loads(data.pop("labels_json"), [])
        data["checklist"] = json_loads(data.pop("checklist_json"), [])
        data["depends_on"] = json_loads(data.pop("depends_on_json"), [])
        data["blocked_by"] = json_loads(data.pop("blocked_by_json"), [])
        data["metadata"] = json_loads(data.pop("metadata_json"), {})
        return data

    @staticmethod
    def _event(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json_loads(data.pop("payload_json"), {})
        return data


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
