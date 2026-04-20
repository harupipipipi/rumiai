"""setup HTTP handlers."""

from __future__ import annotations

from typing import Any, Dict

from ..di_container import get_container
from ..pack_function_runtime import invoke_pack_function
from ..setup_pack import get_setup_pack_manager


class SetupHandlersMixin:
    @staticmethod
    def _pack_function_state(pack_id: str, function_id: str) -> Dict[str, Any]:
        if not pack_id:
            return {
                "exists": False,
                "registry_available": False,
                "reason": "pack_id_missing",
            }
        function_registry = get_container().get_or_none("function_registry")
        if function_registry is None:
            return {
                "exists": False,
                "registry_available": False,
                "reason": "function_registry_unavailable",
            }
        qualified_name = (
            function_id if ":" in function_id else f"{pack_id}:{function_id}"
        )
        if function_registry.get(qualified_name) is None:
            return {
                "exists": False,
                "registry_available": True,
                "reason": "function_not_registered",
            }
        return {
            "exists": True,
            "registry_available": True,
            "reason": None,
        }

    @classmethod
    def _pack_function_exists(cls, pack_id: str, function_id: str) -> bool:
        return bool(cls._pack_function_state(pack_id, function_id).get("exists"))

    def _get_pack_migration_status(self, pack_id: str) -> Dict[str, Any]:
        if not pack_id:
            return {
                "pack_id": None,
                "available": False,
                "needs_user_migration": False,
                "registry_available": False,
                "reason": "pack_id_missing",
            }
        function_state = self._pack_function_state(pack_id, "get_migration_status")
        if not function_state.get("exists"):
            return {
                "pack_id": pack_id,
                "available": False,
                "needs_user_migration": False,
                "registry_available": bool(function_state.get("registry_available")),
                "reason": function_state.get("reason"),
            }
        status = invoke_pack_function(pack_id, "get_migration_status")
        payload = dict(status) if isinstance(status, dict) else {"result": status}
        payload.setdefault("needs_user_migration", False)
        payload["pack_id"] = pack_id
        payload["available"] = True
        payload["registry_available"] = True
        payload["reason"] = None
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

        installed_target_pack_ids = [
            str(pack_id).strip()
            for pack_id in (result.get("installed_target_pack_ids") or [])
            if str(pack_id).strip()
        ]
        if not installed_target_pack_ids:
            active_target_pack_id = str(result.get("active_target_pack_id") or "").strip()
            if active_target_pack_id:
                installed_target_pack_ids = [active_target_pack_id]

        migration_statuses: Dict[str, Dict[str, Any]] = {}
        migrations: Dict[str, Any] = {}
        for target_pack_id in installed_target_pack_ids:
            status = self._get_pack_migration_status(target_pack_id)
            if (
                status.get("available")
                and status.get("needs_user_migration")
                and self._pack_function_exists(target_pack_id, "run_migration")
            ):
                migrations[target_pack_id] = invoke_pack_function(target_pack_id, "run_migration")
                status = self._get_pack_migration_status(target_pack_id)
            migration_statuses[target_pack_id] = status
        if migration_statuses:
            result["migration_statuses"] = migration_statuses
        if migrations:
            result["migrations"] = migrations
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
                "registry_available": False,
                "reason": "active_target_not_selected",
            }
        return self._get_pack_migration_status(active_target_pack_id)
