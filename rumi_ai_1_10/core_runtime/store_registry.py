"""
store_registry.py - Store 定義管理
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


STORE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class StoreRegistry:
    DEFAULT_INDEX_FILE = "user_data/stores/index.json"

    def __init__(self, index_file: str = None, base_dir: str = None):
        self._index_path = Path(index_file) if index_file else Path(self.DEFAULT_INDEX_FILE)
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
        self._lock = threading.RLock()
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _load_index(self) -> Dict[str, Any]:
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self, data: Dict[str, Any]) -> None:
        self._index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_store(self, store_id: str, root_path: str, created_by: str = "system") -> Dict[str, Any]:
        if not store_id or not STORE_ID_REGEX.match(store_id):
            return {"success": False, "error": "invalid_store_id"}
        root = Path(root_path)
        if not root.is_absolute():
            root = (self._base_dir / root).resolve()
        else:
            root = root.resolve()
        try:
            root.relative_to(self._base_dir)
        except ValueError:
            return {"success": False, "error": "root_path_outside_base"}
        with self._lock:
            data = self._load_index()
            if store_id in data:
                return {"success": False, "error": "store_exists"}
            root.mkdir(parents=True, exist_ok=True)
            data[store_id] = {
                "root_path": str(root),
                "created_at": self._now_ts(),
                "created_by": created_by,
            }
            self._save_index(data)
        return {"success": True, "store_id": store_id, "root_path": str(root)}

    def list_stores(self) -> Dict[str, Any]:
        with self._lock:
            data = self._load_index()
            return {"stores": data, "count": len(data)}

    def delete_store(self, store_id: str) -> Dict[str, Any]:
        with self._lock:
            data = self._load_index()
            if store_id not in data:
                return {"success": False, "error": "store_not_found"}
            del data[store_id]
            self._save_index(data)
        return {"success": True, "store_id": store_id, "warning": "store_path_not_deleted"}

    def get_store_path(self, store_id: str) -> Optional[Path]:
        data = self._load_index()
        entry = data.get(store_id)
        if not entry:
            return None
        try:
            return Path(entry.get("root_path", "")).resolve()
        except Exception:
            return None


_global_store_registry: Optional[StoreRegistry] = None
_registry_lock = threading.Lock()


def get_store_registry() -> StoreRegistry:
    global _global_store_registry
    if _global_store_registry is None:
        with _registry_lock:
            if _global_store_registry is None:
                _global_store_registry = StoreRegistry()
    return _global_store_registry


def reset_store_registry(index_file: str = None, base_dir: str = None) -> StoreRegistry:
    global _global_store_registry
    with _registry_lock:
        _global_store_registry = StoreRegistry(index_file, base_dir)
    return _global_store_registry
