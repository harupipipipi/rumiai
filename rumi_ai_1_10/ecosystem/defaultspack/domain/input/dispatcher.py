from __future__ import annotations

from typing import Any

from domain.input.action_registry import get_input_action_registry
from domain.input.envelope import RumiInputEnvelope


def dispatch_input(
    envelope: RumiInputEnvelope | dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(envelope, dict):
        envelope = RumiInputEnvelope.from_dict(envelope)
    delivery = envelope.delivery if isinstance(envelope.delivery, dict) else {}
    action_id = str(delivery.get("action_id") or "chat.message").strip() or "chat.message"
    handler = get_input_action_registry().resolve(action_id)
    if handler is None:
        return {
            "status": "error",
            "code": "UNKNOWN_INPUT_ACTION",
            "error": "unknown input action",
            "assistant_text": "",
            "action_id": action_id,
            "delivery": {"action_id": action_id},
            "available_actions": get_input_action_registry().list_actions(),
        }
    result = handler(envelope, context or {})
    if isinstance(result, dict):
        result.setdefault("action_id", action_id)
    return result
