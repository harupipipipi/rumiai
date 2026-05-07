from __future__ import annotations

from typing import Any

from .run_store import AgentRunStore


class ToolLedger:
    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def started(self, run_id: str, tool_call_id: str, tool_name: str, arguments: dict[str, Any]) -> None:
        self.store.record_tool_call(run_id, tool_call_id, tool_name, arguments, status="running")
        self.store.add_event(run_id, "tool_started", {"tool_call_id": tool_call_id, "tool_name": tool_name})

    def completed(self, run_id: str, tool_call_id: str, tool_name: str, result: Any, *, is_error: bool = False) -> None:
        self.store.record_tool_call(
            run_id,
            tool_call_id,
            tool_name,
            {},
            status="failed" if is_error else "completed",
            result=result,
        )
        self.store.add_event(
            run_id,
            "tool_completed",
            {"tool_call_id": tool_call_id, "tool_name": tool_name, "is_error": is_error},
        )
