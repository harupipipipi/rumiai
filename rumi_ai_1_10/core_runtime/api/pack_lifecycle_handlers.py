"""Pack ライフサイクル ハンドラ Mixin"""
from __future__ import annotations

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class PackLifecycleHandlersMixin:
    """Pack アンインストール / インポート / 適用 のハンドラ"""

    def _uninstall_pack(self, pack_id: str) -> dict:
        if self.container_orchestrator:
            self.container_orchestrator.stop_container(pack_id)
            self.container_orchestrator.remove_container(pack_id)

        if self.approval_manager:
            self.approval_manager.remove_approval(pack_id)

        if self.host_privilege_manager:
            self.host_privilege_manager.revoke_all(pack_id)

        return {"success": True, "pack_id": pack_id}

    def _pack_import(self, source_path: str, notes: str = "") -> dict:
        try:
            from ..pack_importer import get_pack_importer
            importer = get_pack_importer()
            result = importer.import_pack(source_path, notes=notes)
            return result.to_dict()
        except Exception as e:
            _log_internal_error("pack_import", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}

    def _pack_apply(self, staging_id: str, mode: str = "replace") -> dict:
        try:
            from ..pack_importer import get_pack_importer
            importer = get_pack_importer()
            meta = importer.get_staging_meta(staging_id)
            if meta is None:
                return {"success": False, "error": f"Staging not found: {staging_id}"}

            from ..pack_applier import get_pack_applier
            applier = get_pack_applier()
            result = applier.apply_staging(staging_id, mode=mode)
            return result.to_dict() if hasattr(result, "to_dict") else result
        except Exception as e:
            _log_internal_error("pack_apply", e)
            return {"success": False, "error": _SAFE_ERROR_MSG}
