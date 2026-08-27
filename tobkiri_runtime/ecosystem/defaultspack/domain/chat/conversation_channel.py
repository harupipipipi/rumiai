"""Typed conversation-channel context for shared chat execution."""

from __future__ import annotations

from typing import Any, Mapping

MAIN_CONVERSATION_CHANNEL = "main"
SIDE_CONVERSATION_CHANNEL = "side"
SIDE_CONVERSATION_KIND = "side"
SIDE_CHAT_SYSTEM_INSTRUCTION = "あなたはサイドチャットです。"

_SIDE_METADATA_KEYS = {
    "conversation_channel",
    "hidden",
    "side_parent_conversation_id",
}


def conversation_channel(conversation: Mapping[str, Any] | None) -> str:
    """Return the typed execution channel for a conversation record."""
    if not isinstance(conversation, Mapping):
        return MAIN_CONVERSATION_CHANNEL
    metadata = _metadata(conversation)
    explicit = str(metadata.get("conversation_channel") or "").strip().lower()
    if explicit == SIDE_CONVERSATION_CHANNEL:
        return SIDE_CONVERSATION_CHANNEL
    if str(conversation.get("conversation_kind") or "").strip().lower() == (
        SIDE_CONVERSATION_KIND
    ):
        return SIDE_CONVERSATION_CHANNEL
    return MAIN_CONVERSATION_CHANNEL


def is_side_conversation(conversation: Mapping[str, Any] | None) -> bool:
    """Return whether a record is a side-channel child conversation."""
    return conversation_channel(conversation) == SIDE_CONVERSATION_CHANNEL


def side_execution_conversation(
    store: Any,
    conversation: dict[str, Any],
) -> dict[str, Any]:
    """Resolve parent-shared runtime settings without merging message history.

    The side conversation remains the execution and persistence principal. Only
    the main conversation's current model, prompt, agent, group, workspace, and
    tool-preference context are projected into request preparation.
    """
    if not is_side_conversation(conversation):
        return conversation
    parent_id = str(conversation.get("parent_conversation_id") or "").strip()
    if not parent_id:
        return conversation
    parent = store.get_conversation(parent_id)
    if not isinstance(parent, dict):
        return conversation

    resolved = dict(conversation)
    for key in ("model", "system_prompt_id", "agent_id", "group_id"):
        resolved[key] = parent.get(key)

    side_metadata = _metadata(conversation)
    parent_metadata = _metadata(parent)
    resolved["metadata"] = {
        **parent_metadata,
        **{
            key: side_metadata[key]
            for key in _SIDE_METADATA_KEYS
            if key in side_metadata
        },
        "hidden": True,
        "conversation_channel": SIDE_CONVERSATION_CHANNEL,
        "side_parent_conversation_id": parent_id,
    }
    return resolved


def side_system_instruction(conversation: Mapping[str, Any] | None) -> str:
    """Return canonical additional context for side execution only."""
    if is_side_conversation(conversation):
        return SIDE_CHAT_SYSTEM_INSTRUCTION
    return ""


def _metadata(conversation: Mapping[str, Any]) -> dict[str, Any]:
    value = conversation.get("metadata")
    return dict(value) if isinstance(value, Mapping) else {}
