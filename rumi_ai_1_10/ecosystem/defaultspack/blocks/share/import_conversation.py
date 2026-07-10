import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.share.conversation_bundle import import_shared_conversation
from domain.share.store import ShareStore


def run(input_data, context=None):
    token = str((input_data or {}).get("token") or "").strip()
    if not token:
        return error("'token' is required", code="INVALID_INPUT")
    record = ShareStore().get(token)
    if record is None:
        return error("Share link is missing, expired, or revoked", code="NOT_FOUND")
    if record.get("target_type") != "conversation":
        return error("Share does not contain a conversation", code="INVALID_INPUT")
    try:
        conversation = import_shared_conversation(
            record.get("content") or {}, source_url=str((input_data or {}).get("source_url") or record.get("share_url") or "")
        )
    except PermissionError as exc:
        return error(str(exc), code="PERMISSION_DENIED")
    except (TypeError, ValueError) as exc:
        return error(str(exc), code="INVALID_INPUT")
    return ok({"conversation": conversation, "conversation_id": conversation["id"]})
