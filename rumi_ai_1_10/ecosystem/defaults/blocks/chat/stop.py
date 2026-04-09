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
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    stream_id = input_data.get("stream_id")
    call_handler = context.get("call_handler") if context else None
    if call_handler is not None and stream_id:
        try:
            call_handler("defaults.ai.stop", {"stream_id": stream_id})
        except Exception:
            pass
    return ok({"success": True})
