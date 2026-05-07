from __future__ import annotations

from typing import Any

from blocks._common import gen_id

from .run_store import AgentRunStore


class ApprovalService:
    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def request(self, run_id: str, tool_call_id: str, *, reviewer: str = "user", reason: str = "") -> str:
        approval_id = gen_id("approval_")
        self.store.record_approval(
            approval_id,
            run_id,
            tool_call_id,
            reviewer=reviewer,
            status="pending",
            reason=reason,
        )
        self.store.add_event(run_id, "approval_requested", {"approval_id": approval_id, "tool_call_id": tool_call_id})
        return approval_id

    def decide(self, approval_id: str, run_id: str, tool_call_id: str, status: str, decision: dict[str, Any]) -> None:
        self.store.record_approval(
            approval_id,
            run_id,
            tool_call_id,
            status=status,
            decision=decision,
        )
        self.store.add_event(run_id, "approval_decided", {"approval_id": approval_id, "status": status})
