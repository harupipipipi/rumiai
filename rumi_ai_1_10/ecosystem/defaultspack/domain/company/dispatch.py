from __future__ import annotations

from typing import Any

from .models import gen_id, timestamp
from .store import CompanyStore


class CompanyDispatchService:
    """Queue-only dispatch metadata. This service never executes tools."""

    def __init__(self, store: CompanyStore | None = None) -> None:
        self.store = store or CompanyStore()

    def dispatch_task(
        self,
        company_id: str,
        task_id: str,
        *,
        requested_by: str = "system",
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        task = self.store.get_task(company_id, task_id)
        if task is None:
            return None
        dispatch = {
            "id": gen_id("dispatch_"),
            "status": "queued",
            "requested_by": requested_by,
            "target_agent_ids": list(task.get("target_agent_ids", [])),
            "policy": {
                **(policy or {}),
                "mode": "local_queue_only",
                "direct_tool_execution": False,
            },
            "created_at": timestamp(),
        }
        updated = self.store.append_task_dispatch(company_id, task_id, dispatch)
        return {"task": updated, "dispatch": dispatch}
