"""
store_migration.py - JSON → SQLite 自動マイグレーション

StoreRegistry 初期化時に stores.db が存在せず、
JSON ディレクトリ（index.json）が存在する場合に自動実行される。

stores.db.tmp に書き込み → os.replace で atomic rename。
JSON ファイルは削除しない（ロールバック用）。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """マイグレーション用 DB に PRAGMA を設定する。"""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -8000")


def _create_tables(conn: sqlite3.Connection) -> None:
    """テーブルを作成する。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stores (
            store_id   TEXT PRIMARY KEY,
            root_path  TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS store_data (
            store_id   TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            value_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (store_id, key)
        );
    """)


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cleanup_stale_tmp(db_path: Path) -> None:
    """
    起動時に stores.db.tmp が残っていたら削除する。

    前回のマイグレーションが中断した残骸を除去する。
    """
    tmp_path = Path(str(db_path) + ".tmp")
    if tmp_path.exists():
        try:
            tmp_path.unlink()
            logger.info("Removed stale migration temp file: %s", tmp_path)
        except OSError as e:
            logger.warning("Failed to remove stale temp file %s: %s", tmp_path, e)


def migrate_json_to_sqlite(
    db_path: Path,
    index_path: Path,
) -> bool:
    """
    JSON ファイルから SQLite DB へマイグレーションする。

    Args:
        db_path: 出力先 SQLite DB パス (e.g. user_data/stores/stores.db)
        index_path: index.json のパス (e.g. user_data/stores/index.json)

    Returns:
        True: マイグレーション成功, False: スキップまたは失敗
    """
    if db_path.exists():
        logger.debug("SQLite DB already exists, skipping migration: %s", db_path)
        return False

    if not index_path.exists():
        logger.debug("No index.json found, skipping migration: %s", index_path)
        return False

    # _normalize_value_hash を遅延インポート（循環インポート回避）
    from .store_registry import _normalize_value_hash

    tmp_path = Path(str(db_path) + ".tmp")
    logger.info("Starting JSON → SQLite migration: %s → %s", index_path, db_path)

    conn: Optional[sqlite3.Connection] = None
    try:
        # index.json を読み込み
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        stores_dict: Dict[str, Dict[str, Any]] = index_data.get("stores", {})

        # tmp に書き込み
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(tmp_path))
        _apply_pragmas(conn)
        _create_tables(conn)

        now = _now_ts()
        migrated_stores = 0
        migrated_keys = 0

        for store_id, store_data in stores_dict.items():
            root_path = store_data.get("root_path", "")
            created_at = store_data.get("created_at", now)
            created_by = store_data.get("created_by", "")

            conn.execute(
                "INSERT OR IGNORE INTO stores (store_id, root_path, created_at, created_by) "
                "VALUES (?, ?, ?, ?)",
                (store_id, root_path, created_at, created_by),
            )
            migrated_stores += 1

            # 個別データファイルを移行
            store_root = Path(root_path)
            if store_root.is_dir():
                for json_file in sorted(store_root.rglob("*.json")):
                    if not json_file.is_file():
                        continue
                    # .lock / .cas_tmp ファイルはスキップ
                    if json_file.suffix != ".json":
                        continue
                    try:
                        rel = json_file.relative_to(store_root)
                    except ValueError:
                        continue
                    key = str(rel.with_suffix("")).replace("\\", "/")

                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            value_obj = json.load(f)
                    except (json.JSONDecodeError, OSError) as e:
                        logger.warning(
                            "Failed to read data file %s: %s", json_file, e
                        )
                        continue

                    canonical = json.dumps(
                        value_obj,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    value_hash = _normalize_value_hash(value_obj)

                    conn.execute(
                        "INSERT OR IGNORE INTO store_data "
                        "(store_id, key, value, value_hash, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (store_id, key, canonical, value_hash, now),
                    )
                    migrated_keys += 1

        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        conn = None

        # atomic rename
        os.replace(str(tmp_path), str(db_path))

        logger.info(
            "Migration complete: %d stores, %d keys migrated",
            migrated_stores,
            migrated_keys,
        )
        return True

    except Exception as e:
        logger.error("Migration failed: %s", e, exc_info=True)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        # tmp を削除（失敗した場合）
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return False
