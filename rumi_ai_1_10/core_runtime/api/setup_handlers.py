"""setup HTTP handlers."""

from __future__ import annotations

from typing import Any, Dict

from ..pack_function_runtime import invoke_pack_function
from ..setup_pack import get_setup_pack_manager


class SetupHandlersMixin:
    def _setup_list_packs(self) -> Dict[str, Any]:
        return get_setup_pack_manager().list_packs()

    def _setup_install_pack(self, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(body or {})
        setup_pack_id = str(payload.get("setup_pack_id", "")).strip()
        if not setup_pack_id:
            return {"error": "setup_pack_id is required", "status_code": 400}

        result = get_setup_pack_manager().install(setup_pack_id)
        if "error" in result:
            return result

        status = invoke_pack_function("defaultspack", "get_migration_status")
        migration_result = None
        if status.get("needs_user_migration"):
            migration_result = invoke_pack_function("defaultspack", "run_migration")
        result["migration_status"] = invoke_pack_function(
            "defaultspack", "get_migration_status"
        )
        if migration_result is not None:
            result["migration"] = migration_result
        return result

    def _setup_grant_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return get_setup_pack_manager().grant_all_ok(setup_pack_id)

    def _setup_revoke_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return get_setup_pack_manager().revoke_all_ok(setup_pack_id)

    def _setup_get_migration_status(self) -> Dict[str, Any]:
        return invoke_pack_function("defaultspack", "get_migration_status")
