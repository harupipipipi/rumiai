from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List


class DefaultsMigrator:
    def __init__(self, source_root: Path, target_root: Path) -> None:
        self.source_root = Path(source_root)
        self.target_root = Path(target_root)

    def status(self) -> Dict[str, Any]:
        return {"source_root": str(self.source_root), "target_root": str(self.target_root)}

    def _migrate_user_csv(self) -> Dict[str, Any]:
        src = self.source_root / "userdata" / "user.csv"
        if not src.is_file():
            return {"skipped": True, "reason": "user.csv not found"}
        dst_dir = self.target_root / "userdata"
        dst_dir.mkdir(parents=True, exist_ok=True)
        rows: List[Dict[str, Any]] = []
        with src.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append({key: value for key, value in row.items() if key})
        dst = dst_dir / "user.json"
        dst.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"migrated": True, "source": str(src), "target": str(dst)}

    def migrate_all(self) -> Dict[str, Any]:
        steps = [self._migrate_user_csv()]
        success = all(step.get("migrated") or step.get("skipped") for step in steps)
        return {"success": success, "steps": steps}
