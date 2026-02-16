"""
permission_manager.py - コンポーネント権限管理


コンポーネントが権限をリクエスト・チェックするためのAPI。
非Dockerモードでは「permissive」モードで動作（自動許可）。
Dockerモードではsandbox_bridgeに委譲。


設計原則:
- 公式は具体的な権限名をハードコードしない（グループ名は設定可能）
- 安全側にデフォルト（permissiveモードは開発用）
- ecosystem側で権限ポリシーを登録可能

Agent 7-F 変更:
  G-1: pack.update パーミッション標準化 (check_permission)
"""


from __future__ import annotations


import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List




@dataclass
class PermissionRequest:
    """権限リクエスト記録"""
    permission: str
    component_id: str
    config: Dict[str, Any]
    reason: str
    requested_at: str
    status: str = "pending"  # pending, granted, denied
    expires_at: Optional[str] = None




class PermissionManager:
    """
    コンポーネント権限管理
    
    permissiveモード（デフォルト、Docker非使用時）:
      全ての権限リクエストを自動許可
    
    secureモード（Docker使用時）:
      sandbox_bridgeに委譲し、明示的な許可が必要
    
    Usage:
        pm = get_permission_manager()
        
        # 権限をリクエスト
        if pm.request("my_pack:tool:mytool", "file_read", 
                      {"directories": ["${mount:data.user}/mydata"]},
                      reason="設定を読み取るため"):
            # 許可された
            pass
        
        # 権限チェック
        if pm.has_permission("my_pack:tool:mytool", "file_read"):
            pass
        
        # G-1: リソース指定のパーミッションチェック
        if pm.check_permission("admin", "pack.update", "my_pack"):
            pass
    """
    
    def __init__(self, mode: str = "permissive"):
        """
        Args:
            mode: "permissive" (自動許可) or "secure" (明示的許可必要)
        """
        self._mode = mode
        self._pending_requests: List[PermissionRequest] = []
        self._granted: Dict[str, Dict[str, Any]] = {}  # component_id -> {permission -> config}
        self._lock = threading.Lock()
        self._sandbox_bridge = None
        
        # 権限グループ（ecosystem側で追加・変更可能）
        self._permission_groups: Dict[str, List[str]] = {}
        
        # 信頼関係
        self._trust_relationships: Dict[str, List[str]] = {}  # component_id -> [trusted_ids]
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def set_sandbox_bridge(self, bridge) -> None:
        """sandbox_bridgeを設定（secureモードに移行）"""
        self._sandbox_bridge = bridge
        if bridge is not None:
            self._mode = "secure"
    
    def set_mode(self, mode: str) -> None:
        """モードを設定"""
        if mode in ("permissive", "secure"):
            self._mode = mode
    
    def get_mode(self) -> str:
        """現在のモードを取得"""
        return self._mode
    
    # ===== G-1: リソース指定パーミッションチェック =====

    def check_permission(
        self,
        principal_id: str,
        permission_type: str,
        resource_id: str = "",
    ) -> bool:
        """
        リソースに対するパーミッションを判定する。

        pack.update パーミッション:
            approve 済みの Pack のみ更新可能。
            ApprovalManager から Pack の状態を取得し、
            APPROVED であれば True を返す。

        その他のパーミッション:
            has_permission(principal_id, permission_type) に委譲。

        Args:
            principal_id: 操作主体ID
            permission_type: パーミッションタイプ（例: "pack.update"）
            resource_id: 対象リソースID（例: pack_id）

        Returns:
            True: 許可 / False: 拒否
        """
        if permission_type == "pack.update":
            return self._check_pack_update_permission(principal_id, resource_id)

        return self.has_permission(principal_id, permission_type)

    def _check_pack_update_permission(
        self,
        principal_id: str,
        pack_id: str,
    ) -> bool:
        """
        pack.update パーミッションを判定する。

        デフォルト: APPROVED 状態の Pack のみ更新可能。
        permissive モードでは APPROVED チェックのみ（権限チェック省略）。
        secure モードでは権限チェックも実施。
        """
        # Pack が APPROVED かチェック
        try:
            from .approval_manager import get_approval_manager, PackStatus
            am = get_approval_manager()
            status = am.get_status(pack_id)
            if status is None:
                return False
            if status != PackStatus.APPROVED:
                return False
        except Exception:
            print(
                f"[PermissionManager] WARNING: Failed to check pack status for {pack_id}",
                file=sys.stderr,
            )
            return False

        # permissive モードでは APPROVED チェックだけで許可
        if self._mode == "permissive":
            return True

        # secure モードでは追加の権限チェック
        return self.has_permission(principal_id, "pack.update")

    # ===== 権限リクエスト・チェック =====
    
    def request(
        self,
        component_id: str,
        permission: str,
        config: Dict[str, Any] = None,
        reason: str = ""
    ) -> bool:
        """
        権限をリクエスト
        
        Args:
            component_id: フルコンポーネントID (pack:type:id)
            permission: 権限名 (例: "file_read", "network")
            config: 権限設定 (例: {"directories": [...], "domains": [...]})
            reason: 人間可読な理由
        
        Returns:
            True: 許可, False: 拒否またはペンディング
        """
        config = config or {}
        resolved_config = self.resolve_scope_variables(config)
        
        with self._lock:
            # 既に許可済みかチェック
            if self._is_granted_internal(component_id, permission):
                self._audit_log(component_id, permission, "check", resolved_config, True)
                return True
            
            # permissiveモードでは自動許可
            if self._mode == "permissive":
                self._granted.setdefault(component_id, {})[permission] = resolved_config
                self._audit_log(component_id, permission, "auto_grant", resolved_config, True)
                return True
            
            # secureモードではsandbox_bridgeをチェック
            if self._sandbox_bridge:
                has_perm = self._sandbox_bridge.has_permission(component_id, permission)
                if has_perm:
                    self._granted.setdefault(component_id, {})[permission] = resolved_config
                    self._audit_log(component_id, permission, "sandbox_grant", resolved_config, True)
                    return True
            
            # ペンディングリクエストとして記録
            req = PermissionRequest(
                permission=permission,
                component_id=component_id,
                config=resolved_config,
                reason=reason,
                requested_at=self._now_ts()
            )
            self._pending_requests.append(req)
            self._audit_log(component_id, permission, "request_pending", resolved_config, False)
            
            return False
    
    def has_permission(self, component_id: str, permission: str) -> bool:
        """権限を持っているかチェック"""
        with self._lock:
            if self._mode == "permissive":
                return True
            
            if self._is_granted_internal(component_id, permission):
                return True
            
            if self._sandbox_bridge:
                return self._sandbox_bridge.has_permission(component_id, permission)
            
            return False
    
    def _is_granted_internal(self, component_id: str, permission: str) -> bool:
        """内部: 許可済みかチェック（ロック内で呼び出す）"""
        if component_id not in self._granted:
            return False
        
        if permission not in self._granted[component_id]:
            return False
        
        grant_data = self._granted[component_id][permission]
        return self._is_grant_valid(grant_data)
    
    def _is_grant_valid(self, grant_data: Dict[str, Any]) -> bool:
        """許可が有効か（期限切れでないか）チェック"""
        if not isinstance(grant_data, dict):
            return True
        
        expires_at = grant_data.get("_expires_at")
        if not expires_at:
            return True
        
        try:
            exp_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) <= exp_time
        except (ValueError, TypeError):
            return True
    
    # ===== 権限付与・拒否 =====
    
    def grant(
        self, 
        component_id: str, 
        permission: str, 
        config: Dict[str, Any] = None
    ) -> bool:
        """権限を明示的に付与"""
        with self._lock:
            # グループの場合は展開
            perms = self._expand_permission_internal(permission)
            resolved_config = self.resolve_scope_variables(config or {})
            
            for perm in perms:
                self._granted.setdefault(component_id, {})[perm] = resolved_config
                self._audit_log(component_id, perm, "grant", resolved_config, True)
            
            # ペンディングから削除
            self._pending_requests = [
                r for r in self._pending_requests 
                if not (r.component_id == component_id and r.permission in perms)
            ]
            
            return True
    
    def grant_temporary(
        self, 
        component_id: str, 
        permission: str, 
        config: Dict[str, Any] = None,
        duration_seconds: float = 3600
    ) -> bool:
        """一時的に権限を付与"""
        with self._lock:
            perms = self._expand_permission_internal(permission)
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).isoformat().replace("+00:00", "Z")
            
            resolved_config = self.resolve_scope_variables(config or {})
            grant_data = {
                **resolved_config,
                "_expires_at": expires_at,
                "_duration": duration_seconds
            }
            
            for perm in perms:
                self._granted.setdefault(component_id, {})[perm] = grant_data
                self._audit_log(component_id, perm, "grant_temporary", grant_data, True)
            
            return True
    
    def deny(self, component_id: str, permission: str) -> bool:
        """権限を拒否"""
        with self._lock:
            # ペンディングから削除してdenied状態に
            for req in self._pending_requests:
                if req.component_id == component_id and req.permission == permission:
                    req.status = "denied"
            
            self._pending_requests = [
                r for r in self._pending_requests 
                if not (r.component_id == component_id and r.permission == permission)
            ]
            
            self._audit_log(component_id, permission, "deny", {}, False)
            return True
    
    def revoke(self, component_id: str, permission: str = None) -> bool:
        """権限を取り消し"""
        with self._lock:
            if component_id not in self._granted:
                return False
            
            if permission:
                if permission in self._granted[component_id]:
                    del self._granted[component_id][permission]
                    self._audit_log(component_id, permission, "revoke", {}, True)
                    return True
                return False
            else:
                # 全権限を取り消し
                del self._granted[component_id]
                self._audit_log(component_id, "*", "revoke_all", {}, True)
                return True
    
    # ===== 権限グループ =====
    
    def register_permission_group(self, group_name: str, permissions: List[str]) -> None:
        """権限グループを登録"""
        with self._lock:
            self._permission_groups[group_name] = list(permissions)
    
    def expand_permission(self, permission: str) -> List[str]:
        """権限（またはグループ）を個別の権限に展開"""
        with self._lock:
            return self._expand_permission_internal(permission)
    
    def _expand_permission_internal(self, permission: str) -> List[str]:
        """内部: 権限展開（ロック内で呼び出す）"""
        if permission in self._permission_groups:
            return list(self._permission_groups[permission])
        return [permission]
    
    # ===== 信頼関係 =====
    
    def trust(self, component_id: str, trusted_component_id: str) -> None:
        """コンポーネント間の信頼関係を確立"""
        with self._lock:
            if trusted_component_id not in self._trust_relationships.setdefault(component_id, []):
                self._trust_relationships[component_id].append(trusted_component_id)
    
    def untrust(self, component_id: str, trusted_component_id: str) -> bool:
        """信頼関係を削除"""
        with self._lock:
            if component_id in self._trust_relationships:
                if trusted_component_id in self._trust_relationships[component_id]:
                    self._trust_relationships[component_id].remove(trusted_component_id)
                    return True
            return False
    
    def can_act_as(self, actor_id: str, target_id: str) -> bool:
        """actorがtargetの代理として行動できるかチェック"""
        with self._lock:
            if target_id in self._trust_relationships:
                return actor_id in self._trust_relationships[target_id]
            return False
    
    # ===== スコープ変数解決 =====
    
    def resolve_scope_variables(self, value: Any, context: Dict[str, Any] = None) -> Any:
        """
        スコープ変数を解決
        
        サポートする変数:
        - ${mount:key} - マウントパスに解決
        - ${env:KEY} - 環境変数に解決
        - ${component:runtime_dir} - コンポーネントディレクトリに解決
        """
        if isinstance(value, str):
            return self._resolve_string_variables(value, context)
        elif isinstance(value, dict):
            return {k: self.resolve_scope_variables(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_scope_variables(item, context) for item in value]
        return value
    
    def _resolve_string_variables(self, s: str, context: Dict[str, Any] = None) -> str:
        """文字列内の変数を解決"""
        def replacer(match):
            var_type = match.group(1)
            var_key = match.group(2)
            
            if var_type == "mount":
                try:
                    from backend_core.ecosystem.mounts import get_mount_manager
                    mm = get_mount_manager()
                    return str(mm.get_path(var_key, ensure_exists=False))
                except Exception:
                    return match.group(0)
            
            elif var_type == "env":
                return os.environ.get(var_key, match.group(0))
            
            elif var_type == "component":
                if context and "paths" in context:
                    if var_key == "runtime_dir":
                        return context["paths"].get("component_runtime_dir", match.group(0))
                return match.group(0)
            
            return match.group(0)
        
        pattern = r'\$\{(\w+):([^}]+)\}'
        return re.sub(pattern, replacer, s)
    
    # ===== 監査ログ =====

    _SENSITIVE_KEY_PATTERNS = ("key", "token", "secret", "password", "credential", "auth")

    def _mask_sensitive(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        config辞書のセンシティブなキーの値をマスクしたコピーを返す。
        元のconfigは変更しない。
        """
        if not config or not isinstance(config, dict):
            return config

        masked = {}
        for k, v in config.items():
            k_lower = k.lower()
            if any(pattern in k_lower for pattern in self._SENSITIVE_KEY_PATTERNS):
                masked[k] = "***"
            elif isinstance(v, dict):
                masked[k] = self._mask_sensitive(v)
            else:
                masked[k] = v
        return masked

    
    def _audit_log(
        self,
        component_id: str,
        permission: str,
        action: str,
        config: Dict[str, Any] = None,
        result: bool = True
    ) -> None:
        """監査ログを記録"""
        try:
            # マウントシステムを使用してパスを取得
            try:
                from backend_core.ecosystem.mounts import get_mount_manager
                mm = get_mount_manager()
                audit_dir = mm.get_path("data.settings", ensure_exists=True) / "audit"
            except Exception:
                audit_dir = Path("user_data/settings/audit")
            
            audit_dir.mkdir(parents=True, exist_ok=True)
            
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            audit_file = audit_dir / f"permissions_{today}.jsonl"
            
            log_entry = {
                "ts": self._now_ts(),
                "component_id": component_id,
                "permission": permission,
                "action": action,
                "config": self._mask_sensitive(config) if config else config,
                "result": result,
                "mode": self._mode
            }
            
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 監査ログのエラーで処理を止めない
    
    # ===== 状態取得 =====
    
    def get_pending_requests(self) -> List[PermissionRequest]:
        """ペンディング中の権限リクエストを取得"""
        with self._lock:
            return list(self._pending_requests)
    
    def get_grants(self, component_id: str = None) -> Dict[str, Any]:
        """付与された権限を取得"""
        with self._lock:
            if component_id:
                return dict(self._granted.get(component_id, {}))
            return {k: dict(v) for k, v in self._granted.items()}
    
    def get_trust_relationships(self) -> Dict[str, List[str]]:
        """信頼関係を取得"""
        with self._lock:
            return {k: list(v) for k, v in self._trust_relationships.items()}
    
    def get_permission_groups(self) -> Dict[str, List[str]]:
        """権限グループを取得"""
        with self._lock:
            return {k: list(v) for k, v in self._permission_groups.items()}




# グローバル変数（後方互換のため残存。DI コンテナ優先）
_global_permission_manager: Optional[PermissionManager] = None
_pm_lock = threading.Lock()


def get_permission_manager() -> PermissionManager:
    """
    グローバルな PermissionManager を取得する。

    DI コンテナ経由で遅延初期化・キャッシュされる。

    Returns:
        PermissionManager インスタンス
    """
    from .di_container import get_container
    return get_container().get("permission_manager")


def reset_permission_manager() -> PermissionManager:
    """
    PermissionManager をリセットする（テスト用）。

    新しいインスタンスを生成し、DI コンテナのキャッシュを置き換える。

    Returns:
        新しい PermissionManager インスタンス
    """
    global _global_permission_manager
    with _pm_lock:
        _global_permission_manager = PermissionManager()
    # DI コンテナのキャッシュも更新（_pm_lock の外で実行してデッドロック回避）
    from .di_container import get_container
    get_container().set_instance("permission_manager", _global_permission_manager)
    return _global_permission_manager
