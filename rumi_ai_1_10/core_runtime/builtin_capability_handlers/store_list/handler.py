"""
store.list - Built-in Capability Handler

Store 内の全キーを列挙する。
オプションの prefix フィルタでキーを絞り込める。

セキュリティ:
- grant_config.allowed_store_ids で制限
- store root 外のファイルは返さない
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    grant_config = context.get("grant_config", {})

    store_id = args.get("store_id", "")
    prefix = args.get("prefix", "")

    # --- 入力バリデーション ---
    if not store_id or not isinstance(store_id, str):
        return _error("Missing or invalid store_id", "validation_error")

    # --- Grant config: allowed_store_ids ---
    allowed = grant_config.get("allowed_store_ids", [])
    if allowed and store_id not in allowed:
        return _error("Store not in allowed_store_ids", "grant_denied")

    # --- Store 解決 ---
    store_root = _resolve_store_root(store_id)
    if store_root is None:
        return _error("Store not found: " + store_id, "store_not_found")

    # --- キー列挙 ---
    keys = _list_keys(store_root, prefix)

    return {"success": True, "keys": keys}


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


def _list_keys(store_root: Path, prefix: str) -> List[str]:
    """store_root 配下の .json ファイルからキー名を導出する。"""
    keys: List[str] = []
    try:
        for json_file in sorted(store_root.rglob("*.json")):
            if not json_file.is_file():
                continue
            # store_root からの相対パスをキー名に変換
            try:
                rel = json_file.relative_to(store_root)
            except ValueError:
                continue
            # .json 拡張子を除去
            key = str(rel.with_suffix("")).replace("\\", "/")
            if prefix and not key.startswith(prefix):
                continue
            keys.append(key)
    except OSError:
        pass
    return keys


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}
