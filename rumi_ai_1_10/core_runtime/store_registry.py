"""
store_registry.py - ストア定義・作成・列挙・削除

Store（共有領域）を管理する。
公式は "tool/chat/asset" の意味を一切解釈しない。

保存先: user_data/stores/index.json
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


STORES_INDEX_PATH = "user_data/stores/index.json"
STORES_BASE_DIR = Path("user_data/stores")


def _validate_store_path(root_path: str) -> Optional[str]:
    """
    root_path が STORES_BASE_DIR 配下であることを検証する。

    Returns:
        エラーメッセージ (問題がなければ None)
    """
    if ".." in str(root_path):
        return "root_path must not contain '..'"
    resolved = Path(root_path).resolve()
    base = STORES_BASE_DIR.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return f"root_path must be under {STORES_BASE_DIR}/"
    return None


@dataclass
class StoreDefinition:
    store_id: str
    root_path: str
    created_at: str
    created_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store_id": self.store_id,
            "root_path": self.root_path,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoreDefinition":
        return cls(
            store_id=data.get("store_id", ""),
            root_path=data.get("root_path", ""),
            created_at=data.get("created_at", ""),
            created_by=data.get("created_by", ""),
        )


@dataclass
class StoreResult:
    success: bool
    store_id: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "store_id": self.store_id,
            "error": self.error,
        }


class StoreRegistry:
    def __init__(self, index_path: Optional[str] = None):
        self._index_path = Path(index_path or STORES_INDEX_PATH)
        self._lock = threading.RLock()
        self._stores: Dict[str, StoreDefinition] = {}
        self._load()

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, sdata in data.get("stores", {}).items():
                self._stores[sid] = StoreDefinition.from_dict(sdata)
        except Exception:
            pass

    def _save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "stores": {sid: s.to_dict() for sid, s in self._stores.items()},
        }
        tmp = self._index_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self._index_path)

    def create_store(
        self,
        store_id: str,
        root_path: str,
        created_by: str = "api_user",
    ) -> StoreResult:
        if not store_id or not re.match(r'^[a-zA-Z0-9_-]{1,64}$', store_id):
            return StoreResult(
                success=False, store_id=store_id,
                error="store_id must match ^[a-zA-Z0-9_-]{1,64}$",
            )
        if not root_path:
            return StoreResult(
                success=False, store_id=store_id, error="root_path is required",
            )

        # パストラバーサル防止
        path_err = _validate_store_path(root_path)
        if path_err:
            return StoreResult(
                success=False, store_id=store_id, error=path_err,
            )

        with self._lock:
            if store_id in self._stores:
                return StoreResult(
                    success=False, store_id=store_id,
                    error=f"Store already exists: {store_id}",
                )
            rp = Path(root_path)
            try:
                rp.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return StoreResult(
                    success=False, store_id=store_id,
                    error=f"Failed to create root_path: {e}",
                )
            self._stores[store_id] = StoreDefinition(
                store_id=store_id,
                root_path=str(rp.resolve()),
                created_at=self._now_ts(),
                created_by=created_by,
            )
            self._save()
            self._audit("store_created", True, {
                "store_id": store_id, "root_path": str(rp.resolve()),
            })
            return StoreResult(success=True, store_id=store_id)


    def is_store_accessible(
        self,
        store_id: str,
        pack_id: str,
        allowed_store_ids: "Optional[List[str]]" = None,
    ) -> bool:
        """
        pack_id が store_id にアクセスできるか判定する。

        チェック順:
        1. allowed_store_ids (grant の config 由来) に含まれれば許可
        2. SharedStoreManager.is_sharing_approved() が True なら許可
        3. それ以外は拒否

        W2-A の get / set から呼び出されることを想定。
        """
        if allowed_store_ids is not None and store_id in allowed_store_ids:
            return True

        try:
            from .store_sharing_manager import get_shared_store_manager
            ssm = get_shared_store_manager()
            return ssm.is_sharing_approved(pack_id, store_id)
        except Exception:
            return False

    def list_stores(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._stores.values()]

    def get_store(self, store_id: str) -> Optional[StoreDefinition]:
        with self._lock:
            return self._stores.get(store_id)

    def delete_store(
        self,
        store_id: str,
        delete_files: bool = False,
    ) -> StoreResult:
        with self._lock:
            store = self._stores.get(store_id)
            if store is None:
                return StoreResult(
                    success=False, store_id=store_id,
                    error=f"Store not found: {store_id}",
                )

            # パストラバーサル防止（登録済みパスも再検証）
            path_err = _validate_store_path(store.root_path)
            if path_err:
                return StoreResult(
                    success=False, store_id=store_id, error=path_err,
                )

            if delete_files:
                try:
                    rp = Path(store.root_path)
                    if rp.exists():
                        shutil.rmtree(rp)
                except Exception as e:
                    return StoreResult(
                        success=False, store_id=store_id,
                        error=f"Failed to delete files: {e}",
                    )
            del self._stores[store_id]
            self._save()
            self._audit("store_deleted", True, {
                "store_id": store_id, "delete_files": delete_files,
            })
            return StoreResult(success=True, store_id=store_id)

    @staticmethod
    def _audit(event_type: str, success: bool, details: Dict[str, Any]) -> None:
        try:
            from .audit_logger import get_audit_logger
            get_audit_logger().log_system_event(
                event_type=event_type, success=success, details=details,
            )
        except Exception:
            pass


_global_store_registry: Optional[StoreRegistry] = None
_store_lock = threading.Lock()


def get_store_registry() -> StoreRegistry:
    global _global_store_registry
    if _global_store_registry is None:
        with _store_lock:
            if _global_store_registry is None:
                _global_store_registry = StoreRegistry()
    return _global_store_registry


def reset_store_registry(index_path: str = None) -> StoreRegistry:
    global _global_store_registry
    with _store_lock:
        _global_store_registry = StoreRegistry(index_path)
    return _global_store_registry
