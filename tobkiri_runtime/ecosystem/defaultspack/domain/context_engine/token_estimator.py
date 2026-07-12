from __future__ import annotations

import json
from typing import Any


def estimate_tokens(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return max(1, len(value.encode("utf-8")) // 4)
    raw = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, len(raw.encode("utf-8")) // 4)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    discount = 0
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"image", "image_url"}:
                discount += 512
    return max(1, estimate_tokens(message) + discount)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_message_tokens(message) for message in messages if isinstance(message, dict))
