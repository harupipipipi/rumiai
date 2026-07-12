from __future__ import annotations

from typing import Any

from .store import CompanyStore


class CompanyAgentStore:
    def __init__(self, store: CompanyStore | None = None) -> None:
        self.store = store or CompanyStore()

    def list(self, company_id: str) -> list[dict[str, Any]] | None:
        return self.store.list_agents(company_id)

    def get(self, company_id: str, agent_id: str) -> dict[str, Any] | None:
        return self.store.get_agent(company_id, agent_id)

    def upsert(self, company_id: str, agent: dict[str, Any]) -> dict[str, Any] | None:
        return self.store.upsert_agent(company_id, agent)

    def remove(self, company_id: str, agent_id: str) -> bool:
        return self.store.remove_agent(company_id, agent_id)
