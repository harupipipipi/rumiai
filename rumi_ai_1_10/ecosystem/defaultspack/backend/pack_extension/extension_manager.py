from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class PatchMode(str, Enum):
    REQUEST_EXTENSION = "request_extension"
    FORCED_PATCH = "forced_patch"


@dataclass
class ExtensionRequest:
    request_id: str
    mode: PatchMode
    pack_id: str
    target_pack_id: str
    summary: str
    status: str = "pending"
    created_at: float = field(default_factory=time.time)


class ExtensionManager:
    def __init__(self) -> None:
        self._requests: Dict[str, ExtensionRequest] = {}
        self._audit: List[Dict[str, Any]] = []

    def create_request(
        self,
        mode: PatchMode,
        pack_id: str,
        target_pack_id: str,
        summary: str,
    ) -> ExtensionRequest:
        request = ExtensionRequest(
            request_id=uuid.uuid4().hex,
            mode=mode,
            pack_id=pack_id,
            target_pack_id=target_pack_id,
            summary=summary,
        )
        self._requests[request.request_id] = request
        self._audit.append({"action": "create", "request_id": request.request_id, "mode": mode.value})
        return request

    def list_pending(self) -> List[ExtensionRequest]:
        return [request for request in self._requests.values() if request.status == "pending"]

    def approve(self, request_id: str) -> Optional[ExtensionRequest]:
        request = self._requests.get(request_id)
        if request is None:
            return None
        request.status = "approved"
        self._audit.append({"action": "approve", "request_id": request_id})
        return request

    def reject(self, request_id: str) -> Optional[ExtensionRequest]:
        request = self._requests.get(request_id)
        if request is None:
            return None
        request.status = "rejected"
        self._audit.append({"action": "reject", "request_id": request_id})
        return request

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit)
