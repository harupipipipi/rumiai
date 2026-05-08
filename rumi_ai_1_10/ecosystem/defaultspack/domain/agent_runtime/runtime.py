from __future__ import annotations

from typing import Any

from .policy import session_key_for
from .run_store import AgentRunStore


class DurableAgentRuntime:
    """Compatibility runtime that centralizes durable store access."""

    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def status(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            return {"execution_id": run_id, "status": "error", "result": {"error": "execution not found"}}
        execution = run.get("execution_json") if isinstance(run.get("execution_json"), dict) else {}
        steps = execution.get("steps", [])
        return {
            "execution_id": run_id,
            "status": run.get("status"),
            "steps": steps,
            "current_step": execution.get("current_step", len(steps)),
        }

    def cancel(self, run_id: str) -> dict[str, Any]:
        self.store.update_status(run_id, "cancelled", completed=True)
        self.store.add_event(run_id, "run_completed", {"status": "cancelled"})
        return {"execution_id": run_id, "status": "cancelled"}

    @staticmethod
    def session_key(context: dict[str, Any] | None) -> str:
        return session_key_for(context)
