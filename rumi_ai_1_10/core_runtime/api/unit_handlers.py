"""Unit 管理ハンドラ Mixin"""
from __future__ import annotations

from typing import Optional

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class UnitHandlersMixin:
    """Unit の一覧・公開・実行ハンドラ"""

    def _units_list(self, store_id: Optional[str] = None) -> dict:
        """GET /api/units?store_id=xxx"""
        try:
            from ..unit_registry import get_unit_registry
            ur = get_unit_registry()
            if store_id:
                units = ur.list_units(store_id=store_id)
            else:
                units = ur.list_units()
            return {"units": units, "count": len(units)}
        except Exception as e:
            _log_internal_error("units_list", e)
            return {"units": [], "error": _SAFE_ERROR_MSG}

    def _units_publish(self, body: dict) -> dict:
        """POST /api/units/publish"""
        store_id = body.get("store_id", "")
        unit_id = body.get("unit_id", "")
        content = body.get("content")
        if not store_id or not unit_id:
            return {"success": False, "error": "Missing store_id or unit_id"}
        try:
            from ..unit_registry import get_unit_registry
            ur = get_unit_registry()
            result = ur.publish(
                store_id=store_id,
                unit_id=unit_id,
                content=content,
                metadata=body.get("metadata", {}),
            )
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return {"success": True, "store_id": store_id, "unit_id": unit_id}
        except Exception as e:
            _log_internal_error("units_publish", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _units_execute(self, body: dict) -> dict:
        """POST /api/units/execute"""
        store_id = body.get("store_id", "")
        unit_id = body.get("unit_id", "")
        if not store_id or not unit_id:
            return {"success": False, "error": "Missing store_id or unit_id"}
        try:
            from ..unit_executor import get_unit_executor
            ue = get_unit_executor()
            result = ue.execute(
                store_id=store_id,
                unit_id=unit_id,
                params=body.get("params", {}),
                caller_pack_id=body.get("caller_pack_id", "api_user"),
            )
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as e:
            _log_internal_error("units_execute", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
