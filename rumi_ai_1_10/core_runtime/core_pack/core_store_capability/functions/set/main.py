"""
store.set - Built-in Capability Handler

Store にキーに対応する JSON 値を書き込む。

セキュリティ:
- grant_config.allowed_store_ids で制限
- key の '..' 即拒否 + normpath + is_path_within で boundary チェック
- サブプロセス実行のため store_registry は新インスタンス
  （ファイルベースのため書き込みは正常動作。メインプロセスの
   インメモリキャッシュとの即時同期は保証されない。
   現時点では Store index 自体を変更しないため問題なし。
   将来的に store_registry._load() 再呼び出しが必要になる可能性あり）

注意: max_value_bytes の grant_config 制限をサポート（デフォルト1MB）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict


_SAFE_KEY_RE = re.compile(r"^[a-zA-Z0-9_/.-]+$")
DEFAULT_MAX_VALUE_BYTES = 1 * 1024 * 1024  # 1MB


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    grant_config = context.get("grant_config", {})
    principal_id = context.get("principal_id", "")

    store_id = args.get("store_id", "")
    key = args.get("key", "")
    value = args.get("value")

    # --- 入力バリデーション ---
    if not store_id or not isinstance(store_id, str):
        return _error("Missing or invalid store_id", "validation_error")
    if not key or not isinstance(key, str):
        return _error("Missing or invalid key", "validation_error")
    if value is None:
        return _error("Missing value", "validation_error")

    # --- key セキュリティチェック ---
    validation = _validate_key(key)
    if validation is not None:
        return validation

    # --- Grant config: allowed_store_ids ---
    allowed = grant_config.get("allowed_store_ids", [])
    if allowed and store_id not in allowed:
        return _error("Store not in allowed_store_ids", "grant_denied")

    # --- value サイズチェック ---
    max_bytes = grant_config.get("max_value_bytes", DEFAULT_MAX_VALUE_BYTES)
    try:
        value_json = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        return _error("Value is not JSON serializable: " + str(e), "validation_error")

    if len(value_json.encode("utf-8")) > max_bytes:
        return _error(
            "Value too large (max " + str(max_bytes) + " bytes)",
            "payload_too_large",
        )

    # --- Store 解決 ---
    store_root = _resolve_store_root(store_id)
    if store_root is None:
        return _error("Store not found: " + store_id, "store_not_found")

    # --- ファイルパス構築 + boundary チェック ---
    file_path = store_root / (key + ".json")
    file_path = Path(os.path.normpath(file_path))

    if not _is_path_within(file_path, store_root):
        return _error("Path traversal detected", "security_error")

    # --- 書き込み（アトミック） ---
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = file_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(value_json)
        tmp_path.replace(file_path)
    except OSError as e:
        return _error("Failed to write: " + str(e), "write_error")

    _audit_store_write(principal_id, store_id, key, len(value_json))

    return {"success": True, "path": str(file_path)}


def _validate_key(key: str) -> Any:
    if ".." in key.split("/"):
        return _error("Key contains '..' (path traversal)", "security_error")
    if not _SAFE_KEY_RE.match(key):
        return _error(
            "Key contains invalid characters (allowed: a-zA-Z0-9_/.-)",
            "validation_error",
        )
    if key.startswith("/") or key.endswith("/"):
        return _error("Key must not start or end with '/'", "validation_error")
    return None


def _resolve_store_root(store_id: str) -> Any:
    try:
        from core_runtime.store_registry import get_store_registry
        registry = get_store_registry()
        store_def = registry.get_store(store_id)
        if store_def is None:
            return None
        root = Path(store_def.root_path)
        if not root.is_dir():
            return None
        return root.resolve()
    except Exception:
        return None


def _is_path_within(target: Path, boundary: Path) -> bool:
    try:
        resolved_target = target.resolve()
        resolved_boundary = boundary.resolve()
        resolved_target.relative_to(resolved_boundary)
        return True
    except (ValueError, OSError):
        return False


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}


def _audit_store_write(
    principal_id: str, store_id: str, key: str, size_bytes: int
) -> None:
    try:
        from core_runtime.audit_logger import get_audit_logger
        audit = get_audit_logger()
        audit.log_permission_event(
            pack_id=principal_id,
            permission_type="capability",
            action="store_set",
            success=True,
            details={
                "store_id": store_id,
                "key": key,
                "size_bytes": size_bytes,
            },
        )
    except Exception:
        pass
