from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import secrets
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_approval_db_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_APPROVAL_DB_PATH")
    if override:
        return Path(override)
    return _pack_root() / "user_data" / "safety" / "approval.sqlite3"


def default_approval_secret_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_APPROVAL_SECRET_PATH")
    if override:
        return Path(override)
    return default_approval_db_path().with_name("approval_runtime_secret")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


class ApprovalStore:
    """SQLite-backed approval request and one-shot token ledger."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_approval_db_path()
        self._lock = threading.RLock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS approval_requests (
                        request_id TEXT PRIMARY KEY,
                        operation TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        args_hash TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        decision_at INTEGER
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS used_tokens (
                        jti TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        args_hash TEXT NOT NULL,
                        consumed_at INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            self._ready = True

    def save_request(self, request: Any) -> dict[str, Any]:
        self._ensure_schema()
        data = asdict(request) if is_dataclass(request) else dict(request)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approval_requests(
                    request_id, operation, risk_level, args_hash, details_json,
                    created_at, expires_at, status, decision_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    operation=excluded.operation,
                    risk_level=excluded.risk_level,
                    args_hash=excluded.args_hash,
                    details_json=excluded.details_json,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at,
                    status=excluded.status,
                    decision_at=excluded.decision_at
                """,
                (
                    data["request_id"],
                    data["operation"],
                    data["risk_level"],
                    data["args_hash"],
                    _json_dumps(data.get("details", {})),
                    int(data["created_at"]),
                    int(data["expires_at"]),
                    data.get("status", "pending"),
                    data.get("decision_at"),
                ),
            )
        return data

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?",
                (str(request_id),),
            ).fetchone()
        return self._row_to_request(row) if row is not None else None

    def update_request_status(self, request_id: str, status: str, *, decision_at: int | None = None) -> None:
        self._ensure_schema()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE approval_requests SET status = ?, decision_at = ? WHERE request_id = ?",
                (str(status), decision_at, str(request_id)),
            )

    def list_requests(self, *, status: str | None = None, include_expired: bool = True, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_schema()
        limit = max(1, min(500, int(limit or 100)))
        params: list[Any] = []
        where: list[str] = []
        if status:
            where.append("status = ?")
            params.append(str(status))
        if not include_expired:
            where.append("expires_at >= ?")
            params.append(int(time.time()))
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM approval_requests{clause} ORDER BY created_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [self._row_to_request(row) for row in rows]

    def mark_token_used(self, jti: str, request_id: str, operation: str, args_hash: str, *, consumed_at: int | None = None) -> bool:
        self._ensure_schema()
        consumed = int(consumed_at or time.time())
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO used_tokens(jti, request_id, operation, args_hash, consumed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(jti), str(request_id), str(operation), str(args_hash), consumed),
                )
            except sqlite3.IntegrityError:
                return False
            conn.execute(
                "UPDATE approval_requests SET status = ?, decision_at = ? WHERE request_id = ?",
                ("consumed", consumed, str(request_id)),
            )
        return True

    def is_token_used(self, jti: str) -> bool:
        self._ensure_schema()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT 1 FROM used_tokens WHERE jti = ?", (str(jti),)).fetchone()
        return row is not None

    def clear(self) -> None:
        self._ensure_schema()
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM used_tokens")
            conn.execute("DELETE FROM approval_requests")

    def get_metadata(self, key: str) -> str | None:
        self._ensure_schema()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value FROM metadata WHERE key = ?", (str(key),)).fetchone()
        return str(row["value"]) if row is not None else None

    def set_metadata(self, key: str, value: str) -> None:
        self._ensure_schema()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                (str(key), str(value)),
            )

    def get_or_create_runtime_secret(self) -> str:
        existing = self.get_metadata("runtime_secret")
        if existing:
            persist_runtime_secret_for_broker(existing)
            return existing
        # The isolated Viewer harness creates this owner-only file before
        # either the broker or Defaultspack starts.  Adopt it for a fresh
        # approval database so both processes verify the same one-shot tokens.
        # Existing database state remains authoritative for normal restarts.
        try:
            prepared = default_approval_secret_path().read_text(encoding="utf-8").strip()
        except OSError:
            prepared = ""
        if prepared:
            self.set_metadata("runtime_secret", prepared)
            persist_runtime_secret_for_broker(prepared)
            return prepared
        generated = secrets.token_urlsafe(32)
        self.set_metadata("runtime_secret", generated)
        persist_runtime_secret_for_broker(generated)
        return generated

    @staticmethod
    def _row_to_request(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "request_id": row["request_id"],
            "operation": row["operation"],
            "risk_level": row["risk_level"],
            "args_hash": row["args_hash"],
            "details": _json_loads(row["details_json"]),
            "created_at": int(row["created_at"]),
            "expires_at": int(row["expires_at"]),
            "status": row["status"],
            "decision_at": row["decision_at"],
        }


_STORE: ApprovalStore | None = None
_STORE_LOCK = threading.RLock()


def get_approval_store() -> ApprovalStore:
    global _STORE
    expected_path = default_approval_db_path()
    with _STORE_LOCK:
        if _STORE is None or _STORE.path != expected_path:
            _STORE = ApprovalStore(expected_path)
        return _STORE


def persist_runtime_secret_for_broker(secret: str) -> None:
    value = str(secret or "").strip()
    if not value:
        return
    try:
        path = default_approval_secret_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        pass
