import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.chat.store import ChatStore


PREFERENCE_KEY = "tool_preferences"


def run(input_data, context):
    method = str((input_data or {}).get("_method") or "GET").upper()
    return run_put(input_data, context) if method == "PUT" else run_get(input_data, context)


def run_get(input_data, context):
    conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    conversation = ChatStore().get_conversation(conversation_id)
    if conversation is None:
        return error("Conversation not found", "NOT_FOUND")
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    preferences = metadata.get(PREFERENCE_KEY) if isinstance(metadata.get(PREFERENCE_KEY), dict) else {}
    return ok({"conversation_id": conversation_id, "preferences": preferences})


def run_put(input_data, context):
    conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    preferences = input_data.get("preferences")
    if not isinstance(preferences, dict):
        preferences = {
            "mode": input_data.get("mode"),
            "include": input_data.get("include", []),
            "exclude": input_data.get("exclude", []),
        }
    store = ChatStore()
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        return error("Conversation not found", "NOT_FOUND")
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    updated = {**metadata, PREFERENCE_KEY: _sanitize_preferences(preferences)}
    saved = store.update_conversation(conversation_id, {"metadata": updated})
    if saved is None:
        return error("Conversation not found", "NOT_FOUND")
    return ok({"conversation_id": conversation_id, "preferences": updated[PREFERENCE_KEY]})


def _sanitize_preferences(value):
    return {
        "mode": str(value.get("mode") or "auto").strip().lower(),
        "include": value.get("include") if isinstance(value.get("include"), list) else [],
        "exclude": value.get("exclude") if isinstance(value.get("exclude"), list) else [],
    }
