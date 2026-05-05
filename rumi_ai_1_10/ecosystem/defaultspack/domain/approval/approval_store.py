from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .store import ApprovalStore as TokenApprovalStore
from .store import approval_store_path, classify_approval_risk, redact_secrets


class ApprovalStore(TokenApprovalStore):
    """Compatibility facade for approval route blocks.

    The canonical implementation lives in domain.approval.store. This facade
    keeps the route-block API small while preserving hashed server tokens.
    """

    def __init__(self, root: Path | None = None) -> None:
        override = os.environ.get("RUMI_DEFAULTSPACK_APPROVALS_PATH", "").strip()
        if override:
            path = Path(override)
        elif root is not None:
            path = Path(root) / "user_data" / "shared" / "approvals" / "tool_approvals.json"
        else:
            path = approval_store_path()
        super().__init__(path)

    def create(
        self,
        *,
        tool_name: str,
        action: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        profile_id: str | None = None,
        reason: str = "",
        artifact_refs: list[str] | None = None,
        expires_in_seconds: int = 300,
    ) -> dict[str, Any]:
        risk = classify_approval_risk(action, payload)
        request = self.request(
            action,
            payload or {},
            risk_level=str(risk.get("risk_level") or "medium"),
            reason=reason or str(risk.get("reason") or ""),
            ttl_seconds=expires_in_seconds,
        )
        self._merge_metadata(
            str(request["approval_id"]),
            {
                "tool_name": tool_name,
                "agent_id": agent_id,
                "profile_id": profile_id,
                "artifact_refs": artifact_refs or [],
            },
        )
        return self.get(str(request["approval_id"])) or request

    def approve(
        self,
        approval_id: str,
        *,
        scope: str = "once",
        session_id: str = "",
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        if scope == "session":
            result = self.approve_session(
                approval_id,
                session_id=session_id,
                ttl_seconds=int(ttl_seconds or 3600),
            )
        else:
            result = self.approve_once(approval_id, ttl_seconds=int(ttl_seconds or 300))
        if not result.get("ok"):
            raise ValueError(str(result.get("error") or "approval failed"))
        return result

    def deny(self, approval_id: str, reason: str = "") -> dict[str, Any]:
        result = super().deny(approval_id, reason=reason)
        if not result.get("ok"):
            raise ValueError(str(result.get("error") or "approval failed"))
        return result["approval"]

    def consume(
        self,
        approval_id: str | None = None,
        token: str | None = None,
        *,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        return super().consume(
            approval_id=str(approval_id or ""),
            approval_token=str(token or ""),
            action=action,
            payload=payload or {},
            allow_legacy_token=False,
        )

    def _merge_metadata(self, approval_id: str, metadata: dict[str, Any]) -> None:
        data = self._load()
        record = data["requests"].get(approval_id)
        if not isinstance(record, dict):
            return
        for key, value in metadata.items():
            if value not in (None, "", []):
                record[key] = value
        self._save(data)
