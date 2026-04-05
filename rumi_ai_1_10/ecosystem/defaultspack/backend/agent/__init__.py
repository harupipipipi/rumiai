"""agent module - Multi-agent orchestration and organization."""
from __future__ import annotations
import logging, threading, time, uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

@dataclass
class AgentRole:
    role_id: str; display_name: str = ""; description: str = ""; system_prompt: str = ""
    capabilities: List[str] = field(default_factory=list)
    def to_dict(self): return {"role_id": self.role_id, "display_name": self.display_name, "capabilities": self.capabilities}

@dataclass
class AgentTask:
    task_id: str = field(default_factory=lambda: str(_uuid.uuid4()))
    description: str = ""; assigned_to: str = ""; status: str = "pending"
    context: Dict[str, Any] = field(default_factory=dict); result: Optional[Any] = None
    checkpoint: Optional[Dict[str, Any]] = None; created_at: float = field(default_factory=time.time)
    def to_dict(self): return {"task_id": self.task_id, "description": self.description, "assigned_to": self.assigned_to, "status": self.status}

@dataclass
class Channel:
    channel_id: str; name: str = ""; channel_type: str = "general"
    members: List[str] = field(default_factory=list); messages: List[Dict[str, Any]] = field(default_factory=list)
    visibility: str = "all"
    def to_dict(self): return {"channel_id": self.channel_id, "name": self.name, "channel_type": self.channel_type, "members": self.members, "message_count": len(self.messages)}

class AgentManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._roles: Dict[str, AgentRole] = {}; self._tasks: Dict[str, AgentTask] = {}
        self._channels: Dict[str, Channel] = {}
    def register_role(self, role: AgentRole): self._roles[role.role_id] = role
    def create_task(self, description: str, assigned_to: str = "", context: Dict[str, Any] = None) -> AgentTask:
        t = AgentTask(description=description, assigned_to=assigned_to, context=context or {})
        self._tasks[t.task_id] = t; return t
    def get_task(self, tid: str) -> Optional[AgentTask]: return self._tasks.get(tid)
    def update_task_status(self, tid: str, status: str, result=None) -> bool:
        t = self._tasks.get(tid)
        if not t: return False
        t.status = status
        if result is not None: t.result = result
        return True
    def checkpoint_task(self, tid: str, data: Dict[str, Any]) -> bool:
        t = self._tasks.get(tid)
        if not t: return False
        t.checkpoint = data; return True
    def resume_task(self, tid: str) -> Optional[Dict[str, Any]]:
        t = self._tasks.get(tid)
        if not t or not t.checkpoint: return None
        t.status = "running"; return t.checkpoint
    def create_channel(self, name: str, channel_type="general", members=None) -> Channel:
        ch = Channel(channel_id=str(_uuid.uuid4()), name=name, channel_type=channel_type, members=members or [])
        self._channels[ch.channel_id] = ch; return ch
    def send_to_channel(self, cid: str, sender: str, content: str, visibility="all") -> bool:
        ch = self._channels.get(cid)
        if not ch: return False
        ch.messages.append({"sender": sender, "content": content, "visibility": visibility, "timestamp": time.time()})
        return True
    def get_channel_messages(self, cid: str, limit=50) -> List[Dict[str, Any]]:
        ch = self._channels.get(cid)
        return ch.messages[-limit:] if ch else []
    def list_channels(self) -> List[Dict[str, Any]]: return [ch.to_dict() for ch in self._channels.values()]
    def list_tasks(self, status=None) -> List[Dict[str, Any]]:
        tasks = self._tasks.values()
        if status: tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in tasks]
    def list_roles(self) -> List[Dict[str, Any]]: return [r.to_dict() for r in self._roles.values()]
    def escalate_to_pm(self, tid: str, reason: str) -> Dict[str, Any]:
        t = self._tasks.get(tid)
        if not t: return {"error": "Task not found"}
        t.status = "escalated"
        return {"task_id": tid, "escalated_to": "pm", "reason": reason}
