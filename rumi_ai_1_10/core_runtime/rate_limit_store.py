"""
rate_limit_store.py - 永続化レート制限ストア

CapabilityExecutor の rate limit を SQLite に保存し、
プロセス再起動をまたいで制限状態を維持する。
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path


DEFAULT_RATE_LIMIT_DB = Path("user_data/security/rate_limits.db")


class PersistentRateLimitStore:
    """SQLite-backed fixed-window rate limiter."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(
            db_path or os.environ.get("RUMI_RATE_LIMIT_DB", str(DEFAULT_RATE_LIMIT_DB))
        )
        self._lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rate_limit_buckets (
                        principal_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        bucket_start INTEGER NOT NULL,
                        hit_count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (principal_id, scope, bucket_start)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_rate_limit_lookup
                    ON rate_limit_buckets(principal_id, scope, bucket_start)
                    """
                )
                conn.commit()
            self._initialized = True

    def allow(
        self,
        *,
        principal_id: str,
        scope: str,
        limit: int,
        window_seconds: float = 60.0,
        now: float | None = None,
    ) -> bool:
        """現在の time bucket が制限未満なら記録し True を返す。"""
        self._ensure_initialized()
        current = time.time() if now is None else now
        bucket_size = max(int(window_seconds), 1)
        bucket_start = int(current // bucket_size) * bucket_size
        stale_before = bucket_start - bucket_size

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM rate_limit_buckets WHERE bucket_start <= ?",
                    (stale_before,),
                )
                row = conn.execute(
                    """
                    SELECT hit_count
                    FROM rate_limit_buckets
                    WHERE principal_id = ? AND scope = ? AND bucket_start = ?
                    """,
                    (principal_id, scope, bucket_start),
                ).fetchone()
                hit_count = int(row[0]) if row else 0
                if hit_count >= limit:
                    conn.commit()
                    return False
                conn.execute(
                    """
                    INSERT INTO rate_limit_buckets(principal_id, scope, bucket_start, hit_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(principal_id, scope, bucket_start)
                    DO UPDATE SET hit_count = hit_count + 1
                    """,
                    (principal_id, scope, bucket_start),
                )
                conn.commit()
                return True
