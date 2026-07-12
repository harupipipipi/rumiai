from __future__ import annotations

from typing import Any

from .token_estimator import estimate_message_tokens


def build_replacement_history(
    messages: list[dict[str, Any]],
    compact_packet: dict[str, Any],
    *,
    keep_recent_tokens: int = 20000,
) -> list[dict[str, Any]]:
    system = [message for message in messages if message.get("role") == "system"]
    tail = _recent_tail_preserving_tool_pairs(
        [message for message in messages if message.get("role") != "system"],
        keep_recent_tokens,
    )
    summary = {
        "role": "user",
        "content": "Compacted handoff summary:\n" + str(compact_packet),
        "metadata": {"compact_id": compact_packet.get("compact_id")},
    }
    return system + [summary] + tail


def _recent_tail_preserving_tool_pairs(messages: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used = 0
    index = len(messages) - 1
    while index >= 0 and used < budget:
        message = messages[index]
        group = [message]
        if message.get("role") == "tool" and index > 0:
            prev = messages[index - 1]
            if prev.get("tool_calls"):
                group.insert(0, prev)
                index -= 1
        group_tokens = sum(estimate_message_tokens(item) for item in group)
        if selected and used + group_tokens > budget:
            break
        selected[0:0] = group
        used += group_tokens
        index -= 1
    return repair_tool_pairs(selected)


def repair_tool_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    pending_tool_calls = 0
    for message in messages:
        if message.get("tool_calls"):
            pending_tool_calls += len(message.get("tool_calls") or [])
            repaired.append(message)
            continue
        if message.get("role") == "tool":
            if pending_tool_calls <= 0:
                continue
            pending_tool_calls -= 1
            repaired.append(message)
            continue
        if pending_tool_calls > 0:
            repaired.append({"role": "tool", "content": "[tool result omitted during compaction]"})
            pending_tool_calls = 0
        repaired.append(message)
    while pending_tool_calls > 0:
        repaired.append({"role": "tool", "content": "[tool result omitted during compaction]"})
        pending_tool_calls -= 1
    return repaired
