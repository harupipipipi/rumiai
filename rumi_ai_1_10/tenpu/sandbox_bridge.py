"""
sandbox_bridge.py - Sandbox Bridge (公式ファイル)

Ecosystem コンポーネントと Docker コンテナの仲介役。
各 Pack は完全に隔離されたコンテナで実行される。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class SandboxConfig:
    """Sandbox設定"""
    docker_dir: str = "docker"
    auto_reconcile: bool = True


class SandboxBridge:
    """
    Ecosystem と Docker コンテナの仲介役
    """
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._handlers: Dict[str, Any] = {}
        self._handler_meta: Dict[str, Dict[str, Any]] = {}
        self._scopes: Dict[str, Dict[str, Any]] = {}
        self._grants: Dict[str, Dict[str, Any]] = {}
        self._docker_dir: Optional[Path] = None
        self._grants_dir: Optional[Path] = None
        self._initialized = False
        self._container_manager = None
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def initialize(self) -> Dict[str, Any]:
        """Sandbox を初期化"""
        result = {
            "success": True,
            "handlers_loaded": [],
            "scopes_loaded": [],
            "grants_loaded": [],
            "grants_reconciled": [],
            "containers_initialized": False,
            "errors": []
        }
        
        try:
            self._docker_dir = Path(self.config.docker_dir)
            self._grants_dir = self._docker_dir / "grants"
            
            self._grants_dir.mkdir(parents=True, exist_ok=True)
            
            handlers_dir = self._docker_dir / "handlers"
            if handlers_dir.exists():
                for py_file in handlers_dir.glob("*.py"):
                    if py_file.name.startswith("_"):
                        continue
                    try:
                        name = py_file.stem
                        module = self._load_handler_module(py_file)
                        if hasattr(module, "execute") and callable(module.execute):
                            self._handlers[name] = module
                            self._handler_meta[name] = getattr(module, "META", {})
                            result["handlers_loaded"].append(name)
                    except Exception as e:
                        result["errors"].append(f"Handler load error ({py_file.name}): {e}")
            
            scopes_dir = self._docker_dir / "scopes"
            if scopes_dir.exists():
                for json_file in scopes_dir.glob("*.json"):
                    try:
                        name = json_file.stem
                        self._scopes[name] = json.loads(json_file.read_text(encoding="utf-8"))
                        result["scopes_loaded"].append(name)
                    except Exception as e:
                        result["errors"].append(f"Scope load error ({json_file.name}): {e}")
            
            if self._grants_dir.exists():
                for json_file in self._grants_dir.glob("*.json"):
                    if json_file.name.startswith("."):
                        continue
                    try:
                        data = json.loads(json_file.read_text(encoding="utf-8"))
                        component_id = data.get("component_id", json_file.stem)
                        self._grants[component_id] = data
                        result["grants_loaded"].append(component_id)
                    except Exception as e:
                        result["errors"].append(f"Grant load error ({json_file.name}): {e}")
            
            if self.config.auto_reconcile:
                reconciled = self._reconcile_grants()
                result["grants_reconciled"] = reconciled
            
            try:
                from .sandbox_container import get_container_manager
                self._container_manager = get_container_manager()
                container_result = self._container_manager.initialize()
                result["containers_initialized"] = container_result.get("success", False)
                result["docker_available"] = container_result.get("docker_available", False)
                if container_result.get("errors"):
                    result["errors"].extend(container_result["errors"])
            except Exception as e:
                result["errors"].append(f"Container manager error: {e}")
            
            self._initialized = True
            
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"Initialization error: {e}")
        
        return result
    
    def _load_handler_module(self, file_path: Path) -> Any:
        """ハンドラモジュールを動的にロード"""
        module_name = f"sandbox_handler_{file_path.stem}_{abs(hash(str(file_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    
    def _reconcile_grants(self) -> List[str]:
        """grants を現在の handlers/scopes と照合し、矛盾を修正"""
        reconciled = []
        
        for component_id, grant_data in list(self._grants.items()):
            modified = False
            permissions = grant_data.get("permissions", {})
            
            for perm_name,
 perm_config in list(permissions.items()):
                if perm_name not in self._handlers:
                    perm_config["valid"] = False
                    perm_config["invalid_reason"] = "handler_not_found"
                    modified = True
                    continue
                
                meta = self._handler_meta.get(perm_name, {})
                if meta.get("requires_scope") and perm_name not in self._scopes:
                    perm_config["valid"] = False
                    perm_config["invalid_reason"] = "scope_not_found"
                    modified = True
                    continue
                
                if perm_config.get("valid") is False and perm_config.get("invalid_reason") in ("handler_not_found", "scope_not_found"):
                    perm_config["valid"] = True
                    perm_config.pop("invalid_reason", None)
                    modified = True
                elif "valid" not in perm_config:
                    perm_config["valid"] = True
                    modified = True
            
            if modified:
                grant_data["validated_at"] = self._now_ts()
                self._save_grant(component_id, grant_data)
                reconciled.append(component_id)
        
        return reconciled
    
    def _save_grant(self, component_id: str, data: Dict[str, Any]) -> bool:
        """grant を保存"""
        if self._grants_dir is None:
            return False
        
        try:
            safe_filename = component_id.replace(":", "_").replace("/", "_")
            grant_file = self._grants_dir / f"{safe_filename}.json"
            grant_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            return False
    
    def request(
        self,
        component_id: str,
        permission: str,
        args: Dict[str, Any],
        pack_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """コンポーネントからのリクエストを処理"""
        if not self._initialized:
            return {"success": False, "error": "Sandbox not initialized"}
        
        if permission not in self._handlers:
            return {"success": False, "error": f"Handler not found: {permission}"}
        
        grant = self._get_grant(component_id, permission)
        if grant is None:
            return {"success": False, "error": f"Permission not granted: {permission}"}
        
        if not grant.get("enabled", False):
            return {"success": False, "error": f"Permission disabled: {permission}"}
        
        meta = self._handler_meta.get(permission, {})
        if meta.get("requires_scope", False):
            scope_check = self._check_scope(permission, grant, args)
            if not scope_check["allowed"]:
                return {"success": False, "error": scope_check["reason"]}
        
        context = {
            "component_id": component_id,
            "permission": permission,
            "pack_id": pack_id,
            "grant": grant,
            "ts": self._now_ts()
        }
        
        if "allowed_keys" in grant:
            context["allowed_keys"] = grant["allowed_keys"]
        if "directories" in grant:
            context["directories"] = grant["directories"]
        if "allowed_domains" in grant:
            context["allowed_domains"] = grant["allowed_domains"]
        if "blocked_domains" in grant:
            context["blocked_domains"] = grant["blocked_domains"]
        if "allowed_ports" in grant:
            context["allowed_ports"] = grant["allowed_ports"]
        
        if pack_id and self._container_manager:
            return self._execute_in_container(pack_id, permission, context, args)
        
        security_mode = os.environ.get("RUMI_SECURITY_MODE", "strict").lower()
        
        if security_mode != "permissive":
            return {
                "success": False, 
                "error": "Docker is required for handler execution. Set RUMI_SECURITY_MODE=permissive for development."
            }
        
        print(f"[SECURITY WARNING] Executing handler '{permission}' on host without isolation!", file=sys.stderr)
        print(f"[SECURITY WARNING] This is only acceptable for development.", file=sys.stderr)
        
        try:
            handler = self._handlers[permission]
            result = handler.execute(context, args)
            self._audit_log(component_id, permission, args, result)
            return result
        except Exception as e:
            error_result = {"success": False, "error": f"Handler error: {e}"}
            self._audit_log(component_id, permission, args, error_result)
            return error_result
    
    def _execute_in_container(
        self,
        pack_id: str,
        permission: str,
        context: Dict[str, Any],
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """コンテナ内でハンドラを実行"""
        if self._container_manager is None:
            return {"success": False, "error": "Container manager not available"}
        
        return self._container_manager.execute_handler(pack_id, permission, context, args)
    
    def _get_grant(self, component_id: str, permission: str) -> Optional[Dict[str, Any]]:
        """コンポーネントの特定権限のgrantを取得"""
        if component_id not in self._grants:
            return None
        
        grants = self._grants[component_id]
        permissions = grants.get("permissions", {})
        grant = permissions.get(permission)
        
        if grant and grant.get("valid") is False:
            return None
        
        return grant
    
    def _check_scope(
        self,
        permission: str,
        grant: Dict[str, Any],
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """スコープチェック"""
        if "directories" in grant:
            path = args.get("path", "")
            if path:
                allowed_dirs = grant["directories"]
                if not self._is_path_allowed(path, allowed_dirs):
                    return {"allowed": False, "reason": f"Path not in allowed directories: {path}"}
        
        if "allowed_keys" in grant:
            requested_keys = args.get("keys", [])
            if requested_keys:
                allowed_keys = set(grant["allowed_keys"])
                if "*" not in allowed_keys:
                    for key in requested_keys:
                        if key not in allowed_keys:
                            return {"allowed": False, "reason": f"Key not allowed: {key}"}
        
        return {"allowed": True, "reason": ""}
    
    def _is_path_allowed(self, path: str, allowed_dirs: List[str]) -> bool:
        """パスが許可ディレクトリ内かチェック"""
        try:
            target = Path(path).resolve()
            
            for allowed in allowed_dirs:
                allowed_path = Path(allowed).expanduser().resolve()
                try:
                    target.relative_to(allowed_path)
                    return True
                except ValueError:
                    continue
            
            return False
        except Exception:
            return False
    
    def _audit_log(
        self,
        component_id: str,
        permission: str,
        args: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """監査ログを記録"""
        if self._docker_dir is None:
            return
        
        try:
            audit_dir = self._docker_dir / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            audit_file = audit_dir / f"{today}.jsonl"
            
            log_entry = {
                "ts": self._now_ts(),
                "component_id": component_id,
                "permission": permission,
                "success": result.get("success", False),
                "error": result.get("error") if not result.get("success") else None
            }
            
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
    
    def list_handlers(self) -> List[str]:
        """利用可能なハンドラ一覧"""
        return list(self._handlers.keys())
    
    def get_handler_meta(self, name: str) -> Dict[str, Any]:
        """ハンドラのメタ情報取得"""
        return self._handler_meta.get(name, {})
    
    def has_permission(self, component_id: str, permission: str) -> bool:
        """権限があるかチェック"""
        grant = self._get_grant(component_id, permission)
        return grant is not None and grant.get("enabled", False)
    
    def grant_permission(
        self,
        component_id: str,
        permission: str,
        config: Dict[str, Any]
    ) -> bool:
        """権限を付与"""
        if self._grants_dir is None:
            return False
        
        if permission not in self._handlers:
            return False
        
        try:
            self._grants_dir.mkdir(parents=True, exist_ok=True)
            
            safe_filename = component_id.replace(":", "_").replace("/", "_")
            grant_file = self._grants_dir / f"{safe_filename}.json"
            
            if grant_file.exists():
                data = json.loads(grant_file.read_text(encoding="utf-8"))
            else:
                data = {
                    "version": "1.0",
                    "component_id": component_id,
                    "created_at": self._now_ts(),
                    "permissions": {}
                }
            
            data["permissions"][permission] = {
                "enabled": True,
                "valid": True,
                "granted_at": self._now_ts(),
                **config
            }
            data["updated_at"] = self._now_ts()
            data["validated_at"] = self._now_ts()
            
            grant_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._grants[component_id] = data
            
            return True
        except Exception:
            return False
    
    def revoke_permission(self, component_id: str, permission: str) -> bool:
        """権限を取り消し"""
        if self._grants_dir is None:
            return False
        
        try:
            safe_filename = component_id.replace(":", "_").replace("/", "_")
            grant_file = self._grants_dir / f"{safe_filename}.json"
            
            if not grant_file.exists():
                return False
            
            data = json.loads(grant_file.read_text(encoding="utf-8"))
            
            if permission in data.get("permissions", {}):
                del data["permissions"][permission]
                data["updated_at"] = self._now_ts()
                
                grant_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                self._grants[component_id] = data
                return True
            
            return False
        except Exception:
            return False


_global_sandbox: Optional[SandboxBridge] = None


def get_sandbox_bridge() -> SandboxBridge:
    """グローバルなSandboxBridgeを取得"""
    global _global_sandbox
    if _global_sandbox is None:
        _global_sandbox = SandboxBridge()
    return _global_sandbox


def initialize_sandbox() -> Dict[str, Any]:
    """Sandboxを初期化"""
    bridge = get_sandbox_bridge()
    return bridge.initialize()
