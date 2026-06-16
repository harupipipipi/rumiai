from __future__ import annotations

from typing import Any


def content_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content", []) if isinstance(message, dict) else []
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, dict):
        return [content]
    return []


def _non_empty_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _tool_call_entries(message: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        if isinstance(call, dict):
            entries.append(call)
    for block in content_blocks(message):
        block_type = str(block.get("type") or "")
        if block_type in {"tool_call", "tool_use"}:
            entries.append(block)
        nested = block.get("tool_call")
        if isinstance(nested, dict):
            entries.append(nested)
    return entries


def tool_call_count(message: dict[str, Any]) -> int:
    if not isinstance(message, dict):
        return 0
    return len(_tool_call_entries(message))


def tool_call_ids(message: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    if not isinstance(message, dict):
        return ids
    for call in _tool_call_entries(message):
        call_id = _non_empty_id(call.get("id") or call.get("tool_call_id"))
        if call_id:
            ids.add(call_id)
    return ids


def tool_result_ids(message: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    if not isinstance(message, dict):
        return ids

    if message.get("role") == "tool":
        call_id = _non_empty_id(message.get("tool_call_id") or message.get("tool_use_id"))
        if call_id:
            ids.add(call_id)

    for result in message.get("tool_results") or []:
        if isinstance(result, dict):
            call_id = _non_empty_id(result.get("tool_call_id") or result.get("tool_use_id"))
            if call_id:
                ids.add(call_id)

    for block in content_blocks(message):
        block_type = str(block.get("type") or "")
        if block_type in {"tool_result", "tool_output"}:
            call_id = _non_empty_id(
                block.get("tool_call_id")
                or block.get("tool_use_id")
                or block.get("id")
            )
            if call_id:
                ids.add(call_id)
        nested = block.get("tool_result")
        if isinstance(nested, dict):
            call_id = _non_empty_id(nested.get("tool_call_id") or nested.get("tool_use_id"))
            if call_id:
                ids.add(call_id)
    return ids


def _first_index_with_tool_call(messages: list[dict[str, Any]], call_id: str) -> int | None:
    for idx, message in enumerate(messages):
        if call_id in tool_call_ids(message):
            return idx
    return None


def _first_index_with_tool_result(messages: list[dict[str, Any]], call_id: str) -> int | None:
    for idx, message in enumerate(messages):
        if call_id in tool_result_ids(message):
            return idx
    return None


def _same_id_expanded_range(
    messages: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
) -> tuple[int, int]:
    start_id = messages[start_idx].get("id")
    while start_id and start_idx > 0 and messages[start_idx - 1].get("id") == start_id:
        start_idx -= 1
    end_id = messages[end_idx].get("id")
    while end_id and end_idx + 1 < len(messages) and messages[end_idx + 1].get("id") == end_id:
        end_idx += 1
    return start_idx, end_idx


def _range_tool_pairs(
    messages: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
) -> tuple[dict[str, int], dict[str, int]]:
    calls: dict[str, int] = {}
    results: dict[str, int] = {}
    for idx in range(start_idx, end_idx + 1):
        for call_id in tool_call_ids(messages[idx]):
            calls.setdefault(call_id, idx)
        for call_id in tool_result_ids(messages[idx]):
            results.setdefault(call_id, idx)
    return calls, results


def normalize_compaction_range(
    messages: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    protected_start: int | None = None,
    min_segment_length: int = 2,
) -> tuple[int, int] | None:
    """Adjust a compaction range so tool call/result pairs stay together."""
    if not messages:
        return None

    count = len(messages)
    start_idx = max(0, min(int(start_idx), count - 1))
    end_idx = max(0, min(int(end_idx), count - 1))
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx

    if protected_start is None:
        protected_start = count
    protected_start = max(0, min(int(protected_start), count))
    end_idx = min(end_idx, protected_start - 1)
    if end_idx < start_idx:
        return None

    for _ in range((count * 2) + 2):
        original = (start_idx, end_idx)
        start_idx, end_idx = _same_id_expanded_range(messages, start_idx, end_idx)
        calls, results = _range_tool_pairs(messages, start_idx, end_idx)

        for call_id, call_idx in sorted(calls.items(), key=lambda item: item[1]):
            if call_id in results:
                continue
            result_idx = _first_index_with_tool_result(messages, call_id)
            if result_idx is None:
                continue
            if result_idx < start_idx:
                start_idx = result_idx
            elif result_idx > end_idx:
                if result_idx >= protected_start:
                    end_idx = min(end_idx, call_idx - 1)
                else:
                    end_idx = result_idx

        if end_idx < start_idx:
            return None

        calls, results = _range_tool_pairs(messages, start_idx, end_idx)
        for call_id, result_idx in sorted(results.items(), key=lambda item: item[1]):
            if call_id in calls:
                continue
            call_idx = _first_index_with_tool_call(messages, call_id)
            if call_idx is None:
                continue
            if call_idx < start_idx:
                start_idx = call_idx
            elif call_idx > end_idx:
                if call_idx >= protected_start:
                    start_idx = max(start_idx, result_idx + 1)
                else:
                    end_idx = call_idx

        if end_idx < start_idx:
            return None
        end_idx = min(end_idx, protected_start - 1)
        if (start_idx, end_idx) == original:
            break

    if end_idx - start_idx + 1 < min_segment_length:
        return None
    return start_idx, end_idx
