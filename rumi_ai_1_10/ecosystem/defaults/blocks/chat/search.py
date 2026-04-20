import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore


def run(input_data, context):
    store = ChatStore()
    query = input_data.get("query")
    if not query:
        return error("query is required", "INVALID_INPUT")
    conversation_id = input_data.get("conversation_id")
    results = store.search(query, conversation_id=conversation_id)
    return ok({"results": results})
