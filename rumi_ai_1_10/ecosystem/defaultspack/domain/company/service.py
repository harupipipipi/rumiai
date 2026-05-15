from __future__ import annotations

from typing import Any

from .dispatch import CompanyDispatchService
from .inbound_routes import CompanyInboundRouteService
from .mention import CompanyMentionService
from .migration import migrate_operations_company_state
from .models import (
    DEFAULT_COMPANY_DESCRIPTION,
    DEFAULT_COMPANY_ID,
    DEFAULT_COMPANY_NAME,
    DEFAULT_CONVERSATION_GROUP_ID,
    default_agents,
)
from .store import CompanyStore


class CompanyService:
    def __init__(self, store: CompanyStore | None = None) -> None:
        self.store = store or CompanyStore()

    def create_company(self, data: dict[str, Any]) -> dict[str, Any]:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        return self.store.create_company(
            company_id=data.get("id") or data.get("company_id"),
            name=name,
            description=str(data.get("description") or ""),
            settings=data.get("settings") if isinstance(data.get("settings"), dict) else None,
            agents=data.get("agents") if isinstance(data.get("agents"), (list, dict)) else None,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
            conversation_group_id=data.get("conversation_group_id"),
        )

    def get_company(self, company_id: str) -> dict[str, Any] | None:
        return self.store.get_company(company_id)

    def list_companies(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.store.list_companies(limit=limit, offset=offset)

    def update_company(self, company_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self.store.update_company(company_id, updates)

    def delete_company(self, company_id: str) -> bool:
        return self.store.delete_company(company_id)

    def bootstrap_default_company(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.store.ensure_company(
            company_id=DEFAULT_COMPANY_ID,
            name=DEFAULT_COMPANY_NAME,
            description=DEFAULT_COMPANY_DESCRIPTION,
            agents=default_agents(),
            metadata=metadata or {"profile_id": "defaultspack.operations_company"},
            conversation_group_id=(metadata or {}).get("conversation_group_id") or DEFAULT_CONVERSATION_GROUP_ID,
        )

    def status(self, company_id: str | None = None) -> dict[str, Any]:
        target_id = company_id or DEFAULT_COMPANY_ID
        company = self.store.get_company(target_id)
        if company is None and target_id == DEFAULT_COMPANY_ID:
            company = migrate_operations_company_state(store=self.store) or self.bootstrap_default_company()
        return {
            "bootstrapped": company is not None,
            "company_id": target_id,
            "company": company,
            "storage_file": str(self.store.storage_file),
        }

    def mention(self, company_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        content = str(data.get("content") or data.get("message") or "")
        return CompanyMentionService(self.store).create_message_task(
            company_id,
            content=content,
            sender_id=str(data.get("sender_id") or "user"),
            channel_id=str(data.get("channel_id") or "ops-company"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )

    def dispatch(self, company_id: str, task_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        return CompanyDispatchService(self.store).dispatch_task(
            company_id,
            task_id,
            requested_by=str(data.get("requested_by") or "system"),
            policy=data.get("policy") if isinstance(data.get("policy"), dict) else None,
        )

    def inbound_routes(self) -> CompanyInboundRouteService:
        return CompanyInboundRouteService(self.store)
