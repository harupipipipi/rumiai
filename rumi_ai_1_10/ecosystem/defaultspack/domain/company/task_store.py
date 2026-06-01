from __future__ import annotations

from typing import Any

from .runtime_store import CompanyRuntimeStore
from .store import CompanyStore


class CompanyTaskStore:
    def __init__(self, store: CompanyStore | None = None, runtime_store: CompanyRuntimeStore | None = None) -> None:
        self.store = store or CompanyStore()
        self.runtime_store = runtime_store or CompanyRuntimeStore()

    def create(
        self,
        company_id: str,
        *,
        title: str,
        description: str = "",
        target_agent_ids: list[str] | None = None,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if self.store.get_company(company_id) is None:
            return None
        return self.runtime_store.create_task(
            company_id,
            title=title,
            description=description,
            target_agent_ids=target_agent_ids,
            source=source,
            metadata=metadata,
        )

    def list(
        self,
        company_id: str,
        *,
        status: str | None = None,
        target_agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int] | None:
        if self.store.get_company(company_id) is None:
            return None
        return self.runtime_store.list_tasks(
            company_id,
            status=status,
            target_agent_id=target_agent_id,
            limit=limit,
            offset=offset,
        )

    def get(self, company_id: str, task_id: str) -> dict[str, Any] | None:
        if self.store.get_company(company_id) is None:
            return None
        return self.runtime_store.get_task(task_id, company_id=company_id)

    def update(self, company_id: str, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        if self.store.get_company(company_id) is None:
            return None
        return self.runtime_store.update_task(task_id, updates, company_id=company_id)
