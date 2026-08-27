from __future__ import annotations

from .replacement_history import recent_tail_preserving_tool_pairs


def prune_to_budget(messages: list[dict], budget_tokens: int) -> list[dict]:
    return recent_tail_preserving_tool_pairs(messages, budget_tokens)
