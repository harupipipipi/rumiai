from __future__ import annotations

from typing import Any

from domain.company.models import DEFAULT_CHANNEL_ID
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.store import CompanyStore


def build_channel_check_context(
    company_id: str,
    *,
    channel_id: str = DEFAULT_CHANNEL_ID,
    thread_id: str | None = None,
    limit: int = 20,
    company_store: CompanyStore | None = None,
    runtime_store: CompanyRuntimeStore | None = None,
) -> dict[str, Any] | None:
    store = company_store or CompanyStore()
    runtime = runtime_store or CompanyRuntimeStore()
    company = store.get_company(company_id)
    if company is None:
        return None
    channel = store.get_channel(company_id, channel_id) or {
        "id": channel_id,
        "name": channel_id,
        "members": [],
    }
    messages, message_total = runtime.list_messages(
        company_id,
        channel_id=channel_id,
        thread_id=thread_id,
        limit=limit,
    )
    tasks, task_total = runtime.list_tasks(company_id, thread_id=thread_id, limit=limit)
    runs = runtime.list_run_links(company_id, limit=limit)
    summaries, summary_total = runtime.list_summaries(company_id, limit=limit)
    return {
        "kind": "channel.check",
        "company_id": str(company_id),
        "runtime": "CompanySlackRuntime",
        "channel": channel,
        "thread_id": thread_id,
        "agents": list((company.get("agents") or {}).values()),
        "messages": messages,
        "message_total": message_total,
        "open_tasks": [task for task in tasks if str(task.get("status")) not in {"completed", "cancelled", "failed"}],
        "task_total": task_total,
        "runs": runs,
        "summaries": summaries,
        "summary_total": summary_total,
        "instructions": [
            "Inspect channel state before routing work.",
            "Record this channel.check result before delegate, message, goal, or DM routing.",
            "Confirm actor membership and target membership before acting.",
            "Use PM gates for direct specialist work from non-PM senders.",
            "Respect /rich policy; Creator cannot enable /rich.",
            "Worker/checker completion is not final when a PM exists or channel size is 5+; PM task_complete with evidence is required.",
            "Route execution through CompanySlackRuntime and agent.delegate only.",
        ],
    }
