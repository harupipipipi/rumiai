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

        rows = list(csv.reader(self.legacy_user_csv.read_text(encoding="utf-8").splitlines()))
        result: Dict[str, Any] = {}
        if rows and len(rows[0]) >= 2 and rows[0][0] != "key":
            for row in rows:
                if len(row) >= 2:
                    result[row[0]] = row[1]
        else:
            for row in rows[1:]:
                if len(row) >= 2:
                    result[row[0]] = row[1]

        self.user_json.parent.mkdir(parents=True, exist_ok=True)
        self.user_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"migrated": True, "target": str(self.user_json)}



_global_defaultspack_migration_manager: DefaultspackMigrationManager | None = None


def get_defaultspack_migration_manager() -> DefaultspackMigrationManager:
    global _global_defaultspack_migration_manager
    if _global_defaultspack_migration_manager is None:
        _global_defaultspack_migration_manager = DefaultspackMigrationManager()
    return _global_defaultspack_migration_manager
