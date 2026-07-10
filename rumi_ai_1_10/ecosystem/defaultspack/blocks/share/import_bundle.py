import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.share.conversation_bundle import import_shared_conversation


def run(input_data, context=None):
    payload = (input_data or {}).get("bundle") or (input_data or {}).get("history")
    if not isinstance(payload, dict):
        return error("bundle or history object is required", code="INVALID_INPUT")
    try:
        conversation = import_shared_conversation(payload, source_url=(input_data or {}).get("source_url"))
    except (PermissionError, TypeError, ValueError) as exc:
        return error(str(exc), code="INVALID_INPUT")
    return ok({"conversation": conversation, "conversation_id": conversation["id"]})
