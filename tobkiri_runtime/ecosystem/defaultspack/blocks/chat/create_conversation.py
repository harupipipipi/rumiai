import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import error, ok

from domain.chat.conversation_channel import (
    SIDE_CONVERSATION_CHANNEL,
    SIDE_CONVERSATION_KIND,
    is_side_conversation,
)
from domain.chat.store import ChatStore


def _existing_side_conversation(
    store: ChatStore,
    parent: dict,
) -> dict | None:
    for child_id in parent.get("child_conversation_ids") or []:
        child = store.get_conversation(str(child_id))
        if is_side_conversation(child):
            return child
    return None


def _create_or_get_side_conversation(input_data: dict) -> dict:
    store = ChatStore()
    parent_id = str(input_data.get("parent_conversation_id") or "").strip()
    if not parent_id:
        return error(
            "parent_conversation_id is required for side chat",
            "INVALID_INPUT",
        )
    parent = store.get_conversation(parent_id)
    if parent is None:
        return error("Parent conversation not found", "NOT_FOUND")
    parent_metadata = (
        dict(parent.get("metadata"))
        if isinstance(parent.get("metadata"), dict)
        else {}
    )
    if parent_metadata.get("shared_read_only") is True:
        return error(
            "Read-only conversations cannot create a side chat",
            "READ_ONLY",
        )
    existing = _existing_side_conversation(store, parent)
    if existing is not None:
        return ok(existing)

    requested_metadata = (
        dict(input_data.get("metadata"))
        if isinstance(input_data.get("metadata"), dict)
        else {}
    )
    metadata = {
        **requested_metadata,
        "hidden": True,
        "conversation_channel": SIDE_CONVERSATION_CHANNEL,
        "side_parent_conversation_id": parent_id,
    }
    metadata.pop("shared_read_only", None)
    try:
        conversation = store.create_conversation(
            model=parent.get("model"),
            system_prompt_id=parent.get("system_prompt_id"),
            agent_id=parent.get("agent_id"),
            tags=["side-chat"],
            parent_conversation_id=parent_id,
            conversation_kind=SIDE_CONVERSATION_KIND,
            metadata=metadata,
            group_id=parent.get("group_id"),
        )
    except Exception as exc:
        if type(exc).__name__ != "ConversationConflict":
            raise
        refreshed_parent = store.get_conversation(parent_id)
        existing = _existing_side_conversation(store, refreshed_parent or {})
        if existing is None:
            raise
        conversation = existing
    return ok(conversation)


def run(input_data, context):
    requested_metadata = (
        input_data.get("metadata")
        if isinstance(input_data.get("metadata"), dict)
        else {}
    )
    requested_kind = str(input_data.get("conversation_kind") or "").lower()
    requested_channel = str(
        requested_metadata.get("conversation_channel") or ""
    ).lower()
    if (
        requested_kind == SIDE_CONVERSATION_KIND
        or requested_channel == SIDE_CONVERSATION_CHANNEL
    ):
        return _create_or_get_side_conversation(input_data)

    store = ChatStore()
    model = input_data.get("model")
    # Prompt selection is an explicit conversation input.  A mutable
    # profiles/<id>/profile.yaml file is never an execution authority.
    system_prompt_id = input_data.get("system_prompt_id")
    agent_id = input_data.get("agent_id")
    tags = input_data.get("tags")
    parent_conversation_id = input_data.get("parent_conversation_id")
    conversation_kind = input_data.get("conversation_kind")
    metadata = input_data.get("metadata")
    group_id = input_data.get("group_id")
    conv = store.create_conversation(
        model=model,
        system_prompt_id=system_prompt_id,
        agent_id=agent_id,
        tags=tags,
        parent_conversation_id=parent_conversation_id,
        conversation_kind=conversation_kind,
        metadata=metadata,
        group_id=group_id,
    )
    return ok(conv)
