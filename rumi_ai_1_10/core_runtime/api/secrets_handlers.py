"""Secrets ハンドラ Mixin"""
from __future__ import annotations

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class SecretsHandlersMixin:
    """Secrets 管理 (list / set / delete) のハンドラ"""

    def _secrets_list(self) -> dict:
        try:
            from ..secrets_store import get_secrets_store
            store = get_secrets_store()
            keys = store.list_keys()
            return {
                "keys": [k.to_dict() for k in keys],
                "count": len(keys),
            }
        except Exception as e:
            _log_internal_error("secrets_list", e)
            return {"keys": [], "error": _SAFE_ERROR_MSG}

    def _secrets_set(self, body: dict) -> dict:
        key = body.get("key", "")
        value = body.get("value", "")
        if not key:
            return {"success": False, "error": "Missing 'key'"}
        if not isinstance(value, str):
            return {"success": False, "error": "'value' must be a string"}
        try:
            from ..secrets_store import get_secrets_store
            store = get_secrets_store()
            result = store.set_secret(key, value)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("secrets_set", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _secrets_delete(self, body: dict) -> dict:
        key = body.get("key", "")
        if not key:
            return {"success": False, "error": "Missing 'key'"}
        try:
            from ..secrets_store import get_secrets_store
            store = get_secrets_store()
            result = store.delete_secret(key)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("secrets_delete", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
