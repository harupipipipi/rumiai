from __future__ import annotations

from typing import Any


def board_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "board": snapshot.get("board"),
        "column_count": len(snapshot.get("columns") or []),
        "card_count": len(snapshot.get("cards") or []),
        "event_count": len(snapshot.get("events") or []),
    }
