from __future__ import annotations

from typing import Any

MAIN_CONVERSATION_CHANNEL = "main"
SIDE_CONVERSATION_CHANNEL = "side"
SIDE_CHAT_SYSTEM_INSTRUCTION = "あなたはサイドチャットです。"


def _metadata(conversation: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(conversation, dict):
        return {}
    value = conversation.get("metadata")
    return dict(value) if isinstance(value, dict) else {}


def conversation_channel(conversation: dict[str, Any] | None) -> str:
    if not isinstance(conversation, dict):
        return MAIN_CONVERSATION_CHANNEL
    metadata = _metadata(conversation)
    explicit = str(
        metadata.get("conversation_channel")
        or metadata.get("channel")
        or ""
    ).strip().lower()
    if explicit in {MAIN_CONVERSATION_CHANNEL, SIDE_CONVERSATION_CHANNEL}:
        return explicit
    if str(conversation.get("conversation_kind") or "").strip().lower() == SIDE_CONVERSATION_CHANNEL:
        return SIDE_CONVERSATION_CHANNEL
    return MAIN_CONVERSATION_CHANNEL


def runtime_conversation(store: Any, conversation: dict[str, Any]) -> dict[str, Any]:
    """Return the runtime view for a conversation without merging message history."""
    if conversation_channel(conversation) != SIDE_CONVERSATION_CHANNEL:
        return conversation

    parent_id = str(conversation.get("parent_conversation_id") or "").strip()
    if not parent_id:
        return conversation
    parent = store.get_conversation(parent_id)
    if not isinstance(parent, dict):
        return conversation

    merged = dict(conversation)
    for key in ("model", "system_prompt_id", "agent_id", "group_id"):
        if key in parent:
            merged[key] = parent.get(key)

    metadata = _metadata(parent)
    metadata.update(_metadata(conversation))
    metadata.update(
        {
            "hidden": True,
            "conversation_channel": SIDE_CONVERSATION_CHANNEL,
            "side_parent_conversation_id": parent_id,
        }
    )
    merged["metadata"] = metadata
    return merged


def conversation_channel_system_instruction(conversation: dict[str, Any] | None) -> str:
    if conversation_channel(conversation) == SIDE_CONVERSATION_CHANNEL:
        return SIDE_CHAT_SYSTEM_INSTRUCTION
    return ""
