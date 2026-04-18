"""setup HTTP handlers."""

from __future__ import annotations

from typing import Any, Dict

from ..di_container import get_container
from ..pack_function_runtime import invoke_pack_function
from ..setup_pack import get_setup_pack_manager


class SetupHandlersMixin:
    @staticmethod
    def _pack_function_exists(pack_id: str, function_id: str) -> bool:
        if not pack_id:
            return False
        function_registry = get_container().get_or_none("function_registry")
        if function_registry is None:
            return False
        qualified_name = (
            function_id if ":" in function_id else f"{pack_id}:{function_id}"
        )
        return function_registry.get(qualified_name) is not None

    def _get_pack_migration_status(self, pack_id: str) -> Dict[str, Any] | None:
        if not self._pack_function_exists(pack_id, "get_migration_status"):
            return None
        status = invoke_pack_function(pack_id, "get_migration_status")
        payload = dict(status) if isinstance(status, dict) else {"result": status}
        payload.setdefault("needs_user_migration", False)
        payload["pack_id"] = pack_id
        payload["available"] = True
        return payload

    def _setup_list_packs(self) -> Dict[str, Any]:
        return get_setup_pack_manager().list_packs()

    def _setup_install_pack(self, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(body or {})
        setup_pack_ids = payload.get("setup_pack_ids")
        if setup_pack_ids is None:
            setup_pack_id = str(payload.get("setup_pack_id", "")).strip()
            if not setup_pack_id:
                return {"error": "setup_pack_id or setup_pack_ids is required", "status_code": 400}
            setup_pack_ids = setup_pack_id

        result = get_setup_pack_manager().install(setup_pack_ids)
        if "error" in result:
            return result

        active_target_pack_id = str(result.get("active_target_pack_id") or "")
        status = self._get_pack_migration_status(active_target_pack_id)
        if status is not None:
            migration_result = None
            if (
                status.get("needs_user_migration")
                and self._pack_function_exists(active_target_pack_id, "run_migration")
            ):
                migration_result = invoke_pack_function(active_target_pack_id, "run_migration")
            result["migration_pack_id"] = active_target_pack_id
            result["migration_status"] = (
                self._get_pack_migration_status(active_target_pack_id) or status
            )
            if migration_result is not None:
                result["migration"] = migration_result
        return result

    def _setup_grant_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return get_setup_pack_manager().grant_all_ok(setup_pack_id)

    def _setup_revoke_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return get_setup_pack_manager().revoke_all_ok(setup_pack_id)

    def _setup_get_migration_status(self) -> Dict[str, Any]:
        selection = get_setup_pack_manager().get_selection()
        active_target_pack_id = str(selection.get("active_target_pack_id") or "")
        if not active_target_pack_id:
            return {
                "pack_id": None,
                "available": False,
                "needs_user_migration": False,
            }
        status = self._get_pack_migration_status(active_target_pack_id)
        if status is None:
            return {
                "pack_id": active_target_pack_id,
                "available": False,
                "needs_user_migration": False,
            }
        return status
