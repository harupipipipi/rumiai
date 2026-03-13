"""
secrets.get - Built-in Capability Handler

Grant で許可された Secret の値をキー指定で取得する。

セキュリティ:
- grant_config.allowed_keys で明示的に許可されたキーのみアクセス可
- allowed_keys が空リストまたは未指定 → 全拒否 (fail-closed)
- 値はログ・監査・例外メッセージに絶対に含めない
- キーの存在有無を外部に漏らさない（存在しない / 削除済み / アクセス拒否 を同じエラーで返す）
- KEY_PATTERN (^[A-Z0-9_]{1,64}$) によるキー名バリデーション
- 監査ログには pack_id + key 名のみ記録（値は絶対に入れない）
"""

from __future__ import annotations

import re
from typing import Any, Dict


_KEY_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")

# キーの存在有無を漏らさない統一エラーメッセージ
_DENIED_MSG = "Access denied or secret not found"


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    principal_id = context.get("principal_id", "")
    grant_config = context.get("grant_config", {})

    key = args.get("key", "")

    # --- 入力バリデーション ---
    if not key or not isinstance(key, str):
        return _error("Missing or invalid key", "validation_error")

    if not _KEY_PATTERN.match(key):
        return _error(
            "Invalid key: must match ^[A-Z0-9_]{1,64}$",
            "validation_error",
        )

    # --- Grant config: allowed_keys (空 or 未指定 → 全拒否) ---
    allowed_keys = grant_config.get("allowed_keys", [])
    if not allowed_keys or not isinstance(allowed_keys, list):
        _audit_secrets_get(principal_id=principal_id, key=key, success=False)
        return _error(_DENIED_MSG, "access_denied")

    if key not in allowed_keys:
        _audit_secrets_get(principal_id=principal_id, key=key, success=False)
        return _error(_DENIED_MSG, "access_denied")

    # --- SecretsStore から値を取得 ---
    try:
        from core_runtime.secrets_store import get_secrets_store
        store = get_secrets_store()
        value = store._read_value(key)
    except Exception:
        # 内部エラーでも値やキー存在を漏らさない
        _audit_secrets_get(principal_id=principal_id, key=key, success=False)
        return _error(_DENIED_MSG, "access_denied")

    if value is None:
        # 存在しない / 削除済み — アクセス拒否と同じエラーで返す
        _audit_secrets_get(principal_id=principal_id, key=key, success=False)
        return _error(_DENIED_MSG, "access_denied")

    # --- 成功 ---
    _audit_secrets_get(principal_id=principal_id, key=key, success=True)
    return {"success": True, "value": value}


def _error(message: str, error_type: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "error_type": error_type}


def _audit_secrets_get(
    principal_id: str,
    key: str,
    success: bool,
) -> None:
    """監査ログに記録する。値は絶対に含めない。"""
    try:
        from core_runtime.audit_logger import get_audit_logger

        audit = get_audit_logger()
        audit.log_permission_event(
            pack_id=principal_id,
            permission_type="capability",
            action="secrets_get",
            success=success,
            details={
                "key": key,
            },
        )
    except Exception:
        pass
