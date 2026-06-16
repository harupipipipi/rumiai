from __future__ import annotations

from typing import Any

from .tool_pairing import (
    normalize_compaction_range,
    tool_call_count,
    tool_call_ids,
    tool_result_ids,
)

from .token_estimator import estimate_message_tokens


def build_replacement_history(
    messages: list[dict[str, Any]],
    compact_packet: dict[str, Any],
    *,
    keep_recent_tokens: int = 20000,
) -> list[dict[str, Any]]:
    system = [message for message in messages if message.get("role") == "system"]
    tail = recent_tail_preserving_tool_pairs(
        [message for message in messages if message.get("role") != "system"],
        keep_recent_tokens,
    )
    summary = {
        "role": "user",
        "content": "Compacted handoff summary:\n" + str(compact_packet),
        "metadata": {"compact_id": compact_packet.get("compact_id")},
    }
    return system + [summary] + tail


def recent_tail_preserving_tool_pairs(messages: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used = 0
    index = len(messages) - 1
    while index >= 0 and used < budget:
        normalized = normalize_compaction_range(
            messages,
            index,
            index,
            min_segment_length=1,
        )
        if normalized is None:
            start_idx = end_idx = index
        else:
            start_idx, end_idx = normalized
        group = messages[start_idx:end_idx + 1]
        group_tokens = sum(estimate_message_tokens(item) for item in group)
        if selected and used + group_tokens > budget:
            break
        selected[0:0] = group
        used += group_tokens
        index = start_idx - 1
    return repair_tool_pairs(selected)


def repair_tool_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    pending_ids: list[str] = []
    pending_unknown = 0

    def flush_pending() -> None:
        nonlocal pending_unknown
        while pending_ids:
            repaired.append({
                "role": "tool",
                "tool_call_id": pending_ids.pop(0),
                "content": "[tool result omitted during compaction]",
            })
        while pending_unknown > 0:
            repaired.append({"role": "tool", "content": "[tool result omitted during compaction]"})
            pending_unknown -= 1

    for message in messages:
        call_ids = sorted(tool_call_ids(message))
        result_ids = tool_result_ids(message)
        call_count = tool_call_count(message)

        if call_count:
            pending_ids.extend(call_ids)
            for result_id in sorted(result_ids):
                if result_id in pending_ids:
                    pending_ids.remove(result_id)
            pending_unknown += max(0, call_count - len(call_ids))
            repaired.append(message)
            continue

        if result_ids or message.get("role") == "tool":
            if result_ids:
                matched = False
                for result_id in sorted(result_ids):
                    if result_id in pending_ids:
                        pending_ids.remove(result_id)
                        matched = True
                if not matched:
                    continue
                repaired.append(message)
                continue

            if pending_ids:
                pending_ids.pop(0)
                repaired.append(message)
                continue
            if pending_unknown <= 0:
                continue
            pending_unknown -= 1
            repaired.append(message)
            continue

        flush_pending()
        repaired.append(message)
    flush_pending()
    return repaired
