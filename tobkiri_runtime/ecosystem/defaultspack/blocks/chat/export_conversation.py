import os
import sys
from typing import Any, Mapping

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok

from domain.chat.store import ChatStore
from domain.share.audit import record_share_event


def run(
    input_data: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Export an owner-scoped conversation in a supported text format."""
    del context
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    fmt = (
        str(input_data.get("format", "markdown") or "markdown")
        .strip()
        .lower()
        .lstrip(".")
    )
    if fmt == "md":
        fmt = "markdown"
    if fmt == "txt":
        fmt = "text"
    if fmt not in ("markdown", "json", "text"):
        return error(
            "format must be one of: markdown, md, json, text, txt",
            "INVALID_INPUT",
        )
    content = store.export_conversation(conversation_id, fmt=fmt)
    if content is None:
        return error("Conversation not found", "NOT_FOUND")
    audit = record_share_event("export", target_id=conversation_id, mode=str(fmt))
    return ok(
        {
            "conversation_id": conversation_id,
            "format": fmt,
            "content": content,
            "audit": audit,
        }
    )
