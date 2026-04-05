"""chat module - Conversation management, streaming, message queuing."""
from __future__ import annotations
import logging, threading, time, uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

@dataclass
class Message:
    role: str; content: str
    message_id: str = field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self): return {"role": self.role, "content": self.content, "message_id": self.message_id, "timestamp": self.timestamp}

@dataclass
class Conversation:
    conversation_id: str = field(default_factory=lambda: str(_uuid.uuid4()))
    title: str = "New Conversation"
    messages: List[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self): return {"conversation_id": self.conversation_id, "title": self.title, "messages": [m.to_dict() for m in self.messages], "created_at": self.created_at}

class ChatManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._conversations: Dict[str, Conversation] = {}
        self._message_queue: Dict[str, List[Message]] = {}
        self._active_streams: Dict[str, bool] = {}
    def create_conversation(self, title="New Conversation") -> Conversation:
        c = Conversation(title=title)
        with self._lock: self._conversations[c.conversation_id] = c
        return c
    def get_conversation(self, cid: str) -> Optional[Conversation]: return self._conversations.get(cid)
    def list_conversations(self) -> List[Conversation]: return list(self._conversations.values())
    def delete_conversation(self, cid: str) -> bool:
        with self._lock: return self._conversations.pop(cid, None) is not None
    def add_message(self, cid: str, msg: Message) -> bool:
        with self._lock:
            c = self._conversations.get(cid)
            if not c: return False
            c.messages.append(msg); return True
    def get_history(self, cid: str) -> List[Dict[str, Any]]:
        c = self._conversations.get(cid)
        return [m.to_dict() for m in c.messages] if c else []
    def queue_message(self, cid: str, msg: Message):
        with self._lock: self._message_queue.setdefault(cid, []).append(msg)
    def pop_queued(self, cid: str) -> Optional[Message]:
        with self._lock:
            q = self._message_queue.get(cid, [])
            return q.pop(0) if q else None
    def start_stream(self, cid: str): self._active_streams[cid] = True
    def stop_stream(self, cid: str): self._active_streams[cid] = False
    def is_streaming(self, cid: str) -> bool: return self._active_streams.get(cid, False)
    def compact_history(self, cid: str, keep_last: int = 20) -> int:
        with self._lock:
            c = self._conversations.get(cid)
            if not c: return 0
            orig = len(c.messages)
            if orig <= keep_last: return 0
            c.messages = c.messages[-keep_last:]
            return orig - keep_last
    def export_conversation(self, cid: str) -> Optional[Dict[str, Any]]:
        c = self._conversations.get(cid)
        return c.to_dict() if c else None
