"""Store 管理ハンドラ Mixin"""
from __future__ import annotations

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class StoreHandlersMixin:
    """Store の一覧・作成ハンドラ"""

    def _stores_list(self) -> dict:
        """GET /api/stores"""
        try:
            from ..store_registry import get_store_registry
            sr = get_store_registry()
            stores = sr.list_stores()
            return {"stores": stores, "count": len(stores)}
        except Exception as e:
            _log_internal_error("stores_list", e)
            return {"stores": [], "error": _SAFE_ERROR_MSG}

    def _stores_create(self, body: dict) -> dict:
        """POST /api/stores/create"""
        store_id = body.get("store_id", "")
        root_path = body.get("root_path", "")
        if not store_id:
            return {"success": False, "error": "Missing store_id"}
        if not root_path:
            root_path = f"user_data/stores/{store_id}"
        try:
            from ..store_registry import get_store_registry
            sr = get_store_registry()
            result = sr.create_store(
                store_id=store_id,
                root_path=root_path,
                created_by=body.get("created_by", "api_user"),
            )
            return result.to_dict()
        except Exception as e:
            _log_internal_error("stores_create", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
