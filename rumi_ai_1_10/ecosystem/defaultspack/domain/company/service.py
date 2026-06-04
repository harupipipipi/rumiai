from __future__ import annotations

import hashlib
import re
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
from .runtime_store import CompanyRuntimeStore
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

    def bootstrap_conversation_company(self, conversation_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            raise ValueError("conversation_id is required")
        existing = self.store.find_company_by_conversation_id(conversation_id)
        employee_model = _conversation_employee_model(conversation_id, metadata)
        merged_metadata = {
            "profile_id": "defaultspack.operations_company",
            "conversation_id": conversation_id,
            "source": "chat",
            "surface": "main_chat",
            "user_role": "president",
            "employee_model": employee_model,
            **(metadata or {}),
        }
        company_id = str(existing.get("id") if existing else _conversation_company_id(conversation_id))
        return self.store.ensure_company(
            company_id=company_id,
            name=str((metadata or {}).get("name") or "Executive Team"),
            description="Employee group delegated from the current chat.",
            agents=_default_agents_for_model(employee_model),
            metadata=merged_metadata,
            conversation_group_id=(metadata or {}).get("conversation_group_id") or "company:" + company_id,
        )

    def status(self, company_id: str | None = None) -> dict[str, Any]:
        target_id = company_id or DEFAULT_COMPANY_ID
        company = self.store.get_company(target_id)
        if company is None and target_id == DEFAULT_COMPANY_ID:
            company = migrate_operations_company_state(store=self.store) or self.bootstrap_default_company()
        runtime_store = CompanyRuntimeStore()
        return {
            "bootstrapped": company is not None,
            "company_id": target_id,
            "company": company,
            "storage_file": str(self.store.storage_file),
            "runtime_db_path": str(runtime_store.db_path),
            "runtime": runtime_store.stats(target_id) if company is not None else {},
        }

    def status_for_conversation(self, conversation_id: str, *, bootstrap: bool = False) -> dict[str, Any]:
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return self.status(None)
        company = self.store.find_company_by_conversation_id(conversation_id)
        if company is None and bootstrap:
            company = self.bootstrap_conversation_company(conversation_id)
        runtime_store = CompanyRuntimeStore()
        company_id = str(company.get("id") or _conversation_company_id(conversation_id)) if company else _conversation_company_id(conversation_id)
        return {
            "bootstrapped": company is not None,
            "company_id": company_id,
            "conversation_id": conversation_id,
            "company": company,
            "storage_file": str(self.store.storage_file),
            "runtime_db_path": str(runtime_store.db_path),
            "runtime": runtime_store.stats(company_id) if company is not None else {},
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


def _conversation_company_id(conversation_id: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(conversation_id or "").strip()).strip("-").lower()
    if len(clean) > 40:
        clean = clean[:40].strip("-")
    digest = hashlib.sha1(str(conversation_id).encode("utf-8")).hexdigest()[:10]
    return "chat-team-" + (clean or digest) + "-" + digest


def _conversation_employee_model(conversation_id: str, metadata: dict[str, Any] | None) -> str:
    for key in ("employee_model", "model", "preferred_model"):
        candidate = str((metadata or {}).get(key) or "").strip()
        if candidate:
            return candidate
    try:
        from domain.chat.store import ChatStore

        conversation = ChatStore().get_conversation(conversation_id) or {}
        candidate = str(conversation.get("model") or "").strip()
        if candidate:
            return candidate
    except Exception:
        pass
    return ""


def _default_agents_for_model(model: str) -> list[dict[str, Any]]:
    model = str(model or "").strip()
    agents = default_agents()
    if not model:
        return agents
    for agent in agents:
        agent["model"] = model
    return agents
