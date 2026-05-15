import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error
from domain.ai_client.client import AIClient
from domain.chat.run_request import validate_chat_run_input
from domain.chat.store import ChatStore
from domain.chat.stream_engine import ChatRunEngine, _InlineThoughtFilter
from domain.stream.events import to_legacy_chat_stream_event


def _fallback_send(input_data, context):
    # Compatibility shim: keep the old helper name, but route through the
    # unified run engine instead of the legacy threaded send-path fallback.
    yield from _engine_events(input_data, context)


def _engine_events(input_data, context):
    try:
        engine_context = dict(context or {}) if isinstance(context, dict) else {}
        engine_context.setdefault("run_source", "blocks.chat.stream")
        for event in ChatRunEngine(client=AIClient()).stream(input_data, engine_context, stream_mode=True):
            legacy = to_legacy_chat_stream_event(event)
            if legacy is not None:
                yield legacy
    except ValueError as exc:
        yield {"type": "error", "error": {"message": str(exc)}}
    except Exception as exc:
        yield {"type": "error", "error": {"message": "AI request failed: " + str(exc)}}


def run(input_data, context):
    validation_error = validate_chat_run_input(input_data if isinstance(input_data, dict) else {})
    if validation_error:
        return error(validation_error, "INVALID_INPUT")
    conversation_id = input_data.get("conversation_id") if isinstance(input_data, dict) else None
    store = ChatStore()
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        return error("Conversation not found", "NOT_FOUND")
    return {"_sse": True, "events": _engine_events(input_data, context)}
