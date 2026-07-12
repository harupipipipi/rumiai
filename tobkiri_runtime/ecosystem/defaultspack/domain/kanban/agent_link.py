from __future__ import annotations

from typing import Any


def start_agent_for_card(card: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "started": False,
        "mode": "noop",
        "card_id": card.get("card_id"),
        "payload": {key: value for key, value in payload.items() if not str(key).startswith("_")},
    }


def get_agent_status_for_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": card.get("card_id"),
        "agent_status": card.get("agent_status"),
        "agent_run_id": card.get("agent_run_id"),
        "agent_session_id": card.get("agent_session_id"),
    }
