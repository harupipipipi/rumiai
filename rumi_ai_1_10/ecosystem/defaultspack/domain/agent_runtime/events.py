from __future__ import annotations

from typing import Any

from .run_store import AgentRunStore


class AgentEventBus:
    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.store.add_event(run_id, event_type, payload or {})
