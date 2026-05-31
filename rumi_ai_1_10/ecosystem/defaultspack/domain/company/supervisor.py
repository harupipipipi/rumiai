from __future__ import annotations

from typing import Any

from domain.agent_runtime.run_store import AgentRunStore

from .models import DEFAULT_COMPANY_ID
from .runtime_store import CompanyRuntimeStore


class CompanySupervisor:
    """Operations manager tick for company workspace health."""

    def __init__(
        self,
        *,
        runtime_store: CompanyRuntimeStore | None = None,
        run_store: AgentRunStore | None = None,
    ) -> None:
        self.runtime_store = runtime_store or CompanyRuntimeStore()
        self.run_store = run_store or AgentRunStore()

    def tick(self, company_id: str = DEFAULT_COMPANY_ID, *, stale_after_seconds: int = 600) -> dict[str, Any]:
        open_tasks = self.runtime_store.list_open_tasks(company_id)
        unassigned_mentions = self.runtime_store.list_unassigned_mentions(company_id)
        stale_runs = self.run_store.list_stale(stale_after_seconds=stale_after_seconds)
        waiting_approvals = self.run_store.list_waiting_approval()
        failed_runs = self.run_store.list_runs(status="error", limit=50) + self.run_store.list_runs(status="failed", limit=50)
        dirty_summaries = self.runtime_store.list_dirty_summaries(company_id)

        actions: list[dict[str, Any]] = []
        for task in open_tasks:
            actions.append({"type": "open_task", "task_id": task.get("task_id"), "status": task.get("status")})
        for item in unassigned_mentions:
            actions.append({"type": "unassigned_mention", "inbox_id": item.get("inbox_id"), "content": item.get("content")})
        for run in stale_runs:
            actions.append({"type": "stale_run", "run_id": run.get("run_id"), "agent_id": run.get("agent_id")})
        for run in waiting_approvals:
            actions.append({"type": "waiting_approval", "run_id": run.get("run_id"), "agent_id": run.get("agent_id")})
        for run in failed_runs:
            actions.append({"type": "failed_run", "run_id": run.get("run_id"), "error": run.get("error")})
        for summary in dirty_summaries:
            actions.append({"type": "dirty_summary", "scope_type": summary.get("scope_type"), "scope_id": summary.get("scope_id")})

        if actions:
            self.runtime_store.add_inbox_item(
                company_id,
                agent_id="operations_manager",
                kind="supervisor_tick",
                content="Supervisor found " + str(len(actions)) + " company workspace item(s).",
                priority="normal",
                metadata={"actions": actions},
            )

        return {
            "company_id": company_id,
            "open_tasks": open_tasks,
            "unassigned_mentions": unassigned_mentions,
            "stale_runs": stale_runs,
            "waiting_approvals": waiting_approvals,
            "failed_runs": failed_runs,
            "dirty_summaries": dirty_summaries,
            "actions": actions,
        }
