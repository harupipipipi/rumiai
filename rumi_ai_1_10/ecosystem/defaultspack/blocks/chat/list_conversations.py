import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore


def run(input_data, context):
    store = ChatStore()
    limit = input_data.get("limit", 50)
    offset = input_data.get("offset", 0)
    tag = input_data.get("tag")
    is_starred = input_data.get("is_starred")
    is_archived = input_data.get("is_archived")
    conversations, total = store.list_conversations(
        limit=limit,
        offset=offset,
        tag=tag,
        is_starred=is_starred,
        is_archived=is_archived,
    )
    return ok({"conversations": conversations, "total": total})
