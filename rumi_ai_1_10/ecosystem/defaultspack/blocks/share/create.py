import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.share.store import ShareStore


def run(input_data, context=None):
    payload = dict(input_data or {})
    if payload.get("target_type") == "conversation" and not str(payload.get("target_id") or "").strip():
        return error("target_id is required for conversation shares", code="INVALID_INPUT")
    try:
        return ok(ShareStore().create(payload))
    except KeyError:
        return error("Conversation not found", code="NOT_FOUND")
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
