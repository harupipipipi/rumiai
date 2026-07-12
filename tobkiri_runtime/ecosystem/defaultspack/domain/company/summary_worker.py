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
        packet = self._build_packet(company_id, scope_type, scope_id)
        return self.runtime_store.upsert_summary(
            company_id,
            scope_type=scope_type,
            scope_id=scope_id,
            summary=summary,
            generated_by=self.scribe_agent_id,
            dirty=False,
            metadata={"source": "company_summary_worker", "packet": packet, **packet},
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

    def _build_packet(self, company_id: str, scope_type: str, scope_id: str) -> dict[str, Any]:
        packet = _empty_packet(scope_type, scope_id)
        if scope_type == "thread":
            messages, _ = self.runtime_store.list_messages(company_id, thread_id=scope_id, limit=100)
            tasks, _ = self.runtime_store.list_tasks(company_id, thread_id=scope_id, limit=100)
            _add_messages(packet, messages)
            _add_tasks(packet, tasks)
            for task in tasks:
                _add_run_links(packet, self.runtime_store.list_run_links(company_id, task_id=str(task.get("task_id") or ""), limit=100))
        elif scope_type == "channel":
            messages, _ = self.runtime_store.list_messages(company_id, channel_id=scope_id or DEFAULT_CHANNEL_ID, limit=100)
            _add_messages(packet, messages)
        elif scope_type == "task":
            task = self.runtime_store.get_task(scope_id, company_id=company_id)
            if task:
                _add_tasks(packet, [task])
                _add_run_links(packet, self.runtime_store.list_run_links(company_id, task_id=scope_id, limit=100))
        elif scope_type == "run":
            run = self.run_store.get_run(scope_id) or {}
            if run:
                _add_run(packet, run)
        elif scope_type == "company":
            tasks, _ = self.runtime_store.list_tasks(company_id, limit=100)
            _add_tasks(packet, tasks)
            _add_run_links(packet, self.runtime_store.list_run_links(company_id, limit=100))
        packet["owners"] = sorted(set(packet["owners"]))
        packet["changed_files"] = sorted(set(packet["changed_files"]))
        packet["source_message_ids"] = sorted(set(packet["source_message_ids"]))
        packet["source_run_ids"] = sorted(set(packet["source_run_ids"]))
        return packet


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


def _empty_packet(scope_type: str, scope_id: str) -> dict[str, Any]:
    return {
        "scope_type": str(scope_type),
        "scope_id": str(scope_id),
        "decisions": [],
        "blockers": [],
        "owners": [],
        "approvals_needed": [],
        "changed_files": [],
        "next_actions": [],
        "source_message_ids": [],
        "source_run_ids": [],
    }


def _add_messages(packet: dict[str, Any], messages: list[dict[str, Any]]) -> None:
    for message in messages:
        message_id = str(message.get("message_id") or "")
        if message_id:
            packet["source_message_ids"].append(message_id)
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        packet["decisions"].extend(_as_list(metadata.get("decisions")))
        packet["changed_files"].extend(_collect_changed_files(metadata))


def _add_tasks(packet: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        status = str(task.get("status") or "")
        title = str(task.get("title") or task_id)
        packet["owners"].extend(str(agent_id) for agent_id in task.get("target_agent_ids", []) if str(agent_id).strip())
        if task.get("message_id"):
            packet["source_message_ids"].append(str(task["message_id"]))
        if status in {"blocked", "failed", "stale"}:
            packet["blockers"].append({"task_id": task_id, "status": status, "title": title})
        if status == "waiting_approval":
            packet["approvals_needed"].append({"task_id": task_id, "title": title})
        if status in {"queued", "assigned", "running", "waiting_approval", "blocked", "stale"}:
            packet["next_actions"].append({"task_id": task_id, "status": status, "title": title})
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        packet["decisions"].extend(_as_list(metadata.get("decisions")))
        packet["changed_files"].extend(_collect_changed_files(metadata))


def _add_run_links(packet: dict[str, Any], links: list[dict[str, Any]]) -> None:
    for link in links:
        run_id = str(link.get("run_id") or "")
        if run_id:
            packet["source_run_ids"].append(run_id)
        if link.get("agent_id"):
            packet["owners"].append(str(link["agent_id"]))
        metadata = link.get("metadata") if isinstance(link.get("metadata"), dict) else {}
        packet["changed_files"].extend(_collect_changed_files(metadata))


def _add_run(packet: dict[str, Any], run: dict[str, Any]) -> None:
    run_id = str(run.get("run_id") or run.get("execution_id") or "")
    status = str(run.get("status") or "")
    if run_id:
        packet["source_run_ids"].append(run_id)
    if run.get("agent_id"):
        packet["owners"].append(str(run["agent_id"]))
    if status in {"blocked", "failed", "error", "stale"}:
        packet["blockers"].append({"run_id": run_id, "status": status, "error": run.get("error")})
    if status == "waiting_approval":
        packet["approvals_needed"].append({"run_id": run_id})
    packet["changed_files"].extend(_collect_changed_files(run.get("result_json")))
    packet["changed_files"].extend(_collect_changed_files(run.get("execution_json")))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _collect_changed_files(value: Any) -> list[str]:
    files: list[str] = []
    if isinstance(value, dict):
        for key in ("changed_files", "modified_files", "created_files", "deleted_files", "touched_files"):
            files.extend(str(item) for item in _as_list(value.get(key)) if str(item).strip())
        for key in ("file", "file_path", "path"):
            if value.get(key):
                files.append(str(value[key]))
        for nested in value.values():
            files.extend(_collect_changed_files(nested))
    elif isinstance(value, list):
        for item in value:
            files.extend(_collect_changed_files(item))
    return files[:100]
