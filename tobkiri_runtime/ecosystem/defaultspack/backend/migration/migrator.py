from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parents[4]
LEGACY_DEFAULTS_DIR = BASE_DIR / "ecosystem" / "defaults"
LEGACY_USER_CSV = BASE_DIR / "user_data" / "user.csv"
USER_JSON = BASE_DIR / "user_data" / "packs" / "defaultspack" / "user.json"


class DefaultsMigrator:
    def __init__(
        self,
        source_root: Path | None = None,
        target_root: Path | None = None,
        legacy_user_csv: Path | None = None,
        user_json: Path | None = None,
    ) -> None:
        self.source_root = Path(source_root or LEGACY_DEFAULTS_DIR)
        self.target_root = Path(target_root or (BASE_DIR / "user_data" / "packs" / "defaultspack"))
        self.legacy_user_csv = Path(legacy_user_csv or LEGACY_USER_CSV)
        self.user_json = Path(user_json or USER_JSON)

    def status(self) -> Dict[str, Any]:
        return {
            "source_root": str(self.source_root),
            "target_root": str(self.target_root),
            "legacy_defaults_present": self.source_root.exists(),
            "legacy_user_csv_present": self.legacy_user_csv.is_file(),
            "user_json_present": self.user_json.is_file(),
            "needs_user_migration": self.legacy_user_csv.is_file() and not self.user_json.is_file(),
        }

    def _migrate_user_csv(self) -> Dict[str, Any]:
        src = self.legacy_user_csv
        if not src.is_file():
            return {"skipped": True, "reason": "user.csv not found"}
        if self.user_json.is_file():
            return {"skipped": True, "reason": "user.json already exists"}

        text = src.read_text(encoding="utf-8").strip()
        if not text:
            return {"skipped": True, "reason": "user.csv empty"}

        rows = list(csv.reader(text.splitlines()))
        result: Dict[str, Any] = {}
        start_idx = 0
        if rows and len(rows[0]) >= 2 and rows[0][0].strip().lower() == "key":
            start_idx = 1
        for row in rows[start_idx:]:
            if len(row) >= 2 and row[0].strip():
                result[row[0].strip()] = row[1]

        self.user_json.parent.mkdir(parents=True, exist_ok=True)
        self.user_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"migrated": True, "source": str(src), "target": str(self.user_json)}

    def migrate_all(self) -> Dict[str, Any]:
        steps = [self._migrate_user_csv()]
        success = all(step.get("migrated") or step.get("skipped") for step in steps)
        return {"success": success, "steps": steps}


_global_migrator: DefaultsMigrator | None = None


def get_defaults_migrator() -> DefaultsMigrator:
    global _global_migrator
    if _global_migrator is None:
        _global_migrator = DefaultsMigrator()
    return _global_migrator
