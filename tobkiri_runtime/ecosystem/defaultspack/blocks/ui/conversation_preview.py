import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok, error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.frontend.registry import FrontendRegistry


def run(input_data, context):
    conversation_id = (input_data or {}).get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    registry = FrontendRegistry()
    try:
        preview = registry.build_conversation_preview(conversation_id)
    except KeyError:
        return error("Conversation not found", "NOT_FOUND")
    return ok(preview)
