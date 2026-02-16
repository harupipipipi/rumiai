"""
host_privilege_manager.py - ホスト特権操作管理

Dockerコンテナ外で実行が必要な特権操作を管理する。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


@dataclass
class PrivilegeResult:
    """特権操作結果"""
    success: bool
    data: Any = None
    error: Optional[str] = None


class HostPrivilegeManager:
    """ホスト特権操作管理"""
    
    def __init__(self):
        self._granted: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def grant(self, pack_id: str, privilege_id: str) -> PrivilegeResult:
        """特権を付与"""
        with self._lock:
            if pack_id not in self._granted:
                self._granted[pack_id] = set()
            self._granted[pack_id].add(privilege_id)
        return PrivilegeResult(success=True)
    
    def revoke(self, pack_id: str, privilege_id: str) -> PrivilegeResult:
        """特権を取り消し"""
        with self._lock:
            if pack_id in self._granted:
                self._granted[pack_id].discard(privilege_id)
        return PrivilegeResult(success=True)
    
    def revoke_all(self, pack_id: str) -> PrivilegeResult:
        """全特権を取り消し"""
        with self._lock:
            self._granted.pop(pack_id, None)
        return PrivilegeResult(success=True)
    
    def has_privilege(self, pack_id: str, privilege_id: str) -> bool:
        """特権があるかチェック"""
        with self._lock:
            return privilege_id in self._granted.get(pack_id, set())
    
    def execute(self, pack_id: str, privilege_id: str, params: Dict[str, Any]) -> PrivilegeResult:
        """特権操作を実行"""
        if not self.has_privilege(pack_id, privilege_id):
            return PrivilegeResult(success=False, error=f"Privilege not granted: {privilege_id}")
        
        return PrivilegeResult(success=True, data={"privilege_id": privilege_id, "pack_id": pack_id})
    
    def list_privileges(self) -> List[Dict[str, Any]]:
        """付与済み特権一覧"""
        with self._lock:
            return [
                {"pack_id": pack_id, "privileges": list(privs)}
                for pack_id, privs in self._granted.items()
            ]


# グローバル変数（後方互換のため残存。DI コンテナ優先）
_global_privilege_manager: Optional[HostPrivilegeManager] = None
_hpm_lock = threading.Lock()


def get_host_privilege_manager() -> HostPrivilegeManager:
    """
    グローバルな HostPrivilegeManager を取得する。

    DI コンテナ経由で遅延初期化・キャッシュされる。

    Returns:
        HostPrivilegeManager インスタンス
    """
    from .di_container import get_container
    return get_container().get("host_privilege_manager")


def initialize_host_privilege_manager() -> HostPrivilegeManager:
    """
    HostPrivilegeManager を初期化する。

    新しいインスタンスを生成し、DI コンテナのキャッシュを置き換える。

    Returns:
        初期化済み HostPrivilegeManager インスタンス
    """
    global _global_privilege_manager
    with _hpm_lock:
        _global_privilege_manager = HostPrivilegeManager()
    # DI コンテナのキャッシュも更新（_hpm_lock の外で実行してデッドロック回避）
    from .di_container import get_container
    get_container().set_instance("host_privilege_manager", _global_privilege_manager)
    return _global_privilege_manager
