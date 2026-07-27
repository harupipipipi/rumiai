"""Durable Host-owned idempotency ledger for repository context runs."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from .paths import USER_DATA_DIR
from .runtime_state import sqlite_wal_connection

_RUNNING_TTL_SECONDS = 15 * 60
_COMPLETED_TTL_SECONDS = 7 * 24 * 60 * 60
_MAX_ROWS_PER_PROFILE = 4096


class RepositoryContextLedgerError(RuntimeError):
    """Base error for durable repository-context reservations."""


class RepositoryContextLedgerConflict(RepositoryContextLedgerError):
    """An idempotency key was reused with different bound content."""


class RepositoryContextLedgerInProgress(RepositoryContextLedgerError):
    """An equivalent invocation is already running."""


class RepositoryContextLedger:
    """Reserve and complete bounded profile-scoped repository invocations."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else (
            Path(USER_DATA_DIR)
            / "database"
            / "repository_context_idempotency.sqlite3"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def reserve(
        self,
        *,
        profile_id: str,
        key: str,
        digest: str,
    ) -> dict[str, Any] | None:
        now = time.time()
        with sqlite_wal_connection(self.path) as connection:
            self._migrate(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._prune(connection, profile_id, now)
            row = connection.execute(
                """
                SELECT digest, status, result_json, updated_at
                FROM repository_context_invocations
                WHERE profile_id = ? AND invocation_key = ?
                """,
                (profile_id, key),
            ).fetchone()
            if row is not None:
                if str(row["digest"]) != digest:
                    connection.rollback()
                    raise RepositoryContextLedgerConflict(
                        "idempotency key conflicts with different content"
                    )
                if str(row["status"]) == "completed":
                    result = json.loads(str(row["result_json"] or "{}"))
                    connection.commit()
                    return result if isinstance(result, dict) else {}
                if now - float(row["updated_at"] or 0) <= _RUNNING_TTL_SECONDS:
                    connection.rollback()
                    raise RepositoryContextLedgerInProgress(
                        "repository context invocation is already in progress"
                    )
                connection.execute(
                    """
                    UPDATE repository_context_invocations
                    SET updated_at = ?, result_json = NULL
                    WHERE profile_id = ? AND invocation_key = ?
                    """,
                    (now, profile_id, key),
                )
                connection.commit()
                return None
            connection.execute(
                """
                INSERT INTO repository_context_invocations(
                    profile_id, invocation_key, digest, status,
                    result_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'running', NULL, ?, ?)
                """,
                (profile_id, key, digest, now, now),
            )
            connection.commit()
        return None

    def complete(
        self,
        *,
        profile_id: str,
        key: str,
        digest: str,
        result: Mapping[str, Any],
    ) -> None:
        encoded = json.dumps(
            dict(result),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with sqlite_wal_connection(self.path) as connection:
            self._migrate(connection)
            cursor = connection.execute(
                """
                UPDATE repository_context_invocations
                SET status = 'completed', result_json = ?, updated_at = ?
                WHERE profile_id = ? AND invocation_key = ? AND digest = ?
                """,
                (encoded, time.time(), profile_id, key, digest),
            )
            if cursor.rowcount != 1:
                raise RepositoryContextLedgerConflict(
                    "idempotency reservation changed before completion"
                )

    def abandon(
        self,
        *,
        profile_id: str,
        key: str,
        digest: str,
    ) -> None:
        with sqlite_wal_connection(self.path) as connection:
            self._migrate(connection)
            connection.execute(
                """
                DELETE FROM repository_context_invocations
                WHERE profile_id = ? AND invocation_key = ?
                  AND digest = ? AND status = 'running'
                """,
                (profile_id, key, digest),
            )

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS repository_context_invocations(
                profile_id TEXT NOT NULL,
                invocation_key TEXT NOT NULL,
                digest TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(profile_id, invocation_key)
            )
            """
        )

    @staticmethod
    def _prune(
        connection: sqlite3.Connection,
        profile_id: str,
        now: float,
    ) -> None:
        connection.execute(
            """
            DELETE FROM repository_context_invocations
            WHERE profile_id = ? AND (
                (status = 'running' AND updated_at < ?)
                OR (status = 'completed' AND updated_at < ?)
            )
            """,
            (
                profile_id,
                now - _RUNNING_TTL_SECONDS,
                now - _COMPLETED_TTL_SECONDS,
            ),
        )
        connection.execute(
            """
            DELETE FROM repository_context_invocations
            WHERE profile_id = ? AND rowid NOT IN (
                SELECT rowid FROM repository_context_invocations
                WHERE profile_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            )
            """,
            (profile_id, profile_id, _MAX_ROWS_PER_PROFILE),
        )
