import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore


SIDE_CHAT_KIND = "side"
SIDE_CHAT_CHANNEL = "side"
SIDE_CHAT_SYSTEM_INSTRUCTION = "あなたはサイドチャットです。"


def _active_profile_prompt_id() -> str | None:
    try:
        from core_runtime.profile_paths import active_profile_id
        from core_runtime.profile_runtime_selection import apply_profile_graph_selection
        from core_runtime.profile_workspace import ProfileWorkspaceManager
    except Exception:
        return None

    try:
        profile_id = str(active_profile_id() or "").strip()
    except Exception:
        return None
    if not profile_id:
        return None

    try:
        profile = ProfileWorkspaceManager().load_profile_yaml(profile_id)
    except Exception:
        return None
    if not isinstance(profile, dict):
        return None
    try:
        profile = apply_profile_graph_selection(profile)
    except Exception:
        pass
    prompt_id = str(profile.get("system_prompt_id") or profile.get("default_prompt_id") or "").strip()
    return prompt_id or None


def _is_side_conversation(conversation):
    if not isinstance(conversation, dict):
        return False
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    return (
        str(conversation.get("conversation_kind") or "").strip().lower() == SIDE_CHAT_KIND
        or str(metadata.get("conversation_channel") or "").strip().lower() == SIDE_CHAT_CHANNEL
    )


def _existing_side_conversation(store, parent):
    for child_id in parent.get("child_conversation_ids") or []:
        child = store.get_conversation(child_id)
        if _is_side_conversation(child):
            return child
    return None


def _ensure_side_system_instruction(store, conversation):
    messages = conversation.get("messages") if isinstance(conversation, dict) else []
    if not isinstance(messages, list):
        messages = []
    for message in messages:
        if not isinstance(message, dict) or str(message.get("role") or "") != "system":
            continue
        raw_text = str(message.get("raw_text") or "").strip()
        content = message.get("content")
        if raw_text == SIDE_CHAT_SYSTEM_INSTRUCTION:
            return conversation
        if isinstance(content, str) and content.strip() == SIDE_CHAT_SYSTEM_INSTRUCTION:
            return conversation
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and str(block.get("text") or "").strip() == SIDE_CHAT_SYSTEM_INSTRUCTION:
                    return conversation
    store.add_message(
        conversation["id"],
        {
            "role": "system",
            "content": [{"type": "text", "text": SIDE_CHAT_SYSTEM_INSTRUCTION}],
            "raw_text": SIDE_CHAT_SYSTEM_INSTRUCTION,
            "metadata": {
                "conversation_channel": SIDE_CHAT_CHANNEL,
                "side_chat_system_instruction": True,
            },
        },
    )
    return store.get_conversation(conversation["id"]) or conversation


def _create_or_get_side_conversation(store, input_data):
    parent_id = str(input_data.get("parent_conversation_id") or "").strip()
    if not parent_id:
        return None, error("parent_conversation_id is required for side chat", "INVALID_INPUT")
    parent = store.get_conversation(parent_id)
    if parent is None:
        return None, error("Parent conversation not found", "NOT_FOUND")
    parent_metadata = parent.get("metadata") if isinstance(parent.get("metadata"), dict) else {}
    if parent_metadata.get("shared_read_only") is True:
        return None, error("Read-only conversations cannot create a side chat", "READ_ONLY")

    existing = _existing_side_conversation(store, parent)
    if existing is not None:
        return _ensure_side_system_instruction(store, existing), None

    requested_metadata = input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {}
    metadata = {
        **parent_metadata,
        **requested_metadata,
        "hidden": True,
        "conversation_channel": SIDE_CHAT_CHANNEL,
        "side_parent_conversation_id": parent_id,
    }
    metadata.pop("shared_read_only", None)
    conv = store.create_conversation(
        model=input_data.get("model") or parent.get("model"),
        system_prompt_id=parent.get("system_prompt_id"),
        agent_id=parent.get("agent_id"),
        tags=input_data.get("tags") or ["side-chat"],
        parent_conversation_id=parent_id,
        conversation_kind=SIDE_CHAT_KIND,
        metadata=metadata,
        group_id=parent.get("group_id"),
    )
    return _ensure_side_system_instruction(store, conv), None


def run(input_data, context):
    store = ChatStore()
    conversation_kind = str(input_data.get("conversation_kind") or "").strip().lower()
    metadata = input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {}
    requested_channel = str(metadata.get("conversation_channel") or "").strip().lower()
    if conversation_kind == SIDE_CHAT_KIND or requested_channel == SIDE_CHAT_CHANNEL:
        conv, side_error = _create_or_get_side_conversation(store, input_data)
        return side_error or ok(conv)

    model = input_data.get("model")
    system_prompt_id = input_data.get("system_prompt_id") or _active_profile_prompt_id()
    agent_id = input_data.get("agent_id")
    tags = input_data.get("tags")
    parent_conversation_id = input_data.get("parent_conversation_id")
    metadata = input_data.get("metadata")
    group_id = input_data.get("group_id")
    conv = store.create_conversation(
        model=model,
        system_prompt_id=system_prompt_id,
        agent_id=agent_id,
        tags=tags,
        parent_conversation_id=parent_conversation_id,
        conversation_kind=input_data.get("conversation_kind"),
        metadata=metadata,
        group_id=group_id,
    )
    return ok(conv)
