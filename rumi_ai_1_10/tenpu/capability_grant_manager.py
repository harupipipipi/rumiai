"""
capability_grant_manager.py - Capability 権限 Grant 管理

principal_id × permission_id の Grant を管理する。
NetworkGrantManager と同じ HMAC 署名方式を採用。

設計原則:
- 1 principal 1 ファイル
- HMAC-SHA256 署名で改ざん検知
- principal_id のサニタイズ（パストラバーサル防止）
- 公式は permission_id の意味を解釈しない
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .hierarchical_grant import parse_principal_chain, intersect_config

_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|.\x00-\x1f]')


def sanitize_principal_id(principal_id: str) -> str:
    """principal_id をファイルシステム安全な文字列に変換"""
    return _UNSAFE_CHARS.sub("_", principal_id)


@dataclass
class CapabilityPermissionGrant:
    """単一 permission の grant 情報"""
    enabled: bool
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityGrant:
    """principal 単位の grant"""
    principal_id: str
    enabled: bool
    granted_at: str
    updated_at: str
    permissions: Dict[str, CapabilityPermissionGrant] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "principal_id": self.principal_id,
            "enabled": self.enabled,
            "granted_at": self.granted_at,
            "updated_at": self.updated_at,
            "permissions": {
                pid: {"enabled": p.enabled, "config": p.config}
                for pid, p in self.permissions.items()
            },
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CapabilityGrant':
        permissions = {}
        for pid, pdata in data.get("permissions", {}).items():
            if isinstance(pdata, dict):
                permissions[pid] = CapabilityPermissionGrant(
                    enabled=pdata.get("enabled", False),
                    config=pdata.get("config", {}),
                )
        return cls(
            principal_id=data.get("principal_id", ""),
            enabled=data.get("enabled", False),
            granted_at=data.get("granted_at", ""),
            updated_at=data.get("updated_at", ""),
            permissions=permissions,
        )


@dataclass
class GrantCheckResult:
    """Grant チェック結果"""
    allowed: bool
    reason: str
    principal_id: str
    permission_id: str
    config: Dict[str, Any] = field(default_factory=dict)


class CapabilityGrantManager:
    """
    Capability Grant 管理
    
    user_data/permissions/capabilities/<safe_principal_id>.json で
    principal 単位の Grant を永続化する。
    """
    
    DEFAULT_GRANTS_DIR = "user_data/permissions/capabilities"
    SECRET_KEY_FILE = "user_data/permissions/.secret_key"
    
    def __init__(self, grants_dir: str = None, secret_key: str = None):
        self._grants_dir = Path(grants_dir) if grants_dir else Path(self.DEFAULT_GRANTS_DIR)
        self._secret_key = secret_key or self._load_or_create_secret_key()
        self._grants: Dict[str, CapabilityGrant] = {}
        self._tampered_principals: Set[str] = set()
        self._lock = threading.RLock()
        
        self._ensure_dir()
        self._load_all_grants()
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def _ensure_dir(self) -> None:
        """ディレクトリを作成"""
        self._grants_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_or_create_secret_key(self) -> str:
        """NetworkGrantManager と同じ secret_key を流用"""
        key_file = Path(self.SECRET_KEY_FILE)
        
        if key_file.exists():
            try:
                return key_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        
        key = hashlib.sha256(os.urandom(32)).hexdigest()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key, encoding="utf-8")
        
        try:
            os.chmod(key_file, 0o600)
        except (OSError, AttributeError):
            pass
        
        return key
    
    def _compute_hmac(self, data: Dict[str, Any]) -> str:
        """HMAC 署名を計算"""
        data_copy = {k: v for k, v in data.items() if not k.startswith("_hmac")}
        payload = json.dumps(data_copy, sort_keys=True, ensure_ascii=False)
        return hmac.new(
            self._secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    
    def _get_grant_file(self, principal_id: str) -> Path:
        """principal_id から Grant ファイルパスを取得"""
        return self._grants_dir / f"{sanitize_principal_id(principal_id)}.json"
    
    def _load_all_grants(self) -> None:
        """全 Grant をロード"""
        with self._lock:
            self._grants.clear()
            self._tampered_principals.clear()
            
            if not self._grants_dir.exists():
                return
            
            for grant_file in self._grants_dir.glob("*.json"):
                try:
                    self._load_grant_file(grant_file)
                except Exception:
                    pass
    
    def _load_grant_file(self, file_path: Path) -> Optional[CapabilityGrant]:
        """単一 Grant ファイルをロード"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # HMAC 検証
        stored_sig = data.pop("_hmac_signature", None)
        if stored_sig:
            computed_sig = self._compute_hmac(data)
            if not hmac.compare_digest(stored_sig, computed_sig):
                principal_id = data.get("principal_id", file_path.stem)
                # raw と sanitize 両方を登録して確実にブロック
                self._tampered_principals.add(principal_id)  # raw
                self._tampered_principals.add(sanitize_principal_id(principal_id))  # sanitized
                self._tampered_principals.add(file_path.stem)  # ファイル名ベース（フォールバック）
                self._audit_tamper(principal_id, file_path)
                return None
        
        grant = CapabilityGrant.from_dict(data)
        if grant.principal_id:
            self._grants[grant.principal_id] = grant
        return grant
    
    def _audit_tamper(self, principal_id: str, file_path: Path) -> None:
        """改ざん検出を監査ログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_security_event(
                event_type="capability_grant_tampered",
                severity="critical",
                description=f"HMAC verification failed for capability grant: {principal_id}",
                details={
                    "principal_id": principal_id,
                    "file": str(file_path),
                },
            )
        except Exception:
            pass
    
    def _save_grant(self, grant: CapabilityGrant) -> bool:
        """Grant を保存"""
        try:
            data = grant.to_dict()
            data["_hmac_signature"] = self._compute_hmac(data)
            
            file_path = self._get_grant_file(grant.principal_id)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False
    
    def check(self, principal_id: str, permission_id: str) -> GrantCheckResult:
        """
        Grant をチェック
        
        Args:
            principal_id: 主体ID（UDS由来）
            permission_id: 要求する権限ID
        
        Returns:
            GrantCheckResult
        """
        with self._lock:
            # 改ざん検出済みの principal は拒否（raw と sanitize 両方で判定）
            if (principal_id in self._tampered_principals
                    or sanitize_principal_id(principal_id) in self._tampered_principals):
                return GrantCheckResult(
                    allowed=False,
                    reason=f"Grant file for '{principal_id}' has been tampered with",
                    principal_id=principal_id,
                    permission_id=permission_id,
                )

            # 階層 principal チェーン（parent__child 形式に対応）
            chain = parse_principal_chain(principal_id)
            configs = []

            for ancestor_id in chain:
                # 改ざんチェック（各階層）
                if (ancestor_id in self._tampered_principals
                        or sanitize_principal_id(ancestor_id) in self._tampered_principals):
                    label = 'ancestor' if ancestor_id != principal_id else 'principal'
                    return GrantCheckResult(
                        allowed=False,
                        reason=f"Grant file for {label} '{ancestor_id}' has been tampered with",
                        principal_id=principal_id,
                        permission_id=permission_id,
                    )

                grant = self._grants.get(ancestor_id)
                label = 'ancestor' if ancestor_id != principal_id else 'principal'

                if grant is None:
                    return GrantCheckResult(
                        allowed=False,
                        reason=f"No capability grant for {label} '{ancestor_id}'",
                        principal_id=principal_id,
                        permission_id=permission_id,
                    )

                if not grant.enabled:
                    return GrantCheckResult(
                        allowed=False,
                        reason=f"Capability grant for {label} '{ancestor_id}' is disabled",
                        principal_id=principal_id,
                        permission_id=permission_id,
                    )

                perm = grant.permissions.get(permission_id)
                if perm is None:
                    return GrantCheckResult(
                        allowed=False,
                        reason=f"Permission '{permission_id}' not granted to {label} '{ancestor_id}'",
                        principal_id=principal_id,
                        permission_id=permission_id,
                    )

                if not perm.enabled:
                    return GrantCheckResult(
                        allowed=False,
                        reason=f"Permission '{permission_id}' is disabled for {label} '{ancestor_id}'",
                        principal_id=principal_id,
                        permission_id=permission_id,
                    )

                configs.append(dict(perm.config))

            # 全階層 OK → config は intersection
            final_config = intersect_config(configs) if len(configs) > 1 else (configs[0] if configs else {})

            return GrantCheckResult(
                allowed=True,
                reason="Granted",
                principal_id=principal_id,
                permission_id=permission_id,
                config=final_config,
            )

    
    def grant_permission(
        self,
        principal_id: str,
        permission_id: str,
        config: Dict[str, Any] = None,
    ) -> CapabilityGrant:
        """permission を付与"""
        with self._lock:
            now = self._now_ts()
            grant = self._grants.get(principal_id)
            
            if grant is None:
                grant = CapabilityGrant(
                    principal_id=principal_id,
                    enabled=True,
                    granted_at=now,
                    updated_at=now,
                )
                self._grants[principal_id] = grant
            
            grant.updated_at = now
            grant.enabled = True
            grant.permissions[permission_id] = CapabilityPermissionGrant(
                enabled=True,
                config=config or {},
            )
            
            self._tampered_principals.discard(principal_id)  # raw
            self._tampered_principals.discard(sanitize_principal_id(principal_id))  # sanitized
            self._save_grant(grant)
            
            self._audit_grant_event(principal_id, permission_id, "grant", True)
            
            return grant
    
    def revoke_permission(
        self,
        principal_id: str,
        permission_id: str,
    ) -> bool:
        """permission を取り消し"""
        with self._lock:
            grant = self._grants.get(principal_id)
            if grant is None:
                return False
            
            perm = grant.permissions.get(permission_id)
            if perm is None:
                return False
            
            perm.enabled = False
            grant.updated_at = self._now_ts()
            self._save_grant(grant)
            
            self._audit_grant_event(principal_id, permission_id, "revoke", True)
            return True
    
    def revoke_all(self, principal_id: str) -> bool:
        """principal の全 permission を取り消し"""
        with self._lock:
            grant = self._grants.get(principal_id)
            if grant is None:
                return False
            
            grant.enabled = False
            grant.updated_at = self._now_ts()
            self._save_grant(grant)
            
            self._audit_grant_event(principal_id, "*", "revoke_all", True)
            return True
    
    def get_grant(self, principal_id: str) -> Optional[CapabilityGrant]:
        """Grant を取得"""
        with self._lock:
            return self._grants.get(principal_id)
    
    def get_all_grants(self) -> Dict[str, CapabilityGrant]:
        """全 Grant を取得"""
        with self._lock:
            return dict(self._grants)
    
    def delete_grant(self, principal_id: str) -> bool:
        """Grant を削除"""
        with self._lock:
            if principal_id not in self._grants:
                return False
            
            del self._grants[principal_id]
            
            file_path = self._get_grant_file(principal_id)
            if file_path.exists():
                file_path.unlink()
            
            self._audit_grant_event(principal_id, "*", "delete", True)
            return True
    
    def _audit_grant_event(
        self, principal_id: str, permission_id: str, action: str, success: bool
    ) -> None:
        """Grant 操作を監査ログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_permission_event(
                pack_id=principal_id,
                permission_type="capability",
                action=action,
                success=success,
                details={
                    "principal_id": principal_id,
                    "permission_id": permission_id,
                },
            )
        except Exception:
            pass


# グローバルインスタンス
_global_grant_manager: Optional[CapabilityGrantManager] = None
_grant_lock = threading.Lock()


def get_capability_grant_manager() -> CapabilityGrantManager:
    """グローバルなCapabilityGrantManagerを取得"""
    global _global_grant_manager
    if _global_grant_manager is None:
        with _grant_lock:
            if _global_grant_manager is None:
                _global_grant_manager = CapabilityGrantManager()
    return _global_grant_manager


def reset_capability_grant_manager(grants_dir: str = None, secret_key: str = None) -> CapabilityGrantManager:
    """リセット（テスト用）"""
    global _global_grant_manager
    with _grant_lock:
        _global_grant_manager = CapabilityGrantManager(grants_dir, secret_key)
    return _global_grant_manager
