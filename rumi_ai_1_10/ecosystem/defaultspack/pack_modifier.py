"""
pack_modifier.py - Pack modification modes (request extension / forced patch).

Both modes require user approval. Provides conflict resolution,
slot-based mounting, rollback, and audit logging.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModifyMode(str, enum.Enum):
    REQUEST_EXTENSION = "request_extension"
    FORCED_PATCH = "forced_patch"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ModifyRequest:
    request_id: str
    mode: ModifyMode
    pack_id: str
    target_slot: str
    description: str
    requester: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    rollback_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "mode": self.mode.value,
            "pack_id": self.pack_id,
            "target_slot": self.target_slot,
            "description": self.description,
            "requester": self.requester,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }


class PackModifier:
    """Manages pack modification requests (extension + forced patch)."""

    def __init__(self):
        self._requests: Dict[str, ModifyRequest] = {}
        self._active_slots: Dict[str, str] = {}  # slot -> pack_id
        self._audit: List[Dict[str, Any]] = []
        self._counter = 0

    def request_extension(
        self, pack_id: str, slot: str, description: str, requester: str,
    ) -> ModifyRequest:
        self._counter += 1
        req = ModifyRequest(
            request_id=f"ext-{self._counter}",
            mode=ModifyMode.REQUEST_EXTENSION,
            pack_id=pack_id,
            target_slot=slot,
            description=description,
            requester=requester,
        )
        self._requests[req.request_id] = req
        self._log("request_extension", req)
        return req

    def forced_patch(
        self, pack_id: str, slot: str, description: str, requester: str,
    ) -> ModifyRequest:
        self._counter += 1
        req = ModifyRequest(
            request_id=f"patch-{self._counter}",
            mode=ModifyMode.FORCED_PATCH,
            pack_id=pack_id,
            target_slot=slot,
            description=description,
            requester=requester,
        )
        self._requests[req.request_id] = req
        self._log("forced_patch", req)
        return req

    def approve(self, request_id: str, approver: str) -> bool:
        req = self._requests.get(request_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False
        # Check slot conflicts
        if req.target_slot in self._active_slots:
            existing = self._active_slots[req.target_slot]
            if req.mode == ModifyMode.FORCED_PATCH:
                req.rollback_data = {"previous_pack": existing}
            else:
                logger.warning("Slot '%s' conflict: %s vs %s", req.target_slot, existing, req.pack_id)
                return False
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = time.time()
        req.resolved_by = approver
        self._active_slots[req.target_slot] = req.pack_id
        self._log("approved", req)
        return True

    def reject(self, request_id: str, approver: str) -> bool:
        req = self._requests.get(request_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False
        req.status = ApprovalStatus.REJECTED
        req.resolved_at = time.time()
        req.resolved_by = approver
        self._log("rejected", req)
        return True

    def rollback(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req is None or req.status != ApprovalStatus.APPROVED:
            return False
        if req.rollback_data and "previous_pack" in req.rollback_data:
            self._active_slots[req.target_slot] = req.rollback_data["previous_pack"]
        else:
            self._active_slots.pop(req.target_slot, None)
        self._log("rollback", req)
        return True

    def get_active_slots(self) -> Dict[str, str]:
        return dict(self._active_slots)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit)

    def _log(self, action: str, req: ModifyRequest) -> None:
        self._audit.append({
            "action": action,
            "request": req.to_dict(),
            "timestamp": time.time(),
        })
