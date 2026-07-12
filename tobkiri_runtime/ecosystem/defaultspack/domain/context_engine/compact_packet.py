from __future__ import annotations

from typing import Any

from blocks._common import gen_id, timestamp


def build_compact_packet(
    *,
    run_id: str = "",
    conversation_id: str = "",
    goal: str = "",
    summary: str = "",
    source_transcript_id: str = "",
    replacement_transcript_id: str = "",
    progress: dict[str, Any] | None = None,
    decisions: list[Any] | None = None,
    constraints: list[Any] | None = None,
    user_preferences: list[Any] | None = None,
    changed_files: list[Any] | None = None,
    tool_results: list[Any] | None = None,
    terminal_results: list[Any] | None = None,
    pinned_context: list[Any] | None = None,
    dropped_context_log: list[Any] | None = None,
    memory_flush_refs: list[Any] | None = None,
    next_steps: list[Any] | None = None,
    critical_context: list[Any] | None = None,
    compact_id: str | None = None,
) -> dict[str, Any]:
    return {
        "compact_id": compact_id or gen_id("compact_"),
        "run_id": run_id,
        "conversation_id": conversation_id,
        "goal": goal,
        "summary": summary,
        "current_task_state": summary,
        "progress": progress or {"done": [], "in_progress": [], "blocked": []},
        "decisions": decisions or [],
        "constraints": constraints or [],
        "user_preferences": user_preferences or [],
        "changed_files": changed_files or [],
        "tool_results": tool_results or [],
        "terminal_results": terminal_results or [],
        "pinned_context": pinned_context or [],
        "dropped_context_log": dropped_context_log or [],
        "memory_flush_refs": memory_flush_refs or [],
        "next_steps": next_steps or [],
        "critical_context": critical_context or [],
        "created_at": timestamp(),
        "source_transcript_id": source_transcript_id,
        "replacement_transcript_id": replacement_transcript_id,
    }
