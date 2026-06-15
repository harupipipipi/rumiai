from __future__ import annotations

from typing import Any

from domain.company.message_router import CompanySlackRuntime
from domain.company.mention import CompanyMentionService
from domain.company.models import DEFAULT_CHANNEL_ID, timestamp
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.service import CompanyService
from domain.company.store import CompanyStore

from .creator_service import CreatorService
from .ids import slug_id, stable_short_id
from .mention_parser import parse_mentions
from .normalizers import (
    enrich_short_ids,
    lifecycle_update,
    normalize_goal_request,
    normalize_message_request,
    normalize_team_agent,
    normalize_team_channel,
)
from .pm_gate import gated_content, pm_gate_decision
from .prompt_context import build_channel_check_context
from .rich_policy import evaluate_rich_payload


class SubagentTeamService:
    """Slack/Discord-like Team Workspace facade over CompanySlackRuntime."""

    def __init__(
        self,
        *,
        company_store: CompanyStore | None = None,
        runtime_store: CompanyRuntimeStore | None = None,
    ) -> None:
        self.company_store = company_store or CompanyStore()
        self.runtime_store = runtime_store or CompanyRuntimeStore()

    def ensure_team(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = data if isinstance(data, dict) else {}
        company_id = str(data.get("company_id") or data.get("id") or "").strip()
        conversation_id = str(data.get("conversation_id") or "").strip()
        if company_id:
            company = self.company_store.get_company(company_id)
            if company is None and data.get("bootstrap"):
                company = CompanyService(self.company_store).create_company(
                    {
                        "id": company_id,
                        "name": data.get("name") or "Team Workspace",
                        "description": data.get("description") or "Creator-managed subagent team workspace.",
                        "metadata": {"subagent_team": True, **(data.get("metadata") if isinstance(data.get("metadata"), dict) else {})},
                    }
                )
            return {"company_id": company_id, "company": company, "bootstrapped": company is not None}
        if conversation_id:
            return CompanyService(self.company_store).status_for_conversation(
                conversation_id,
                bootstrap=bool(data.get("bootstrap", True)),
            )
        return CompanyService(self.company_store).status()

    def status(self, company_id: str) -> dict[str, Any] | None:
        company = self.company_store.get_company(company_id)
        if company is None:
            return None
        tasks, _ = self.runtime_store.list_tasks(company_id, limit=100)
        runs = self.runtime_store.list_run_links(company_id, limit=100)
        inbox = self.runtime_store.list_inbox(company_id, limit=100)
        return {
            "company": company,
            "runtime": "CompanySlackRuntime",
            "stats": self.runtime_store.stats(company_id),
            "open_tasks": [task for task in tasks if str(task.get("status")) not in {"completed", "cancelled", "failed"}],
            "runs": runs,
            "inbox": inbox,
            "policy": {
                "direct_tool_execution": False,
                "routing": "agent.delegate",
                "client_approved_flags_trusted": False,
            },
        }

    def list_channels(self, company_id: str) -> list[dict[str, Any]] | None:
        channels = self.company_store.list_channels(company_id)
        if channels is None:
            return None
        return enrich_short_ids(channels, prefix="ch")

    def get_channel(self, company_id: str, channel_id: str) -> dict[str, Any] | None:
        channel = self.company_store.get_channel(company_id, channel_id)
        if channel is None:
            return None
        return enrich_short_ids([channel], prefix="ch")[0]

    def upsert_channel(self, company_id: str, data: dict[str, Any], *, actor_id: str = "creator") -> dict[str, Any] | None:
        existing = self.list_channels(company_id) or []
        channel = normalize_team_channel(data, existing_short_ids=[str(item.get("short_id")) for item in existing])
        channel["metadata"] = lifecycle_update(channel.get("metadata"), state="active", actor_id=actor_id)
        return self.company_store.upsert_channel(company_id, channel)

    def archive_channel(self, company_id: str, channel_id: str, *, actor_id: str = "creator") -> dict[str, Any] | None:
        channel = self.company_store.get_channel(company_id, channel_id)
        if channel is None:
            return None
        channel["metadata"] = lifecycle_update(channel.get("metadata"), state="archived", actor_id=actor_id)
        channel["visibility"] = "archived"
        return self.company_store.upsert_channel(company_id, channel)

    def channel_check(self, company_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        return build_channel_check_context(
            company_id,
            channel_id=str(data.get("channel_id") or DEFAULT_CHANNEL_ID),
            thread_id=data.get("thread_id"),
            limit=int(data.get("limit") if isinstance(data.get("limit"), int) else 20),
            company_store=self.company_store,
            runtime_store=self.runtime_store,
        )

    def list_agents(self, company_id: str) -> list[dict[str, Any]] | None:
        agents = self.company_store.list_agents(company_id)
        if agents is None:
            return None
        return enrich_short_ids(agents, prefix="ag", id_key="agent_id")

    def get_agent(self, company_id: str, agent_id: str) -> dict[str, Any] | None:
        agent = self.company_store.get_agent(company_id, agent_id)
        if agent is None:
            return None
        return enrich_short_ids([agent], prefix="ag", id_key="agent_id")[0]

    def upsert_agent(self, company_id: str, data: dict[str, Any], *, actor_id: str = "creator") -> dict[str, Any] | None:
        existing = self.list_agents(company_id) or []
        agent = normalize_team_agent(data, existing_short_ids=[str(item.get("short_id")) for item in existing])
        agent["metadata"] = lifecycle_update(agent.get("metadata"), state="active", actor_id=actor_id)
        return self.company_store.upsert_agent(company_id, agent)

    def archive_agent(self, company_id: str, agent_id: str, *, actor_id: str = "creator") -> dict[str, Any] | None:
        agent = self.company_store.get_agent(company_id, agent_id)
        if agent is None:
            return None
        agent["status"] = "archived"
        agent["metadata"] = lifecycle_update(agent.get("metadata"), state="archived", actor_id=actor_id)
        return self.company_store.upsert_agent(company_id, agent)

    def list_messages(self, company_id: str, data: dict[str, Any]) -> tuple[list[dict[str, Any]], int] | None:
        if self.company_store.get_company(company_id) is None:
            return None
        limit = int(data.get("limit") if isinstance(data.get("limit"), int) else 50)
        offset = int(data.get("offset") if isinstance(data.get("offset"), int) else 0)
        return self.runtime_store.list_messages(
            company_id,
            channel_id=data.get("channel_id"),
            thread_id=data.get("thread_id"),
            limit=max(1, limit),
            offset=max(0, offset),
        )

    def send_message(self, company_id: str, data: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if self.company_store.get_company(company_id) is None:
            return None
        message = normalize_message_request(data)
        rich = evaluate_rich_payload({**data, "content": message["content"]})
        target_agent_ids = self._resolve_target_agent_ids(
            company_id,
            explicit=message["target_agent_ids"],
            content=message["content"],
        )
        gate = pm_gate_decision(
            sender_id=message["sender_id"],
            content=message["content"],
            target_agent_ids=target_agent_ids,
            rich_requested=rich["requested"],
            action=str(data.get("action") or "message"),
        )
        routed_content = gated_content(content=rich["content"], sender_id=message["sender_id"], gate=gate)
        metadata = {
            **message["metadata"],
            "subagent_team": {
                "parsed": message["parsed"],
                "rich": rich,
                "pm_gate": gate,
                "original_content": message["content"],
                "client_approved_ignored": "approved" in data,
            },
        }
        if rich["rich_payload"]:
            metadata["rich_payload"] = rich["rich_payload"]
        if rich["attachments"]:
            metadata["attachments"] = rich["attachments"]
        return CompanySlackRuntime(company_store=self.company_store, runtime_store=self.runtime_store).post_message(
            company_id,
            content=routed_content,
            sender_id=message["sender_id"],
            channel_id=message["channel_id"],
            thread_id=message["thread_id"],
            target_agent_ids=gate["target_agent_ids"],
            metadata=metadata,
            context=context or {},
        )

    def _resolve_target_agent_ids(self, company_id: str, *, explicit: list[str], content: str) -> list[str]:
        resolved: list[str] = []
        mention_service = CompanyMentionService(self.company_store)
        if explicit:
            explicit_resolution = mention_service.resolve(company_id, explicit) or {}
            resolved.extend(str(item) for item in explicit_resolution.get("resolved_agent_ids") or [])
            resolved.extend(
                str(item).strip().lstrip("@")
                for item in explicit_resolution.get("unresolved") or []
                if str(item).strip()
            )
        content_resolution = mention_service.resolve(company_id, content) or {}
        resolved.extend(str(item) for item in content_resolution.get("resolved_agent_ids") or [])
        return _dedupe(resolved)

    def parse_message(self, content: str) -> dict[str, Any]:
        return parse_mentions(content)

    def rich_preview(self, data: dict[str, Any]) -> dict[str, Any]:
        return evaluate_rich_payload(data)

    def creator_preview(self, company_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        return CreatorService(company_store=self.company_store, runtime_store=self.runtime_store).preview(company_id, data)

    def creator_request(self, company_id: str, data: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return CreatorService(company_store=self.company_store, runtime_store=self.runtime_store).request(
            company_id,
            data,
            context=context or {},
        )

    def list_goals(self, company_id: str, data: dict[str, Any]) -> tuple[list[dict[str, Any]], int] | None:
        if self.company_store.get_company(company_id) is None:
            return None
        limit = int(data.get("limit") if isinstance(data.get("limit"), int) else 50)
        offset = int(data.get("offset") if isinstance(data.get("offset"), int) else 0)
        tasks, total = self.runtime_store.list_tasks(company_id, limit=max(1, limit * 2), offset=max(0, offset))
        goals = [task for task in tasks if _is_goal(task)]
        return enrich_short_ids(goals[:limit], prefix="goal", id_key="task_id"), total

    def get_goal(self, company_id: str, goal_id: str) -> dict[str, Any] | None:
        task = self.runtime_store.get_task(goal_id, company_id=company_id)
        if task is None or not _is_goal(task):
            return None
        return enrich_short_ids([task], prefix="goal", id_key="task_id")[0]

    def create_goal(self, company_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if self.company_store.get_company(company_id) is None:
            return None
        goal = normalize_goal_request(data)
        sender_id = str(data.get("sender_id") or data.get("actor_id") or "user")
        gate = pm_gate_decision(
            sender_id=sender_id,
            content=goal["description"] or goal["title"],
            target_agent_ids=goal["target_agent_ids"],
            action="create_goal",
        )
        description = goal["description"]
        targets = goal["target_agent_ids"]
        if gate["requires_pm"]:
            description = gated_content(content=description or goal["title"], sender_id=sender_id, gate=gate)
            targets = gate["target_agent_ids"]
        return self.runtime_store.create_task(
            company_id,
            title=goal["title"],
            description=description,
            target_agent_ids=targets or ["project_manager"],
            source="goal",
            status=goal["status"],
            priority=goal["priority"],
            channel_id=goal["channel_id"] or DEFAULT_CHANNEL_ID,
            thread_id=goal["thread_id"],
            metadata={**goal["metadata"], "pm_gate": gate},
        )

    def update_goal(self, company_id: str, goal_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        if self.company_store.get_company(company_id) is None:
            return None
        clean = dict(updates or {})
        metadata = clean.get("metadata") if isinstance(clean.get("metadata"), dict) else {}
        if "status" in clean:
            metadata = lifecycle_update(metadata, state=str(clean["status"]), actor_id=str(clean.get("actor_id") or "creator"))
            clean["metadata"] = metadata
        return self.runtime_store.update_task(goal_id, clean, company_id=company_id)

    def list_dms(self, company_id: str) -> list[dict[str, Any]] | None:
        channels = self.list_channels(company_id)
        if channels is None:
            return None
        return [channel for channel in channels if _is_dm(channel)]

    def ensure_dm(self, company_id: str, data: dict[str, Any], *, actor_id: str = "creator") -> dict[str, Any] | None:
        participants = _dedupe([str(data.get("sender_id") or "user"), *list(data.get("participants") or data.get("target_agent_ids") or [])])
        if len(participants) < 2 and data.get("agent_id"):
            participants.append(str(data["agent_id"]))
        channel_id = str(data.get("dm_id") or data.get("channel_id") or _dm_channel_id(company_id, participants))
        channel = {
            "id": channel_id,
            "name": str(data.get("name") or "dm-" + "-".join(participants[:3])),
            "description": str(data.get("description") or "Direct message channel"),
            "visibility": "dm",
            "members": participants,
            "metadata": {"dm": True, "participants": participants},
        }
        return self.upsert_channel(company_id, channel, actor_id=actor_id)

    def send_dm(self, company_id: str, data: dict[str, Any], *, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        dm = self.ensure_dm(company_id, data, actor_id=str(data.get("sender_id") or data.get("actor_id") or "creator"))
        if dm is None:
            return None
        targets = data.get("target_agent_ids") if isinstance(data.get("target_agent_ids"), list) else []
        if data.get("agent_id") and str(data.get("agent_id")) not in targets:
            targets = [*targets, str(data.get("agent_id"))]
        return self.send_message(
            company_id,
            {
                **data,
                "channel_id": dm["id"],
                "target_agent_ids": targets,
                "metadata": {
                    **(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
                    "dm_id": dm["id"],
                },
            },
            context=context or {},
        )


def _is_goal(task: dict[str, Any]) -> bool:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return str(task.get("source") or "") == "goal" or bool(metadata.get("subagent_team_goal"))


def _is_dm(channel: dict[str, Any]) -> bool:
    metadata = channel.get("metadata") if isinstance(channel.get("metadata"), dict) else {}
    return str(channel.get("visibility") or "") == "dm" or bool(metadata.get("dm"))


def _dm_channel_id(company_id: str, participants: list[str]) -> str:
    seed = str(company_id) + ":" + ",".join(sorted(participants))
    return "dm_" + stable_short_id("dm", seed).split("_", 1)[-1]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = slug_id(str(value or "").strip().lstrip("@"), fallback="")
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
