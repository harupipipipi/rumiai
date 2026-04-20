from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConversationMemory:
    def __init__(self, base_dir: Path) -> None:
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def write(self, key: str, value: Dict[str, Any]) -> None:
        self._path(key).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

    def read(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        q = (query or "").lower()
        results = []
        for path in self._dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(data, ensure_ascii=False).lower()
            if q in text:
                results.append({"key": path.stem, "value": data})
        return results[:limit]
