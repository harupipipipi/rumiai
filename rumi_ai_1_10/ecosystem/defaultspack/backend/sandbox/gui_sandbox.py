from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import uuid


@dataclass
class SandboxSession:
    session_id: str
    title: str
    created_at: float = field(default_factory=time.time)
    events: List[Dict[str, Any]] = field(default_factory=list)


class GUISandbox:
    def __init__(self) -> None:
        self._sessions: Dict[str, SandboxSession] = {}

    def create_session(self, title: str) -> SandboxSession:
        session = SandboxSession(session_id=uuid.uuid4().hex, title=title)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SandboxSession]:
        return self._sessions.get(session_id)

    def click(self, session_id: str, x: int, y: int) -> Dict[str, Any]:
        return self._record(session_id, "click", {"x": x, "y": y})

    def type_text(self, session_id: str, text: str) -> Dict[str, Any]:
        return self._record(session_id, "type", {"text": text})

    def scroll(self, session_id: str, amount: int) -> Dict[str, Any]:
        return self._record(session_id, "scroll", {"amount": amount})

    def screenshot(self, session_id: str) -> Dict[str, Any]:
        return self._record(session_id, "screenshot", {"path": None})

    def _record(self, session_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "error": "session not found"}
        event = {"action": action, **payload, "ts": time.time()}
        session.events.append(event)
        return {"ok": True, "session_id": session_id, "event": event}
