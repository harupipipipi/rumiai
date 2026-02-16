"""Secrets 管理ハンドラ Mixin"""
from __future__ import annotations

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class SecretsHandlersMixin:
    """シークレット一覧・登録・削除ハンドラ"""

    def _secrets_list(self) -> dict:
        """GET /api/secrets"""
        try:
            from ..secrets_store import get_secrets_store
            ss = get_secrets_store()
            entries = ss.list_secrets()
            return {"secrets": entries, "count": len(entries)}
        except Exception as e:
            _log_internal_error("secrets_list", e)
            return {"secrets": [], "error": _SAFE_ERROR_MSG}

    def _secrets_set(self, body: dict) -> dict:
        """POST /api/secrets/set"""
        pack_id = body.get("pack_id", "")
        key = body.get("key", "")
        value = body.get("value", "")
        if not pack_id or not key:
            return {"success": False, "error": "Missing pack_id or key"}
        try:
            from ..secrets_store import get_secrets_store
            ss = get_secrets_store()
            ss.set_secret(pack_id, key, value)
            return {"success": True, "pack_id": pack_id, "key": key}
        except Exception as e:
            _log_internal_error("secrets_set", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _secrets_delete(self, body: dict) -> dict:
        """POST /api/secrets/delete"""
        pack_id = body.get("pack_id", "")
        key = body.get("key", "")
        if not pack_id or not key:
            return {"success": False, "error": "Missing pack_id or key"}
        try:
            from ..secrets_store import get_secrets_store
            ss = get_secrets_store()
            ss.delete_secret(pack_id, key)
            return {"success": True, "pack_id": pack_id, "key": key}
        except Exception as e:
            _log_internal_error("secrets_delete", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
