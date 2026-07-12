import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore


def run(input_data, context):
    store = ChatStore()
    model = input_data.get("model")
    system_prompt_id = input_data.get("system_prompt_id")
    agent_id = input_data.get("agent_id")
    tags = input_data.get("tags")
    conv = store.create_conversation(
        model=model,
        system_prompt_id=system_prompt_id,
        agent_id=agent_id,
        tags=tags,
    )
    return ok(conv)
