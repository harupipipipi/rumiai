"""Pack 管理ハンドラ Mixin"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG


class PackHandlersMixin:
    """Pack 承認 / スキャン / reject 関連のハンドラ"""

    def _get_all_packs(self) -> list:
        if not self.approval_manager:
            return []
        packs = self.approval_manager.scan_packs()
        return [
            {
                "pack_id": p,
                "status": self.approval_manager.get_status(p).value if self.approval_manager.get_status(p) else "unknown"
            }
            for p in packs
        ]

    def _get_pending_packs(self) -> list:
        if not self.approval_manager:
            return []
        return self.approval_manager.get_pending_packs()

    def _get_pack_status(self, pack_id: str) -> Optional[dict]:
        if not self.approval_manager:
            return None
        status = self.approval_manager.get_status(pack_id)
        if not status:
            return None
        approval = self.approval_manager.get_approval(pack_id)
        return {
            "pack_id": pack_id,
            "status": status.value,
            "approval": asdict(approval) if approval else None
        }

    def _scan_packs(self) -> dict:
        if not self.approval_manager:
            return {"scanned": 0}
        packs = self.approval_manager.scan_packs()
        return {"scanned": len(packs), "packs": packs}

    def _approve_pack(self, pack_id: str) -> dict:
        if not self.approval_manager:
            return {"success": False, "error": "ApprovalManager not initialized"}
        result = self.approval_manager.approve(pack_id)
        return {"success": result.success, "error": result.error}

    def _reject_pack(self, pack_id: str, reason: str) -> dict:
        if not self.approval_manager:
            return {"success": False}
        self.approval_manager.reject(pack_id, reason)
        return {"success": True, "pack_id": pack_id, "reason": reason}
