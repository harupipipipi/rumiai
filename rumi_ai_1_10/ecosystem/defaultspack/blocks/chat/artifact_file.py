import mimetypes
from pathlib import Path

from blocks._common import error
from domain.chat.store import ChatStore


def _pack_root():
    return Path(__file__).resolve().parents[2]


def _allowed_roots(store, conversation_id):
    pack_root = _pack_root()
    return [
        store.conversation_workspace_dir(conversation_id).resolve(),
        (pack_root / "user_data" / "artifacts").resolve(),
    ]


def _resolve_allowed_path(raw_path, roots):
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    try:
        resolved = Path(raw_path).expanduser().resolve()
    except Exception:
        return None
    if not resolved.is_file():
        return None
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None


def _owner_error(conversation, headers):
    metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
    owner = metadata.get("user_id") or metadata.get("owner_user_id") if isinstance(metadata, dict) else None
    if not owner:
        return None
    requested = headers.get("X-Rumi-User-Id") or headers.get("x-rumi-user-id")
    if requested != owner:
        result = error("conversation owner mismatch", "FORBIDDEN")
        result["_http_status"] = 403
        return result
    return None


def run(input_data, context):
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    store = ChatStore()
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        result = error("Conversation not found", "NOT_FOUND")
        result["_http_status"] = 404
        return result

    headers = input_data.get("_headers") if isinstance(input_data.get("_headers"), dict) else {}
    owner_err = _owner_error(conversation, headers)
    if owner_err:
        return owner_err

    resolved = _resolve_allowed_path(input_data.get("path"), _allowed_roots(store, conversation_id))
    if resolved is None:
        result = error("artifact file not found or not allowed", "NOT_FOUND")
        result["_http_status"] = 404
        return result

    mime_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    try:
        body = resolved.read_bytes()
    except OSError as exc:
        result = error("failed to read artifact file: {}".format(exc), "READ_FAILED")
        result["_http_status"] = 500
        return result
    return {"_static": True, "content_type": mime_type, "body": body}
