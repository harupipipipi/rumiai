from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok  # noqa: E402
from domain.chat.directive_layer import (  # noqa: E402
    DIRECTIVE_SCOPE,
    clear_directive_metadata,
    is_clear_directive_instruction,
    set_directive_metadata,
)
from domain.chat.store import ChatStore  # noqa: E402


def run(input_data: Any = None, context: Any = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    conversation_id = str(data.get("conversation_id") or "").strip()
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    store = ChatStore()
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        return error("Conversation not found", "NOT_FOUND")

    instruction = str(data.get("instruction") or data.get("directive") or "").strip()
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    source_command = str(data.get("command") or "directive").strip().lstrip("/") or "directive"

    if is_clear_directive_instruction(instruction):
        updated = store.update_conversation(
            conversation_id,
            {"metadata": clear_directive_metadata(metadata)},
        )
        if updated is None:
            return error("Conversation not found", "NOT_FOUND")
        return ok(
            {
                "conversation_id": conversation_id,
                "scope": DIRECTIVE_SCOPE,
                "directive": None,
                "cleared": True,
                "message": "Directive Layer cleared for this conversation.",
            }
        )

    if not instruction:
        return error("directive instruction is required", "MISSING_PARAM")

    try:
        updated_metadata, directive = set_directive_metadata(
            metadata,
            instruction,
            source_command=source_command,
        )
    except ValueError as exc:
        return error(str(exc), "INVALID_INPUT")

    updated = store.update_conversation(conversation_id, {"metadata": updated_metadata})
    if updated is None:
        return error("Conversation not found", "NOT_FOUND")

    preview = directive["content"].replace("\n", " ").strip()
    if len(preview) > 180:
        preview = preview[:177].rstrip() + "..."
    return ok(
        {
            "conversation_id": conversation_id,
            "scope": DIRECTIVE_SCOPE,
            "directive": directive,
            "cleared": False,
            "message": f"Directive Layer active for this conversation: {preview}",
        }
    )
