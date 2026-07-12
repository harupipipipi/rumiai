"""
store.get - Built-in Capability Handler

Store からキーに対応する JSON 値を読み取る。

セキュリティ:
- grant_config.allowed_store_ids で許可された Store のみアクセス可
- key に '..' が含まれる場合は即拒否（パストラバーサル防止）
- normpath + is_path_within で store root 内に収まることを検証
- サブプロセスで実行されるため store_registry は新インスタンスが生成される
  （ファイルベースのため読み取りは正常動作）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict


_SAFE_KEY_RE = re.compile(r"^[a-zA-Z0-9_/.-]+$")


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    grant_config = context.get("grant_config", {})

    store_id = args.get("store_id", "")
    key = args.get("key", "")

    # --- 入力バリデーション ---
    if not store_id or not isinstance(store_id, str):
        return _error("Missing or invalid store_id", "validation_error")
    if not key or not isinstance(key, str):
        return _error("Missing or invalid key", "validation_error")

    # --- key セキュリティチェック ---
    validation = _validate_key(key)
    if validation is not None:
        return validation

    # --- Grant config: allowed_store_ids ---
    allowed = grant_config.get("allowed_store_ids", [])
    if allowed and store_id not in allowed:
        return _error("Store not in allowed_store_ids", "grant_denied")

    # --- Store 解決 ---
    store_root = _resolve_store_root(store_id)
    if store_root is None:
        return _error("Store not found: " + store_id, "store_not_found")

    # --- ファイルパス構築 + boundary チェック ---
    file_path = store_root / (key + ".json")
    file_path = Path(os.path.normpath(file_path))

    if not _is_path_within(file_path, store_root):
        return _error("Path traversal detected", "security_error")

    # --- 読み取り ---
    if not file_path.exists():
        return _error("Key not found: " + key, "key_not_found")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            value = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return _error("Failed to read: " + str(e), "read_error")

    return {"success": True, "value": value}


def _validate_key(key: str) -> Any:
    """key のセキュリティバリデーション。問題があればエラー dict を返す。"""
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
    """store_id から store root Path を解決する。"""
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
    """target が boundary 配下にあるか判定する。"""
    try:
        resolved_target = target.resolve()
        resolved_boundary = boundary.resolve()
        resolved_target.relative_to(resolved_boundary)
        return True
    except (ValueError, OSError):
        return False


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}
