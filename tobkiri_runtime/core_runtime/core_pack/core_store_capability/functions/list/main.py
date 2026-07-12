"""
store.list - Built-in Capability Handler

Store 内のキーを列挙する。
ページネーション対応: limit, cursor パラメータで制御。
オプションの prefix フィルタでキーを絞り込める。

後方互換: limit/cursor を指定しなければ従来通り全件返却。

セキュリティ:
- grant_config.allowed_store_ids で制限
- store root 外のファイルは返さない
"""

from __future__ import annotations

from typing import Any, Dict


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    grant_config = context.get("grant_config", {})

    store_id = args.get("store_id", "")
    prefix = args.get("prefix", "")
    limit = args.get("limit")
    cursor = args.get("cursor")

    # --- 入力バリデーション ---
    if not store_id or not isinstance(store_id, str):
        return _error("Missing or invalid store_id", "validation_error")

    # --- Grant config: allowed_store_ids ---
    allowed = grant_config.get("allowed_store_ids", [])
    if allowed and store_id not in allowed:
        return _error("Store not in allowed_store_ids", "grant_denied")

    # --- limit バリデーション ---
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return _error("Invalid limit (must be integer)", "validation_error")

    # --- cursor バリデーション ---
    if cursor is not None and not isinstance(cursor, str):
        return _error("Invalid cursor (must be string)", "validation_error")

    # --- StoreRegistry の list_keys を呼び出す ---
    try:
        from core_runtime.store_registry import get_store_registry
        registry = get_store_registry()
        result = registry.list_keys(
            store_id=store_id,
            prefix=prefix or "",
            limit=limit,
            cursor=cursor,
        )
    except Exception as e:
        return _error(f"Failed to list keys: {e}", "internal_error")

    return result


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}
