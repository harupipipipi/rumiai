import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore


def run(input_data, context):
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    fmt = input_data.get("format", "markdown")
    if fmt not in ("markdown", "json"):
        return error("format must be 'markdown' or 'json'", "INVALID_INPUT")
    content = store.export_conversation(conversation_id, fmt=fmt)
    if content is None:
        return error("Conversation not found", "NOT_FOUND")
    return ok({"content": content})
