"""
defaultspack_migration.py - legacy defaults -> defaultspack compatibility helpers
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict

from .paths import BASE_DIR

LEGACY_DEFAULTS_DIR = BASE_DIR / "ecosystem" / "defaults"
LEGACY_USER_CSV = BASE_DIR / "user_data" / "user.csv"
USER_JSON = BASE_DIR / "user_data" / "user.json"


class DefaultspackMigrationManager:
    def __init__(
        self,
        legacy_defaults_dir: Path | None = None,
        legacy_user_csv: Path | None = None,
        user_json: Path | None = None,
    ) -> None:
        self.legacy_defaults_dir = Path(legacy_defaults_dir or LEGACY_DEFAULTS_DIR)
        self.legacy_user_csv = Path(legacy_user_csv or LEGACY_USER_CSV)
        self.user_json = Path(user_json or USER_JSON)

    def status(self) -> Dict[str, Any]:
        return {
            "legacy_defaults_present": self.legacy_defaults_dir.exists(),
            "legacy_user_csv_present": self.legacy_user_csv.is_file(),
            "user_json_present": self.user_json.is_file(),
            "needs_user_migration": self.legacy_user_csv.is_file() and not self.user_json.is_file(),
        }

    def migrate_user_csv(self) -> Dict[str, Any]:
        if not self.legacy_user_csv.is_file():
            return {"migrated": False, "reason": "user_csv_not_found"}
        if self.user_json.is_file():
            return {"migrated": False, "reason": "user_json_already_exists"}

        text = self.legacy_user_csv.read_text(encoding="utf-8").strip()
        if not text:
            return {"migrated": False, "reason": "user_csv_empty"}

        rows = list(csv.reader(text.splitlines()))
        result: Dict[str, Any] = {}
        start_idx = 0
        if rows and len(rows[0]) >= 2 and rows[0][0].strip().lower() == "key":
            start_idx = 1

        for row in rows[start_idx:]:
            if len(row) >= 2 and row[0].strip():
                result[row[0].strip()] = row[1]

        self.user_json.parent.mkdir(parents=True, exist_ok=True)
        self.user_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"migrated": True, "target": str(self.user_json)}



_global_defaultspack_migration_manager: DefaultspackMigrationManager | None = None


def get_defaultspack_migration_manager() -> DefaultspackMigrationManager:
    global _global_defaultspack_migration_manager
    if _global_defaultspack_migration_manager is None:
        _global_defaultspack_migration_manager = DefaultspackMigrationManager()
    return _global_defaultspack_migration_manager
