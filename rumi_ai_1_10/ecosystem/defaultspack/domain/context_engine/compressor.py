from __future__ import annotations

from typing import Any

from .compact_packet import build_compact_packet
from .replacement_history import build_replacement_history
from .token_estimator import estimate_messages_tokens
from .validation import validate_compact_packet


class ContextCompressor:
    def should_compact(
        self,
        messages: list[dict[str, Any]],
        *,
        context_window: int = 200000,
        threshold: float = 0.50,
        reserve_tokens: int = 20000,
    ) -> bool:
        tokens = estimate_messages_tokens(messages)
        return tokens >= context_window * threshold or tokens > max(1, context_window - reserve_tokens)

    def compact(self, messages: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = metadata or {}
        summary = _summary_from_messages(messages)
        packet = build_compact_packet(
            run_id=str(metadata.get("run_id") or ""),
            conversation_id=str(metadata.get("conversation_id") or ""),
            goal=str(metadata.get("goal") or ""),
            summary=summary,
            source_transcript_id=str(metadata.get("source_transcript_id") or ""),
            replacement_transcript_id=str(metadata.get("replacement_transcript_id") or ""),
            progress=metadata.get("progress"),
            changed_files=list(metadata.get("changed_files") or []),
            decisions=list(metadata.get("decisions") or []),
            constraints=list(metadata.get("constraints") or []),
            user_preferences=list(metadata.get("user_preferences") or []),
            tool_results=list(metadata.get("tool_results") or []),
            terminal_results=list(metadata.get("terminal_results") or []),
            pinned_context=list(metadata.get("pinned_context") or []),
            dropped_context_log=list(metadata.get("dropped_context_log") or metadata.get("dropped_context") or []),
            memory_flush_refs=list(metadata.get("memory_flush_refs") or []),
            next_steps=list(metadata.get("next_steps") or []),
            critical_context=list(metadata.get("critical_context") or []),
        )
        packet["validation"] = validate_compact_packet(packet).to_dict()
        replacement = build_replacement_history(messages, packet)
        return {
            "packet": packet,
            "replacement_history": replacement,
            "tokens_before": estimate_messages_tokens(messages),
            "tokens_after": estimate_messages_tokens(replacement),
        }


def _summary_from_messages(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages[-20:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role", "unknown")
        content = message.get("content", "")
        lines.append(f"{role}: {str(content)[:500]}")
    return "\n".join(lines)
