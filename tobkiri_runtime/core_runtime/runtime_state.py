"""Persistence helpers shared by durable pack runtimes."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    return str(value)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=_json_default)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(target.parent),
        delete=False,
    ) as handle:
        handle.write(data)
        handle.write("\n")
        tmp_name = handle.name
    os.replace(tmp_name, target)


def append_jsonl(path: str | Path, entry: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=_json_default)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")


def read_tail_jsonl(path: str | Path, limit: int = 100) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file() or limit <= 0:
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
                if len(rows) > limit:
                    rows.pop(0)
    return rows


def sqlite_wal_connection(path: str | Path, *, timeout: float = 30.0) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=timeout, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout={}".format(int(timeout * 1000)))
    return conn


def run_migrations(
    conn: sqlite3.Connection,
    migrations: Iterable[tuple[int, Callable[[sqlite3.Connection], None]]],
    *,
    table_name: str = "schema_migrations",
) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {table_name} (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {
        int(row["version"])
        for row in conn.execute(f"SELECT version FROM {table_name}").fetchall()
    }
    for version, migrate in sorted(migrations, key=lambda item: item[0]):
        if version in applied:
            continue
        with conn:
            migrate(conn)
            conn.execute(
                f"INSERT INTO {table_name}(version, applied_at) VALUES (?, ?)",
                (version, _utc_now()),
            )


def execute_with_retry(
    operation: Callable[[], Any],
    *,
    attempts: int = 5,
    base_delay: float = 0.05,
) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            time.sleep(base_delay * (2**attempt))
    if last_error is not None:
        raise last_error
    return operation()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
