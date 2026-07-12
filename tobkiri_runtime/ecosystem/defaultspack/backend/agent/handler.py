from __future__ import annotations

from typing import Any, Dict, List, Optional

from .orchestrator import AgentOrchestrator, AgentRole, AgentSpec, TaskStatus, VisibilityScope

_orch = AgentOrchestrator()


def create_agent(role: str, name: str) -> Dict[str, Any]:
    spec = AgentSpec(agent_id=name.lower().replace(" ", "_"), role=AgentRole.CODING if role == "coding" else AgentRole.GENERAL, display_name=name)
    _orch.register_agent(spec)
    return {"created": True, "id": spec.agent_id, "role": spec.role.value}


def execute_task(agent_id: str = "", task_type: str = "general", instructions: str = "", parent_task: Optional[str] = None) -> Dict[str, Any]:
    task = _orch.create_task(instructions or task_type, task_type, parent_task=parent_task)
    _orch.start_task(task.task_id)
    return {"task_id": task.task_id, "state": task.status.value}


def get_task_status(task_id: str) -> Dict[str, Any]:
    task = _orch.get_task(task_id)
    if task is None:
        return {"status_code": 404}
    return {"task_id": task.task_id, "state": task.status.value, "step_count": len(task.sub_tasks)}


def pause_task(task_id: str) -> Dict[str, Any]:
    task = _orch.pause_task(task_id)
    return {"task_id": task_id, "state": task.status.value if task else "missing"}


def resume_task(task_id: str) -> Dict[str, Any]:
    data = _orch.resume_task(task_id)
    task = _orch.get_task(task_id)
    return data if data is not None else {"task_id": task_id, "state": task.status.value if task else "missing"}


def cancel_task(task_id: str) -> Dict[str, Any]:
    task = _orch.cancel_task(task_id)
    return {"task_id": task_id, "state": task.status.value if task else "missing"}


def checkpoint(task_id: str) -> Dict[str, Any]:
    return _orch.checkpoint_task(task_id, {"checkpoint_id": task_id})


def add_instruction(task_id: str, instruction: str) -> Dict[str, Any]:
    task = _orch.get_task(task_id)
    if task is None:
        return {"status_code": 404}
    task.sub_tasks.append(instruction)
    return {"added": True}


def create_channel(name: str, visibility_scope: VisibilityScope = VisibilityScope.GLOBAL, members: Optional[List[str]] = None):
    return _orch.create_channel(name, visibility_scope, members)


def list_channels() -> List[Dict[str, Any]]:
    return _orch.list_channels()


def post_message(channel_id: str, thread_id: str, agent_id: str, content: str) -> Dict[str, Any]:
    message = _orch.post_message(channel_id, thread_id, agent_id, content)
    return {
        "message_id": message.message_id if message else "",
        "agent_id": agent_id,
        "content": content,
    }


def get_thread(channel_id: str, thread_id: str):
    channel = _orch._channels.get(channel_id)
    return channel.get_thread(thread_id) if channel else []


def pm_escalation(task_id: str, reason: str = "") -> Dict[str, Any]:
    return _orch.escalate_to_pm(task_id, reason)
