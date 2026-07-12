from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from blocks._common import gen_id
from core_runtime.runtime_audit_helpers import redact_sensitive
from core_runtime.runtime_events import utc_now
from core_runtime.runtime_state import run_migrations, sqlite_wal_connection

from .models import MemoryEntry


def default_memory_dir() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_MEMORY2_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "memory"


class MemorySQLiteStore:
    _instance: "MemorySQLiteStore | None" = None

    def __new__(cls, db_path: str | Path | None = None):
        if db_path is None:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
        inst = super().__new__(cls)
        inst._initialized = False
        return inst

    def __init__(self, db_path: str | Path | None = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self.root = Path(db_path).parent if db_path is not None else default_memory_dir()
        self.db_path = Path(db_path) if db_path is not None else self.root / "state.db"
        self._local = threading.local()
        self._migrate_lock = threading.RLock()
        _ = self.conn
        self._initialized = True

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite_wal_connection(self.db_path)
            with self._migrate_lock:
                self._migrate(conn)
            self._local.conn = conn
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        run_migrations(conn, [(1, self._migration_1), (2, self._migration_2)], table_name="memory_migrations")

    @staticmethod
    def _migration_1(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_entries(
              id TEXT PRIMARY KEY,
              scope TEXT,
              agent_id TEXT,
              project_id TEXT,
              content TEXT,
              metadata_json TEXT,
              source TEXT,
              confidence REAL,
              created_at TEXT,
              updated_at TEXT,
              archived_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_entries(scope, updated_at);
            """
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                  content,
                  metadata,
                  content='memory_entries',
                  content_rowid='rowid'
                )
                """
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _migration_2(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memo_folders(
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              slug TEXT NOT NULL UNIQUE,
              description TEXT,
              metadata_json TEXT,
              created_at TEXT,
              updated_at TEXT,
              archived_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_memo_folders_slug ON memo_folders(slug);

            CREATE TABLE IF NOT EXISTS memo_notes(
              id TEXT PRIMARY KEY,
              folder_id TEXT NOT NULL,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              metadata_json TEXT,
              source TEXT,
              created_at TEXT,
              updated_at TEXT,
              archived_at TEXT,
              FOREIGN KEY(folder_id) REFERENCES memo_folders(id)
            );
            CREATE INDEX IF NOT EXISTS idx_memo_notes_folder ON memo_notes(folder_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_memo_notes_updated ON memo_notes(updated_at);
            """
        )
        now = utc_now()
        conn.execute(
            """
            INSERT INTO memo_folders(id, name, slug, description, metadata_json, created_at, updated_at, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                "personalization",
                "Personalization",
                "personalization",
                "Default folder for stable user preferences and personalization notes.",
                json.dumps({"default": True, "kind": "personalization"}, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )

    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        scope: str = "user",
        agent_id: str | None = None,
        project_id: str | None = None,
        source: str = "manual",
        confidence: float = 1.0,
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        entry = MemoryEntry(
            id=memory_id or gen_id("mem_"),
            scope=scope,
            agent_id=agent_id,
            project_id=project_id,
            content=str(redact_sensitive(content)),
            metadata=redact_sensitive(metadata or {}),
            source=source,
            confidence=float(confidence),
            created_at=now,
            updated_at=now,
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO memory_entries(
                  id, scope, agent_id, project_id, content, metadata_json, source,
                  confidence, created_at, updated_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  scope=excluded.scope,
                  agent_id=excluded.agent_id,
                  project_id=excluded.project_id,
                  content=excluded.content,
                  metadata_json=excluded.metadata_json,
                  source=excluded.source,
                  confidence=excluded.confidence,
                  updated_at=excluded.updated_at,
                  archived_at=excluded.archived_at
                """,
                (
                    entry.id,
                    entry.scope,
                    entry.agent_id,
                    entry.project_id,
                    entry.content,
                    json.dumps(entry.metadata, ensure_ascii=False, sort_keys=True),
                    entry.source,
                    entry.confidence,
                    entry.created_at,
                    entry.updated_at,
                    entry.archived_at,
                ),
        )
        return entry.to_dict()

    @staticmethod
    def json_dumps(value: Any) -> str:
        return json.dumps(redact_sensitive(value or {}), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def json_loads(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value or "{}"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def get(self, memory_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT rowid, * FROM memory_entries WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def update(self, memory_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get(memory_id)
        if not current:
            return None
        merged = dict(current)
        merged.update(updates or {})
        return self.add(
            merged["content"],
            merged.get("metadata", {}),
            scope=merged.get("scope", "user"),
            agent_id=merged.get("agent_id"),
            project_id=merged.get("project_id"),
            source=merged.get("source", "manual"),
            confidence=float(merged.get("confidence", 1.0)),
            memory_id=memory_id,
        )

    def delete(self, memory_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute(
                "UPDATE memory_entries SET archived_at = ?, updated_at = ? WHERE id = ? AND archived_at IS NULL",
                (utc_now(), utc_now(), memory_id),
            )
        return cur.rowcount > 0

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        scope: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ["archived_at IS NULL"]
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if agent_id:
            where.append("agent_id = ?")
            params.append(agent_id)
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        text = str(query or "").strip()
        if text:
            where.append("(content LIKE ? OR metadata_json LIKE ?)")
            needle = f"%{text}%"
            params.extend([needle, needle])
        sql = "SELECT rowid, * FROM memory_entries WHERE " + " AND ".join(where) + " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        results = [self._row_to_entry(row) for row in rows]
        for result in results:
            result["score"] = _score(text, result["content"])
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return results[:limit]

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        metadata = data.pop("metadata_json", "{}")
        try:
            data["metadata"] = json.loads(metadata)
        except json.JSONDecodeError:
            data["metadata"] = {}
        data.pop("rowid", None)
        return data


def _score(query: str, content: str) -> float:
    q = query.lower().strip()
    c = content.lower().strip()
    if not q:
        return 0.1
    if q == c:
        return 1.0
    if q in c:
        return round(len(q) / max(len(c), 1), 4)
    q_words = set(q.split())
    if not q_words:
        return 0.0
    c_words = set(c.split())
    return round(len(q_words & c_words) / len(q_words), 4)
