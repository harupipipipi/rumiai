"""Store Sharing ハンドラ Mixin"""
from __future__ import annotations

from .._helpers import _log_internal_error, _SAFE_ERROR_MSG


class StoreShareHandlersMixin:
    """Store 共有 (#21) のハンドラ"""

    def _stores_shared_list(self) -> dict:
        """GET /api/stores/shared"""
        try:
            from ...store_sharing_manager import get_shared_store_manager
            ssm = get_shared_store_manager()
            entries = ssm.list_shared_stores()
            return {"entries": entries, "count": len(entries)}
        except Exception as e:
            _log_internal_error("stores_shared_list", e)
            return {"entries": [], "error": _SAFE_ERROR_MSG}

    def _stores_shared_approve(
        self, provider_pack_id: str, consumer_pack_id: str, store_id: str,
    ) -> dict:
        """POST /api/stores/shared/approve"""
        if not provider_pack_id or not consumer_pack_id or not store_id:
            return {
                "success": False,
                "error": "Missing provider_pack_id, consumer_pack_id, or store_id",
            }
        try:
            from ...store_sharing_manager import get_shared_store_manager
            ssm = get_shared_store_manager()
            return ssm.approve_sharing(provider_pack_id, consumer_pack_id, store_id)
        except Exception as e:
            _log_internal_error("stores_shared_approve", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _stores_shared_revoke(
        self, provider_pack_id: str, consumer_pack_id: str, store_id: str,
    ) -> dict:
        """POST /api/stores/shared/revoke"""
        if not provider_pack_id or not consumer_pack_id or not store_id:
            return {
                "success": False,
                "error": "Missing provider_pack_id, consumer_pack_id, or store_id",
            }
        try:
            from ...store_sharing_manager import get_shared_store_manager
            ssm = get_shared_store_manager()
            return ssm.revoke_sharing(provider_pack_id, consumer_pack_id, store_id)
        except Exception as e:
            _log_internal_error("stores_shared_revoke", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
