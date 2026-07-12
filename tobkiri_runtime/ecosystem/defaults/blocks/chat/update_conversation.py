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
    updates = input_data.get("updates")
    if not updates or not isinstance(updates, dict):
        return error("updates dict is required", "INVALID_INPUT")
    conv = store.update_conversation(conversation_id, updates)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    return ok(conv)
