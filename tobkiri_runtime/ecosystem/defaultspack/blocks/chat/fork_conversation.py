"""Create a writable conversation fork through the chat state owner."""

from typing import Any, Mapping

from blocks._common import error, ok
from domain.chat.store import ChatStore


def run(
    input_data: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Fork a conversation at an explicit or authoritative current message."""
    del context
    store = ChatStore()
    conversation_id = str(input_data.get("conversation_id") or "").strip()
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    source = store.get_conversation(conversation_id)
    if source is None:
        return error("Conversation not found", "NOT_FOUND")

    requested_message_id = str(input_data.get("message_id") or "").strip()
    messages = list(source.get("messages") or [])
    message_id = requested_message_id or str(source.get("current_node_id") or "")
    if not message_id and messages:
        message_id = str(messages[-1].get("id") or "")
    if message_id and store.get_message(conversation_id, message_id) is None:
        return error("Message not found", "NOT_FOUND")

    fork = store.branch(conversation_id, message_id or None)
    if fork is None:
        return error("Failed to create conversation fork", "INTERNAL_ERROR")

    fork_metadata = dict(fork.get("metadata") or {})
    fork_metadata.update(
        {
            "forked_from_conversation_id": conversation_id,
            "forked_from_message_id": message_id or None,
            "forked_from_title": source.get("title"),
            "forked_from_updated_at": source.get("updated_at"),
        }
    )
    if fork_metadata.get("shared_read_only") is True:
        fork_metadata["shared_read_only"] = False
        fork_metadata["shared_import_mode"] = "continue_copy"

    title = str(source.get("title") or "Conversation").strip() or "Conversation"
    updated = store.update_conversation(
        fork["id"],
        {
            "title": f"{title} (fork)",
            "conversation_kind": source.get("conversation_kind"),
            "group_id": source.get("group_id"),
            "metadata": fork_metadata,
        },
    )
    return ok(updated or fork)
