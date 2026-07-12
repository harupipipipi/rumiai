from __future__ import annotations

from typing import Any

from domain.agent_runtime.run_store import AgentRunStore


def record_agent_event(payload: dict[str, Any]) -> None:
    run_id = payload.get("run_id")
    if run_id:
        AgentRunStore().add_event(str(run_id), str(payload.get("event_type") or "hook"), payload)
