import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore
from domain.chat.message_converter import convert_to_standard
from domain.chat.message_builder import build_assistant_message


def _stub_response():
    return {
        "content": [{"type": "text", "text": "[stub] Regenerated AI response placeholder"}],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def run(input_data, context):
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    message_id = input_data.get("message_id")
    if not message_id:
        return error("message_id is required", "INVALID_INPUT")
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    target_msg = store.get_message(conversation_id, message_id)
    if target_msg is None:
        return error("Message not found", "NOT_FOUND")
    parent_id = target_msg.get("parent_id")
    deleted = store.delete_message(conversation_id, message_id)
    if not deleted:
        return error("Failed to delete message for regeneration", "INTERNAL_ERROR")
    if parent_id is not None:
        chain = store.get_message_chain(conversation_id, parent_id)
    else:
        chain = []
    standard_messages = convert_to_standard(chain)
    model = conv.get("model", "stub/default")
    call_handler = context.get("call_handler") if context else None
    if call_handler is not None:
        try:
            ai_params = {
                "model": model,
                "messages": standard_messages,
                "tools": [],
                "params": {},
            }
            response = call_handler("defaults.ai.complete", ai_params)
        except Exception:
            response = _stub_response()
    else:
        response = _stub_response()
    parent_msg = store.get_message(conversation_id, parent_id) if parent_id else None
    seq = (parent_msg.get("sequence_number", 0) + 1) if parent_msg else 1
    assistant_msg_dict = build_assistant_message(
        conversation_id=conversation_id,
        parent_id=parent_id,
        sequence_number=seq,
        response=response,
        model=model,
    )
    assistant_msg = store.add_message(conversation_id, assistant_msg_dict)
    if assistant_msg is None:
        return error("Failed to add regenerated message", "INTERNAL_ERROR")
    return ok(assistant_msg)
