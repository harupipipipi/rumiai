"""Pack ライフサイクル（import / apply / uninstall）ハンドラ Mixin"""
from __future__ import annotations

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class PackLifecycleHandlersMixin:
    """Pack の import / apply / uninstall ハンドラ"""

    def _pack_import(self, source_path: str, notes: str = "") -> dict:
        """POST /api/packs/import"""
        try:
            from ..pack_importer import get_pack_importer
            importer = get_pack_importer()
            result = importer.import_pack(source_path, notes=notes)
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            _log_internal_error("pack_import", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pack_apply(self, staging_id: str, mode: str = "replace") -> dict:
        """POST /api/packs/apply"""
        try:
            from ..pack_applier import get_pack_applier
            applier = get_pack_applier()
            result = applier.apply(staging_id, mode=mode)
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            _log_internal_error("pack_apply", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _uninstall_pack(self, pack_id: str) -> dict:
        """DELETE /api/packs/{pack_id}"""
        if self.container_orchestrator:
            self.container_orchestrator.stop_container(pack_id)
            self.container_orchestrator.remove_container(pack_id)

        if self.approval_manager:
            self.approval_manager.remove_approval(pack_id)

        if self.host_privilege_manager:
            self.host_privilege_manager.revoke_all(pack_id)

        return {"success": True, "pack_id": pack_id}
