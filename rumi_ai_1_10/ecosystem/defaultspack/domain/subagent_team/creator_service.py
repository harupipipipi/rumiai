from __future__ import annotations

from typing import Any

from domain.company.models import DEFAULT_CHANNEL_ID
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.store import CompanyStore

from .normalizers import normalize_goal_request, normalize_message_request
from .pm_gate import gated_content, pm_gate_decision
from .rich_policy import evaluate_rich_payload


class CreatorService:
    """Decision previews and requests for creator-managed team lifecycle."""

    def __init__(
        self,
        *,
        company_store: CompanyStore | None = None,
        runtime_store: CompanyRuntimeStore | None = None,
    ) -> None:
        self.company_store = company_store or CompanyStore()
        self.runtime_store = runtime_store or CompanyRuntimeStore()

    def preview(self, company_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if self.company_store.get_company(company_id) is None:
            return None
        action = str(data.get("action") or "message").lower()
        message = normalize_message_request(data)
        rich = evaluate_rich_payload({**data, "content": message["content"]})
        gate = pm_gate_decision(
            sender_id=message["sender_id"],
            content=message["content"],
            target_agent_ids=message["target_agent_ids"] or message["parsed"]["agent_mentions"],
            rich_requested=rich["requested"],
            action=action,
        )
        route_content = gated_content(content=rich["content"], sender_id=message["sender_id"], gate=gate)
        return {
            "action": action,
            "company_id": str(company_id),
            "will_execute_tools": False,
            "routing": {
                "runtime": "CompanySlackRuntime",
                "route": "agent.delegate",
                "direct_tool_execution": False,
                "target_agent_ids": gate["target_agent_ids"],
            },
            "pm_gate": gate,
            "rich": rich,
            "message": {
                "channel_id": message["channel_id"],
                "thread_id": message["thread_id"],
                "sender_id": message["sender_id"],
                "content": route_content,
                "original_content": message["content"],
            },
            "lifecycle": {
                "managed_by": "creator",
                "store": "CompanyStore/CompanyRuntimeStore",
                "approval_bypass": False,
            },
        }

    def request(self, company_id: str, data: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        preview = self.preview(company_id, data)
        if preview is None:
            return None
        action = str(preview["action"])
        if action in {"message", "request", "delegate", "route"}:
            from .service import SubagentTeamService

            return {
                "preview": preview,
                "result": SubagentTeamService(
                    company_store=self.company_store,
                    runtime_store=self.runtime_store,
                ).send_message(company_id, data, context=context or {}),
            }
        if action in {"create_goal", "goal"}:
            goal = normalize_goal_request(data)
            gate = preview["pm_gate"]
            if gate.get("requires_pm"):
                goal["description"] = gated_content(
                    content=goal["description"] or goal["title"],
                    sender_id=preview["message"]["sender_id"],
                    gate=gate,
                )
                goal["target_agent_ids"] = gate["target_agent_ids"]
            task = self.runtime_store.create_task(
                company_id,
                title=goal["title"],
                description=goal["description"],
                target_agent_ids=goal["target_agent_ids"] or ["project_manager"],
                source="goal",
                status=goal["status"],
                priority=goal["priority"],
                channel_id=goal["channel_id"] or DEFAULT_CHANNEL_ID,
                thread_id=goal["thread_id"],
                metadata={**goal["metadata"], "creator_preview": preview},
            )
            return {"preview": preview, "goal": task}
        return {"preview": preview, "result": {"status": "preview_only", "action": action}}
