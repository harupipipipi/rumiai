from __future__ import annotations

from typing import Any

from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.store import CompanyStore

from .models import public_agent, public_channel, public_message
from .rich_policy import evaluate_rich_policy


class SubagentStatusAggregator:
    def __init__(self, *, company_store: CompanyStore | None = None, runtime_store: CompanyRuntimeStore | None = None) -> None:
        self.company_store = company_store or CompanyStore()
        self.runtime_store = runtime_store or CompanyRuntimeStore()

    def aggregate(self, company_id: str, *, channel_id: str | None = None, short_id: str | None = None) -> dict[str, Any]:
        company = self.company_store.get_company(company_id)
        if company is None:
            return {"status": "not_found", "company_id": company_id}
        agents = [public_agent(agent) for agent in self.company_store.list_agents(company_id) or []]
        agents_by_id = {agent["id"]: raw for agent, raw in zip(agents, self.company_store.list_agents(company_id) or [])}
        channels = [
            public_channel(channel, agents_by_id)
            for channel in self.company_store.list_channels(company_id) or []
        ]
        if channel_id:
            channels = [channel for channel in channels if channel["id"] == channel_id]
        if short_id:
            agents = [agent for agent in agents if agent.get("short_id") == short_id or agent.get("id") == short_id]
        messages, total_messages = self.runtime_store.list_messages(company_id, channel_id=channel_id, limit=80)
        tasks, total_tasks = self.runtime_store.list_tasks(company_id, limit=80)
        runs = self.runtime_store.list_run_links(company_id, limit=80)
        return {
            "status": "ok",
            "company_id": company_id,
            "company": company,
            "channels": channels,
            "agents": agents,
            "messages": [public_message(message, agents_by_id) for message in messages],
            "tasks": tasks,
            "runs": runs,
            "totals": {
                "channels": len(channels),
                "agents": len(agents),
                "messages": total_messages,
                "tasks": total_tasks,
                "runs": len(runs),
            },
            "rich": evaluate_rich_policy(company_id, requested_new_agents=0, settings=company.get("settings"), runtime_store=self.runtime_store),
        }
