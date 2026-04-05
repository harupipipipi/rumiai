"""migration module - Data migration from old defaults to new defaultspack."""
from __future__ import annotations
import csv, json, logging, os
from pathlib import Path
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

class MigrationManager:
    def __init__(self, old_data_dir: Optional[Path] = None, new_data_dir: Optional[Path] = None):
        self._old_dir = old_data_dir; self._new_dir = new_data_dir
        self._deprecation_log: List[Dict[str, Any]] = []; self._migration_results: Dict[str, Any] = {}
    def migrate_user_csv_to_json(self, csv_path: str, json_path: str) -> Dict[str, Any]:
        try:
            users = []
            with open(csv_path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f): users.append(dict(row))
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"users": users, "migrated_from": csv_path}, f, indent=2)
            r = {"success": True, "count": len(users), "output": json_path}
            self._migration_results["user_csv"] = r; return r
        except Exception as e: return {"success": False, "error": str(e)}
    def migrate_old_config(self, old_path: str, new_path: str) -> Dict[str, Any]:
        try:
            with open(old_path, "r", encoding="utf-8") as f: old_data = json.load(f)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump({"version": "2.0", "migrated_from": old_path, "settings": old_data}, f, indent=2)
            return {"success": True}
        except Exception as e: return {"success": False, "error": str(e)}
    def check_old_data(self) -> Dict[str, Any]:
        checks = {}
        if self._old_dir and self._old_dir.is_dir():
            for p in ["*.csv", "*.json", "*.yaml"]:
                checks[p] = [str(f) for f in self._old_dir.glob(p)]
        return checks
    def log_deprecation(self, feature: str, replacement: str, version: str = "2.0"):
        self._deprecation_log.append({"feature": feature, "replacement": replacement, "deprecated_since": version})
    def get_deprecation_log(self): return list(self._deprecation_log)
    def rollback(self): return {"status": "rollback_available", "results": self._migration_results}
    def run_full_migration(self): return {"checks": self.check_old_data(), "deprecations": self.get_deprecation_log()}
