from __future__ import annotations

from .replacement_history import repair_tool_pairs
from .token_estimator import estimate_messages_tokens


def prune_to_budget(messages: list[dict], budget_tokens: int) -> list[dict]:
    kept: list[dict] = []
    for message in reversed(messages):
        candidate = [message] + kept
        if kept and estimate_messages_tokens(candidate) > budget_tokens:
            break
        kept = candidate
    return repair_tool_pairs(kept)
