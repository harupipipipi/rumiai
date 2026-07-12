from __future__ import annotations

from typing import Any

from .run_store import AgentRunStore


class ResumeService:
    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def resume_run(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            return {"run_id": run_id, "status": "error", "error": "run not found"}
        if run.get("status") in {"running", "stale", "resumable"}:
            self.store.update_status(run_id, "queued")
            self.store.add_event(run_id, "run_resumed", {"from_status": run.get("status")})
            run["status"] = "queued"
        return run

    def execution_dict(self, run_id: str) -> dict[str, Any] | None:
        return self.store.load_execution_dict(run_id)
