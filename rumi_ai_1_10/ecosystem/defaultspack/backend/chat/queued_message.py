from __future__ import annotations

from dataclasses import dataclass
import time
import uuid


def _id() -> str:
    return str(uuid.uuid4())


@dataclass
class Message:
    conversation_id: str
    content: str
    role: str = "user"
    message_id: str = ""
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = _id()
        if not self.created_at:
            self.created_at = time.time()


class MessageQueue:
    def __init__(self) -> None:
        self._queues = {}

    def enqueue(self, conversation_id: str, content: str, role: str = "user") -> Message:
        msg = Message(conversation_id=conversation_id, content=content, role=role)
        self._queues.setdefault(conversation_id, []).append(msg)
        return msg

    def dequeue(self, conversation_id: str):
        queue = self._queues.get(conversation_id, [])
        if not queue:
            return None
        return queue.pop(0)

    def size(self, conversation_id: str) -> int:
        return len(self._queues.get(conversation_id, []))
