from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRole(str, Enum):
    PM = "pm"
    CODING = "coding"
    SEARCHER = "searcher"
    REVIEWER = "reviewer"
    GENERAL = "general"


class VisibilityScope(str, Enum):
    GLOBAL = "global"
    TEAM = "team"
    PRIVATE = "private"


@dataclass
class AgentSpec:
    agent_id: str
    role: AgentRole
    display_name: str = ""
    system_prompt: str = ""
    model: str = "default"
    tools: List[str] = field(default_factory=list)


@dataclass
class Task:
    task_id: str
    description: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = 0.0
    parent_task_id: Optional[str] = None
    sub_tasks: List[str] = field(default_factory=list)
    checkpoint_data: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class ChannelMessage:
    message_id: str
    channel_id: str
    thread_id: str
    role: str
    content: str
    created_at: float = field(default_factory=time.time)


@dataclass
class Thread:
    thread_id: str
    channel_id: str
    title: str
    messages: List[ChannelMessage] = field(default_factory=list)


@dataclass
class Channel:
    channel_id: str
    name: str
    visibility_scope: VisibilityScope = VisibilityScope.GLOBAL
    members: List[str] = field(default_factory=list)
    threads: Dict[str, Thread] = field(default_factory=dict)

    def post(self, thread_id: str, agent_id: str, content: str) -> Dict[str, Any]:
        thread = self.threads.setdefault(
            thread_id,
            Thread(thread_id=thread_id, channel_id=self.channel_id, title=thread_id),
        )
        message = ChannelMessage(
            message_id=uuid.uuid4().hex,
            channel_id=self.channel_id,
            thread_id=thread_id,
            role=agent_id,
            content=content,
        )
        thread.messages.append(message)
        return {"message_id": message.message_id, "agent_id": agent_id, "content": content}

    def get_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        thread = self.threads.get(thread_id)
        if thread is None:
            return []
        return [
            {
                "message_id": msg.message_id,
                "agent_id": msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
            }
            for msg in thread.messages
        ]


class AgentOrchestrator:
    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._channels: Dict[str, Channel] = {}
        self._agents: Dict[str, AgentSpec] = {}

    def register_agent(self, spec: AgentSpec) -> AgentSpec:
        self._agents[spec.agent_id] = spec
        return spec

    def list_agents(self) -> List[AgentSpec]:
        return list(self._agents.values())

    def create_task(self, first: str, second: str, parent_task: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> Task:
        known_roles = {role.value for role in AgentRole} | set(self._agents.keys())
        if first in known_roles and second not in known_roles:
            task_type, description = first, second
        elif second in known_roles and first not in known_roles:
            task_type, description = second, first
        else:
            description, task_type = first, second
        task = Task(
            task_id=uuid.uuid4().hex,
            description=description,
            task_type=task_type,
            parent_task_id=parent_task,
        )
        self._tasks[task.task_id] = task
        if parent_task and parent_task in self._tasks:
            self._tasks[parent_task].sub_tasks.append(task.task_id)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus) -> Optional[Task]:
        task = self._tasks.get(task_id)
        if task:
            task.status = status
        return task

    def get_status(self, task_id: str) -> Dict[str, Any]:
        task = self._tasks.get(task_id)
        if task is None:
            return {"status": "missing", "status_code": 404}
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "step_count": len(task.sub_tasks),
        }

    def start_task(self, task_id: str) -> Optional[Task]:
        return self.update_task_status(task_id, TaskStatus.RUNNING)

    def pause_task(self, task_id: str) -> Optional[Task]:
        return self.update_task_status(task_id, TaskStatus.PAUSED)

    def resume_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.status = TaskStatus.RUNNING
        if task.checkpoint_data is None:
            return None
        return dict(task.checkpoint_data)

    def complete_task(self, task_id: str, result: str = "") -> Optional[Task]:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.checkpoint_data = {"result": result}
        return task

    def cancel_task(self, task_id: str) -> Optional[Task]:
        return self.update_task_status(task_id, TaskStatus.CANCELLED)

    def checkpoint_task(self, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        task = self._tasks.get(task_id)
        if task is None:
            return {"error": "task not found", "status_code": 404}
        task.checkpoint_data = dict(data)
        return dict(task.checkpoint_data)

    def escalate_to_pm(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self._tasks.get(task_id)
        if task is None:
            return {"error": "task not found", "status_code": 404}
        task.status = TaskStatus.RUNNING
        return {"task_id": task_id, "escalated": True, "reason": reason}

    def create_channel(self, name: str, visibility_scope: VisibilityScope = VisibilityScope.GLOBAL, members: Optional[List[str]] = None) -> Channel:
        channel = Channel(
            channel_id=uuid.uuid4().hex,
            name=name,
            visibility_scope=visibility_scope,
            members=list(members or []),
        )
        self._channels[channel.channel_id] = channel
        return channel

    def list_channels(self) -> List[Dict[str, Any]]:
        return [
            {
                "channel_id": channel.channel_id,
                "name": channel.name,
                "visibility_scope": channel.visibility_scope.value,
                "members": list(channel.members),
            }
            for channel in self._channels.values()
        ]

    def create_thread(self, channel_id: str, title: str) -> Optional[Thread]:
        channel = self._channels.get(channel_id)
        if channel is None:
            return None
        thread = Thread(thread_id=uuid.uuid4().hex, channel_id=channel_id, title=title)
        channel.threads[thread.thread_id] = thread
        return thread

    def post_message(self, channel_id: str, thread_id: str, role: str, content: str) -> Optional[ChannelMessage]:
        channel = self._channels.get(channel_id)
        if channel is None:
            return None
        thread = channel.threads.setdefault(
            thread_id, Thread(thread_id=thread_id, channel_id=channel_id, title=thread_id)
        )
        message = ChannelMessage(
            message_id=uuid.uuid4().hex,
            channel_id=channel_id,
            thread_id=thread_id,
            role=role,
            content=content,
        )
        thread.messages.append(message)
        return message
