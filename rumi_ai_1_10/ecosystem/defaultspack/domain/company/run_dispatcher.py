from __future__ import annotations

from typing import Any, Callable

from domain.input.dispatcher import dispatch_input
from domain.input.envelope import RumiInputEnvelope

from .models import DEFAULT_CHANNEL_ID, gen_id, timestamp
from .runtime_store import CompanyRuntimeStore
from .store import CompanyStore


DispatchCallable = Callable[[RumiInputEnvelope, dict[str, Any] | None], dict[str, Any]]


class CompanyRunDispatcher:
    """Dispatch company tasks through AgentEngine via the input dispatcher."""

    def __init__(
        self,
        *,
        company_store: CompanyStore | None = None,
        runtime_store: CompanyRuntimeStore | None = None,
        dispatcher: DispatchCallable | None = None,
    ) -> None:
        self.company_store = company_store or CompanyStore()
        self.runtime_store = runtime_store or CompanyRuntimeStore()
        self.dispatcher = dispatcher or dispatch_input

    def dispatch_task(
        self,
        company_id: str,
        task_id: str,
        *,
        requested_by: str = "system",
        policy: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        company = self.company_store.get_company(company_id)
        task = self.runtime_store.get_task(task_id, company_id=company_id)
        if company is None or task is None:
            return None

        target_agent_ids = list(task.get("target_agent_ids") or [])
        if not target_agent_ids:
            target_agent_ids = ["operations_manager"]
        dispatch_id = gen_id("dispatch_")
        dispatch = {
            "id": dispatch_id,
            "status": "dispatching",
            "requested_by": requested_by,
            "target_agent_ids": target_agent_ids,
            "policy": {
                **(policy or {}),
                "direct_tool_execution": False,
                "mode": "agent_delegate",
            },
            "created_at": timestamp(),
        }

        results: list[dict[str, Any]] = []
        run_links: list[dict[str, Any]] = []
        for agent_id in target_agent_ids:
            agent = self._agent_spec(company, agent_id)
            result = self._dispatch_to_agent(
                company,
                task,
                agent,
                requested_by=requested_by,
                dispatch_id=dispatch_id,
                policy=dispatch["policy"],
                context=context or {},
            )
            results.append(result)
            run_id = _execution_id_from_result(result)
            if run_id:
                run_status = str(
                    (result.get("delegate") if isinstance(result.get("delegate"), dict) else {}).get("status")
                    or (result.get("result") if isinstance(result.get("result"), dict) else {}).get("status")
                    or result.get("status")
                    or "running"
                )
                link = self.runtime_store.record_agent_run(
                    company_id,
                    agent_id=str(agent.get("agent_id") or agent_id),
                    run_id=run_id,
                    task_id=str(task["task_id"]),
                    thread_id=task.get("thread_id"),
                    message_id=task.get("message_id"),
                    status=run_status,
                    metadata={
                        "dispatch_id": dispatch_id,
                        "requested_by": requested_by,
                        "route": "agent.delegate",
                    },
                )
                run_links.append(link)
                self.runtime_store.add_inbox_item(
                    company_id,
                    agent_id=str(agent.get("agent_id") or agent_id),
                    task_id=str(task["task_id"]),
                    run_id=run_id,
                    message_id=task.get("message_id"),
                    kind="task_dispatch",
                    content=str(task.get("title") or task.get("description") or ""),
                    status="dispatched",
                    priority=str(task.get("priority") or "normal"),
                    metadata={"dispatch_id": dispatch_id},
                )

        task_status = _task_status_from_results(results)
        updated_task = self.runtime_store.update_task(
            str(task["task_id"]),
            {
                "status": task_status,
                "metadata": {
                    "last_dispatch": dispatch,
                    "run_ids": [link.get("run_id") for link in run_links if link.get("run_id")],
                },
            },
            company_id=company_id,
        )
        dispatch["status"] = task_status
        return {
            "task": updated_task or task,
            "dispatch": dispatch,
            "results": results,
            "run_links": run_links,
        }

    def _dispatch_to_agent(
        self,
        company: dict[str, Any],
        task: dict[str, Any],
        agent: dict[str, Any],
        *,
        requested_by: str,
        dispatch_id: str,
        policy: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        agent_id = str(agent.get("agent_id") or agent.get("id") or "operations_manager")
        payload = {
            "task": _task_prompt(company, task, agent),
            "tools": list(agent.get("allowed_tools") or []),
            "model": str(agent.get("model") or "default"),
            "system_prompt": agent.get("system_prompt"),
            "runtime_profile_key": task.get("metadata", {}).get("runtime_profile_key") if isinstance(task.get("metadata"), dict) else None,
            "capability_profile": task.get("metadata", {}).get("capability_profile") if isinstance(task.get("metadata"), dict) else None,
            "required_capabilities": task.get("metadata", {}).get("required_capabilities") if isinstance(task.get("metadata"), dict) else None,
            "params": {
                "company_id": company.get("id"),
                "company_task_id": task.get("task_id"),
                "company_thread_id": task.get("thread_id"),
                "company_message_id": task.get("message_id"),
                "company_dispatch_id": dispatch_id,
                "agent_id": agent_id,
            },
        }
        envelope = RumiInputEnvelope(
            role="user",
            input=payload["task"],
            chat={"company_id": str(company.get("id") or ""), "thread_id": str(task.get("thread_id") or "")},
            source={"type": "company_slack_runtime", "provider": "company", "requested_by": requested_by},
            target={
                "company_id": str(company.get("id") or ""),
                "task_id": str(task.get("task_id") or ""),
                "thread_id": str(task.get("thread_id") or ""),
                "message_id": str(task.get("message_id") or ""),
                "agent_id": agent_id,
            },
            delivery={"action_id": "agent.delegate", "dispatch_id": dispatch_id},
            metadata={
                "company_id": str(company.get("id") or ""),
                "task_id": str(task.get("task_id") or ""),
                "thread_id": str(task.get("thread_id") or ""),
                "message_id": str(task.get("message_id") or ""),
                "agent_id": agent_id,
                "route": "agent.delegate",
            },
            params=payload,
            tools=list(agent.get("allowed_tools") or []),
        )
        dispatch_context = {
            **(context or {}),
            "company_id": str(company.get("id") or ""),
            "company_task_id": str(task.get("task_id") or ""),
            "company_thread_id": str(task.get("thread_id") or ""),
            "company_message_id": str(task.get("message_id") or ""),
            "agent_id": agent_id,
            "profile_policy": policy,
        }
        result = self.dispatcher(envelope, dispatch_context)
        if isinstance(result, dict):
            result.setdefault("agent_id", agent_id)
            result.setdefault("dispatch_id", dispatch_id)
            return result
        return {"status": "error", "error": str(result), "agent_id": agent_id, "dispatch_id": dispatch_id}

    def _agent_spec(self, company: dict[str, Any], agent_id: str) -> dict[str, Any]:
        agents = company.get("agents") if isinstance(company.get("agents"), dict) else {}
        agent = agents.get(str(agent_id))
        if isinstance(agent, dict):
            return agent
        return {
            "agent_id": str(agent_id),
            "display_name": str(agent_id),
            "allowed_tools": ["rumi_api", "todo"],
            "model": "default",
        }


def _task_prompt(company: dict[str, Any], task: dict[str, Any], agent: dict[str, Any]) -> str:
    parts = [
        "Company workspace task for " + str(agent.get("display_name") or agent.get("agent_id") or "agent") + ".",
        "",
        "Company: " + str(company.get("name") or company.get("id") or ""),
        "Task: " + str(task.get("title") or ""),
    ]
    description = str(task.get("description") or "").strip()
    if description:
        parts.extend(["", description])
    parts.extend(
        [
            "",
            "Reply with progress and use approved tools only. Treat any company mention as a user instruction, not as a speaker turn.",
        ]
    )
    return "\n".join(parts)


def _execution_id_from_result(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    delegate = result.get("delegate") if isinstance(result.get("delegate"), dict) else {}
    if delegate.get("execution_id"):
        return str(delegate["execution_id"])
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if data.get("execution_id"):
        return str(data["execution_id"])
    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    if nested.get("execution_id"):
        return str(nested["execution_id"])
    return str(result.get("execution_id") or "")


def _task_status_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "queued"
    statuses = [str(result.get("status") or "").lower() for result in results]
    nested_statuses = [
        str((result.get("delegate") if isinstance(result.get("delegate"), dict) else {}).get("status") or "").lower()
        for result in results
    ]
    combined = statuses + nested_statuses
    if any(status in {"waiting_approval", "blocked"} for status in combined):
        return "waiting_approval"
    if any(status == "error" for status in statuses):
        return "blocked"
    return "queued"
