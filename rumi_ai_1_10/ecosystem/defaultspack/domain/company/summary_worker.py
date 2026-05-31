from __future__ import annotations

from typing import Any

from domain.agent_runtime.run_store import AgentRunStore

from .models import DEFAULT_CHANNEL_ID, DEFAULT_COMPANY_ID
from .runtime_store import CompanyRuntimeStore


class CompanySummaryWorker:
    """Scribe worker for company, channel, thread, task, and run summaries."""

    def __init__(
        self,
        *,
        runtime_store: CompanyRuntimeStore | None = None,
        run_store: AgentRunStore | None = None,
        scribe_agent_id: str = "scribe",
    ) -> None:
        self.runtime_store = runtime_store or CompanyRuntimeStore()
        self.run_store = run_store or AgentRunStore()
        self.scribe_agent_id = scribe_agent_id

    def summarize_scope(self, company_id: str, scope_type: str, scope_id: str) -> dict[str, Any]:
        summary = self._build_summary(company_id, scope_type, scope_id)
        return self.runtime_store.upsert_summary(
            company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            summary=summary,
            generated_by=self.scribe_agent_id,
            dirty=False,
            metadata={"source": "company_summary_worker"},
        )

    def process_dirty(self, company_id: str = DEFAULT_COMPANY_ID, *, limit: int = 25) -> list[dict[str, Any]]:
        processed = []
        for item in self.runtime_store.list_dirty_summaries(company_id, limit=limit):
            processed.append(self.summarize_scope(company_id, str(item["scope_type"]), str(item["scope_id"])))
        return processed

    def _build_summary(self, company_id: str, scope_type: str, scope_id: str) -> str:
        if scope_type == "thread":
            messages, total = self.runtime_store.list_messages(company_id, thread_id=scope_id, limit=20)
            tasks, task_total = self.runtime_store.list_tasks(company_id, thread_id=scope_id, limit=20)
            return _format_summary("thread", scope_id, messages, total, tasks, task_total)
        if scope_type == "channel":
            messages, total = self.runtime_store.list_messages(company_id, channel_id=scope_id or DEFAULT_CHANNEL_ID, limit=20)
            return _format_summary("channel", scope_id, messages, total, [], 0)
        if scope_type == "task":
            task = self.runtime_store.get_task(scope_id, company_id=company_id) or {}
            links = self.runtime_store.list_run_links(company_id, task_id=scope_id)
            return (
                "Task summary: "
                + str(task.get("title") or scope_id)
                + " status="
                + str(task.get("status") or "unknown")
                + "; runs="
                + str(len(links))
            )
        if scope_type == "run":
            run = self.run_store.get_run(scope_id) or {}
            events = self.run_store.events(scope_id, limit=10) if run else []
            return (
                "Run summary: "
                + str(scope_id)
                + " status="
                + str(run.get("status") or "unknown")
                + "; events="
                + str(len(events))
            )
        if scope_type == "company":
            stats = self.runtime_store.stats(company_id)
            return "Company summary: " + ", ".join(key + "=" + str(value) for key, value in sorted(stats.items()))
        return "Summary for " + scope_type + ":" + scope_id


def _format_summary(
    label: str,
    scope_id: str,
    messages: list[dict[str, Any]],
    total_messages: int,
    tasks: list[dict[str, Any]],
    total_tasks: int,
) -> str:
    recent = "; ".join(
        str(message.get("sender_id") or "unknown") + ": " + str(message.get("content") or "")[:80]
        for message in messages[-5:]
    )
    task_bits = "; ".join(str(task.get("title") or task.get("task_id")) + " [" + str(task.get("status")) + "]" for task in tasks[:5])
    summary = label.capitalize() + " summary for " + str(scope_id) + ": " + str(total_messages) + " message(s)"
    if total_tasks:
        summary += ", " + str(total_tasks) + " task(s)"
    if recent:
        summary += ". Recent: " + recent
    if task_bits:
        summary += ". Tasks: " + task_bits
    return summary
