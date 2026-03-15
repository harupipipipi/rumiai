"""Pack 管理ハンドラ Mixin"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from .._helpers import _log_internal_error, _SAFE_ERROR_MSG


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

    def _approve_rule_pack(self, pack_id: str) -> dict:
        """rule Pack に対するルール拡張承認を実行する。"""
        if not self.approval_manager:
            return {"error": "ApprovalManager not initialized", "status_code": 500}
        if not hasattr(self.approval_manager, "approve_rule"):
            return {"error": "approve_rule not supported", "status_code": 501}
        result = self.approval_manager.approve_rule(pack_id)
        if result.success:
            return {"success": True, "pack_id": pack_id}
        return {"error": result.error, "status_code": 400}

    def _get_pack_dependencies(self, pack_id: str) -> dict:
        """Pack の依存関係ツリーを返す。"""
        if not self.approval_manager:
            return {"error": "ApprovalManager not initialized", "status_code": 500}

        # ecosystem.json を読み取る
        eco_data = {}
        if hasattr(self.approval_manager, "_read_ecosystem_data"):
            eco_data = self.approval_manager._read_ecosystem_data(pack_id)
        if not eco_data:
            return {"error": "Pack not found or ecosystem.json unreadable", "status_code": 404}

        try:
            from ...dependency_resolver import extract_dependencies
        except ImportError:
            from core_runtime.dependency_resolver import extract_dependencies

        deps = extract_dependencies(eco_data)
        pack_type = eco_data.get("pack_type", "application")
        runtime_type = eco_data.get("runtime_type", "python")
        provides_runtime = eco_data.get("provides_runtime", [])

        return {
            "pack_id": pack_id,
            "pack_type": pack_type,
            "runtime_type": runtime_type,
            "provides_runtime": provides_runtime,
            "depends_on": deps,
        }

    def _get_available_runtimes(self) -> dict:
        """現在利用可能なランタイム一覧を返す。

        承認済み rule Pack の provides_runtime を集約する。
        """
        if not self.approval_manager:
            return {"error": "ApprovalManager not initialized", "status_code": 500}

        runtimes = {}  # runtime_name -> list of provider pack_ids
        approved_ids = self.approval_manager.get_approved_pack_ids()

        for pid in approved_ids:
            eco_data = {}
            if hasattr(self.approval_manager, "_read_ecosystem_data"):
                eco_data = self.approval_manager._read_ecosystem_data(pid)
            pt = eco_data.get("pack_type", "application")
            if pt != "rule":
                continue
            # ルール拡張承認もチェック
            if hasattr(self.approval_manager, "is_rule_approved"):
                if not self.approval_manager.is_rule_approved(pid):
                    continue
            provides = eco_data.get("provides_runtime", [])
            if isinstance(provides, list):
                for rt in provides:
                    if isinstance(rt, str) and rt:
                        if rt not in runtimes:
                            runtimes[rt] = []
                        runtimes[rt].append(pid)

        return {"runtimes": runtimes}
