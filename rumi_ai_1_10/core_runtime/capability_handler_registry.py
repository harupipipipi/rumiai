"""
capability_handler_registry.py - Capability ハンドラーレジストリ

user_data/capabilities/handlers/ 配下の handler.json + handler.py を探索し、
permission_id → handler 定義のインデックスを構築する。

設計原則:
- permission_id の重複は起動失敗（曖昧さ排除）
- 公式は permission_id の意味を解釈しない（贔屓なし）
- handler.py の sha256 計算ヘルパーを提供
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HandlerDefinition:
    """ハンドラー定義"""
    handler_id: str
    permission_id: str
    entrypoint: str  # "handler.py:execute"
    description: str = ""
    risk: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    
    # 内部メタデータ
    handler_dir: Optional[Path] = None
    handler_py_path: Optional[Path] = None
    handler_json_path: Optional[Path] = None
    handler_py_sha256: Optional[str] = None
    slug: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "handler_id": self.handler_id,
            "permission_id": self.permission_id,
            "entrypoint": self.entrypoint,
            "description": self.description,
            "risk": self.risk,
            "handler_dir": str(self.handler_dir) if self.handler_dir else None,
            "handler_py_sha256": self.handler_py_sha256,
            "slug": self.slug,
        }


@dataclass
class RegistryLoadResult:
    """レジストリロード結果"""
    success: bool
    handlers_loaded: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    duplicates: List[Dict[str, Any]] = field(default_factory=list)


class CapabilityHandlerRegistry:
    """
    Capability ハンドラーレジストリ
    
    user_data/capabilities/handlers/<slug>/handler.json をスキャンし、
    permission_id → HandlerDefinition のマッピングを構築する。
    
    重複 permission_id は起動失敗として扱う。
    """
    
    DEFAULT_HANDLERS_DIR = "user_data/capabilities/handlers"
    
    def __init__(self, handlers_dir: str = None):
        self._handlers_dir = Path(handlers_dir) if handlers_dir else Path(self.DEFAULT_HANDLERS_DIR)
        self._lock = threading.RLock()
        self._by_permission_id: Dict[str, HandlerDefinition] = {}
        self._by_handler_id: Dict[str, HandlerDefinition] = {}
        self._load_errors: List[Dict[str, Any]] = []
        self._duplicates: List[Dict[str, Any]] = []
        self._loaded: bool = False
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def load_all(self) -> RegistryLoadResult:
        """
        全ハンドラーをロード
        
        重複 permission_id が見つかった場合は RegistryLoadResult.success = False。
        """
        with self._lock:
            self._by_permission_id.clear()
            self._by_handler_id.clear()
            self._load_errors.clear()
            self._duplicates.clear()
            self._loaded = False
            
            if not self._handlers_dir.exists():
                self._loaded = True
                return RegistryLoadResult(success=True, handlers_loaded=0)
            
            permission_candidates: Dict[str, List[HandlerDefinition]] = {}
            
            for slug_dir in sorted(self._handlers_dir.iterdir()):
                if not slug_dir.is_dir() or slug_dir.name.startswith("."):
                    continue
                
                handler_json_path = slug_dir / "handler.json"
                if not handler_json_path.exists():
                    self._load_errors.append({
                        "slug": slug_dir.name,
                        "error": "handler.json not found",
                        "path": str(slug_dir),
                        "ts": self._now_ts(),
                    })
                    continue
                
                handler_def = self._load_handler(slug_dir, handler_json_path)
                if handler_def is None:
                    continue
                
                if handler_def.handler_id in self._by_handler_id:
                    existing = self._by_handler_id[handler_def.handler_id]
                    self._load_errors.append({
                        "slug": slug_dir.name,
                        "error": f"Duplicate handler_id: {handler_def.handler_id}",
                        "existing_slug": existing.slug,
                        "existing_path": str(existing.handler_dir),
                        "new_path": str(slug_dir),
                        "ts": self._now_ts(),
                    })
                    continue
                
                self._by_handler_id[handler_def.handler_id] = handler_def
                
                pid = handler_def.permission_id
                if pid not in permission_candidates:
                    permission_candidates[pid] = []
                permission_candidates[pid].append(handler_def)
            
            has_duplicates = False
            for pid, handlers in permission_candidates.items():
                if len(handlers) > 1:
                    has_duplicates = True
                    dup_info = {
                        "permission_id": pid,
                        "handler_count": len(handlers),
                        "handlers": [
                            {
                                "handler_id": h.handler_id,
                                "slug": h.slug,
                                "path": str(h.handler_dir),
                            }
                            for h in handlers
                        ],
                        "ts": self._now_ts(),
                    }
                    self._duplicates.append(dup_info)
                else:
                    self._by_permission_id[pid] = handlers[0]
            
            if has_duplicates:
                self._loaded = False
                self._audit_duplicate_error()
                return RegistryLoadResult(
                    success=False,
                    handlers_loaded=len(self._by_permission_id),
                    errors=list(self._load_errors),
                    duplicates=list(self._duplicates),
                )
            
            self._loaded = True
            return RegistryLoadResult(
                success=True,
                handlers_loaded=len(self._by_permission_id),
                errors=list(self._load_errors),
                duplicates=[],
            )
    
    def _load_handler(self, slug_dir: Path, handler_json_path: Path) -> Optional[HandlerDefinition]:
        """単一のハンドラーをロード"""
        slug = slug_dir.name
        
        try:
            with open(handler_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self._load_errors.append({
                "slug": slug, "error": f"Failed to parse handler.json: {e}",
                "path": str(handler_json_path), "ts": self._now_ts(),
            })
            return None
        
        if not isinstance(data, dict):
            self._load_errors.append({
                "slug": slug, "error": "handler.json must be a JSON object",
                "path": str(handler_json_path), "ts": self._now_ts(),
            })
            return None
        
        handler_id = data.get("handler_id")
        permission_id = data.get("permission_id")
        entrypoint = data.get("entrypoint", "handler.py:execute")
        
        if not handler_id or not isinstance(handler_id, str):
            self._load_errors.append({
                "slug": slug, "error": "Missing or invalid 'handler_id'",
                "path": str(handler_json_path), "ts": self._now_ts(),
            })
            return None
        
        if not permission_id or not isinstance(permission_id, str):
            self._load_errors.append({
                "slug": slug, "error": "Missing or invalid 'permission_id'",
                "path": str(handler_json_path), "ts": self._now_ts(),
            })
            return None
        
        if ":" not in entrypoint:
            self._load_errors.append({
                "slug": slug, "error": f"Invalid entrypoint format (expected 'file:func'): {entrypoint}",
                "path": str(handler_json_path), "ts": self._now_ts(),
            })
            return None
        
        ep_file, ep_func = entrypoint.rsplit(":", 1)
        handler_py_path = slug_dir / ep_file
        
        if not handler_py_path.exists():
            self._load_errors.append({
                "slug": slug, "error": f"Entrypoint file not found: {ep_file}",
                "path": str(handler_py_path), "ts": self._now_ts(),
            })
            return None
        
        sha256 = compute_file_sha256(handler_py_path)
        
        return HandlerDefinition(
            handler_id=handler_id, permission_id=permission_id, entrypoint=entrypoint,
            description=data.get("description", ""), risk=data.get("risk", ""),
            input_schema=data.get("input_schema", {}), output_schema=data.get("output_schema", {}),
            handler_dir=slug_dir.resolve(), handler_py_path=handler_py_path.resolve(),
            handler_json_path=handler_json_path.resolve(), handler_py_sha256=sha256, slug=slug,
        )
    
    def _audit_duplicate_error(self) -> None:
        """重複 permission_id エラーを監査ログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            for dup in self._duplicates:
                audit.log_security_event(
                    event_type="capability_handler_duplicate_permission",
                    severity="error",
                    description=f"Duplicate permission_id '{dup['permission_id']}' found in {dup['handler_count']} handlers",
                    details={"permission_id": dup["permission_id"], "handlers": dup["handlers"]},
                )
        except Exception:
            pass
    
    def get_by_permission_id(self, permission_id: str) -> Optional[HandlerDefinition]:
        """permission_id からハンドラーを取得"""
        with self._lock:
            return self._by_permission_id.get(permission_id)
    
    def get_by_handler_id(self, handler_id: str) -> Optional[HandlerDefinition]:
        """handler_id からハンドラーを取得"""
        with self._lock:
            return self._by_handler_id.get(handler_id)
    
    def list_all(self) -> List[HandlerDefinition]:
        """全ハンドラーを取得"""
        with self._lock:
            return list(self._by_permission_id.values())
    
    def list_permission_ids(self) -> List[str]:
        """登録済み permission_id を取得"""
        with self._lock:
            return list(self._by_permission_id.keys())
    
    def is_loaded(self) -> bool:
        """正常にロード完了したか"""
        with self._lock:
            return self._loaded
    
    def get_load_errors(self) -> List[Dict[str, Any]]:
        """ロードエラーを取得"""
        with self._lock:
            return list(self._load_errors)
    
    def get_duplicates(self) -> List[Dict[str, Any]]:
        """重複情報を取得"""
        with self._lock:
            return list(self._duplicates)


def compute_file_sha256(file_path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# グローバルインスタンス
_global_registry: Optional[CapabilityHandlerRegistry] = None
_registry_lock = threading.Lock()


def get_capability_handler_registry() -> CapabilityHandlerRegistry:
    """グローバルなCapabilityHandlerRegistryを取得"""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = CapabilityHandlerRegistry()
    return _global_registry


def reset_capability_handler_registry(handlers_dir: str = None) -> CapabilityHandlerRegistry:
    """リセット（テスト用）"""
    global _global_registry
    with _registry_lock:
        _global_registry = CapabilityHandlerRegistry(handlers_dir)
    return _global_registry
