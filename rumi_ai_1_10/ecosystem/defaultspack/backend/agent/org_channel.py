from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class OrgThread:
    thread_id: str = ""
    title: str = ""
    messages: List[Dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.thread_id:
            self.thread_id = str(uuid.uuid4())


class OrgChannel:
    def __init__(self, channel_id: str, name: str) -> None:
        self.channel_id = channel_id
        self.name = name
        self._members: List[str] = []
        self._messages: List[Dict[str, str]] = []
        self._threads: Dict[str, OrgThread] = {}

    def add_member(self, role: str) -> None:
        if role not in self._members:
            self._members.append(role)

    def create_thread(self, title: str) -> OrgThread:
        thread = OrgThread(title=title)
        self._threads[thread.thread_id] = thread
        return thread

    def post_message(self, role: str, content: str, thread_id: Optional[str] = None) -> Dict[str, str]:
        payload = {"role": role, "content": content}
        if thread_id is None:
            self._messages.append(payload)
        else:
            thread = self._threads.setdefault(thread_id, OrgThread(thread_id=thread_id))
            thread.messages.append(payload)
        return payload

    def get_messages(self, thread_id: Optional[str] = None) -> List[Dict[str, str]]:
        if thread_id is None:
            return list(self._messages)
        thread = self._threads.get(thread_id)
        return list(thread.messages) if thread else []
