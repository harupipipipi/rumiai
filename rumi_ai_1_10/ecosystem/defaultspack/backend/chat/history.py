from __future__ import annotations

from typing import Any, Dict, List


class HistoryManager:
    def compress(self, messages: List[Dict[str, Any]], max_messages: int = 20) -> List[Dict[str, Any]]:
        if len(messages) <= max_messages + 1:
            return list(messages)
        head = [m for m in messages if m.get("role") == "system"][:1]
        tail = [m for m in messages if m.get("role") != "system"][-max_messages:]
        return head + tail
