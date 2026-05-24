from __future__ import annotations

from domain.chat.store import ChatStore
from domain.input.envelope import RumiInputEnvelope


def handle(envelope: RumiInputEnvelope, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    route_override = {
        key: value
        for key, value in {
            "preferred_model": envelope.params.get("model") or envelope.params.get("profile_id"),
            "preferred_group": envelope.params.get("preferred_group"),
            "requested_thinking_level": envelope.params.get("thinking_level"),
            "task_hints": envelope.params.get("task_hints") if isinstance(envelope.params.get("task_hints"), dict) else {},
        }.items()
        if value not in (None, "", {})
    }
    if not route_override:
        return {"status": "error", "code": "MISSING_INPUT", "error": "model route override is required", "assistant_text": ""}
    target = envelope.target if isinstance(envelope.target, dict) else {}
    conversation_id = str(target.get("conversation_id") or envelope.chat.get("conversation_id") or "").strip()
    if not conversation_id:
        return {"status": "error", "code": "MISSING_TARGET", "error": "conversation_id is required", "assistant_text": ""}
    store = ChatStore()
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        return {"status": "error", "code": "NOT_FOUND", "error": "conversation not found", "assistant_text": ""}
    metadata = dict(conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {})
    metadata["turn_model_route_override"] = route_override
    updated = store.update_conversation(conversation_id, {"metadata": metadata}) or conversation
    return {
        "status": "ok",
        "assistant_text": "",
        "conversation_id": conversation_id,
        "route_override": route_override,
        "conversation": updated,
    }
