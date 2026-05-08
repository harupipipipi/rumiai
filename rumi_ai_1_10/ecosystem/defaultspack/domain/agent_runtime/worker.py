from __future__ import annotations

from typing import Any

from .locks import session_lock
from .run_store import AgentRunStore


class AgentWorker:
    """Synchronous worker facade around the existing AgentEngine."""

    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def run_once(self, run_id: str, session_key: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            return {"run_id": run_id, "status": "error", "error": "run not found"}
        with session_lock(session_key):
            self.store.update_status(run_id, "running")
            self.store.add_event(run_id, "run_started", {"session_key": session_key})
            return run
