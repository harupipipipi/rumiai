"""
store.cas - Built-in Capability Handler

Compare-And-Swap: 楽観的排他制御を提供する。
expected_value が現在値と一致する場合のみ new_value で上書きする。

セキュリティ:
- grant_config.allowed_store_ids で制限
- key の '..' 即拒否 + 安全文字チェック
- ファイルレベルロック (fcntl.flock) で排他制御
- Linux/macOS のみ対応
"""

from __future__ import annotations

import re
from typing import Any, Dict


_SAFE_KEY_RE = re.compile(r"^[a-zA-Z0-9_/.-]+$")


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    grant_config = context.get("grant_config", {})
    principal_id = context.get("principal_id", "")

    store_id = args.get("store_id", "")
    key = args.get("key", "")
    expected_value = args.get("expected_value")
    new_value = args.get("new_value")

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

    # --- CAS 実行 ---
    try:
        from core_runtime.store_registry import get_store_registry
        registry = get_store_registry()
        result = registry.cas(
            store_id=store_id,
            key=key,
            expected_value=expected_value,
            new_value=new_value,
        )
    except NotImplementedError as e:
        return _error(str(e), "not_supported")
    except Exception as e:
        return _error(f"CAS execution failed: {e}", "internal_error")

    # 監査ログ
    if result.get("success"):
        _audit_cas(principal_id, store_id, key, True)
    else:
        _audit_cas(
            principal_id, store_id, key, False,
            error_type=result.get("error_type", "unknown"),
        )

    return result


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


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}


def _audit_cas(
    principal_id: str,
    store_id: str,
    key: str,
    success: bool,
    error_type: str = "",
) -> None:
    try:
        from core_runtime.audit_logger import get_audit_logger
        audit = get_audit_logger()
        audit.log_permission_event(
            pack_id=principal_id,
            permission_type="capability",
            action="store_cas",
            success=success,
            details={
                "store_id": store_id,
                "key": key,
                "error_type": error_type,
            },
        )
    except Exception:
        pass
