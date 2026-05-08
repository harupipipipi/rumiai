import base64
import mimetypes
from pathlib import Path

from blocks._common import ok, error
from domain.chat.store import ChatStore


def _pack_root():
    return Path(__file__).resolve().parents[2]


def _allowed_roots(store, conversation_id):
    pack_root = _pack_root()
    return [
        store.conversation_workspace_dir(conversation_id).resolve(),
        (pack_root / "user_data" / "artifacts").resolve(),
    ]


def _is_allowed_image_path(path, roots):
    try:
        resolved = Path(path).expanduser().resolve()
    except Exception:
        return None
    if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
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


def _candidate_image_records(value, inherited=None):
    inherited = dict(inherited or {})
    if isinstance(value, dict):
        local = dict(inherited)
        for meta_key in ("click_marker", "marker", "target", "target_window", "image_size", "action"):
            if meta_key in value:
                local[meta_key] = value.get(meta_key)
        for key, item in value.items():
            if key in {"path", "model_image_path", "screenshot_path"} and isinstance(item, str):
                record = dict(local)
                record["path"] = item
                record["path_key"] = key
                yield record
            else:
                yield from _candidate_image_records(item, local)
    elif isinstance(value, list):
        for item in value:
            yield from _candidate_image_records(item, inherited)


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
    run_id = input_data.get("run_id")
    if not conversation_id or not run_id:
        return error("conversation_id and run_id are required", "INVALID_INPUT")

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

    message = store.get_message(conversation_id, run_id)
    if message is None or message.get("role") != "assistant":
        result = error("Run result not found", "NOT_FOUND")
        result["_http_status"] = 404
        return result

    roots = _allowed_roots(store, conversation_id)
    screenshots = []
    seen = set()
    for log in message.get("tool_logs", []) if isinstance(message.get("tool_logs"), list) else []:
        if not isinstance(log, dict):
            continue
        tool_name = str(log.get("tool_name") or "")
        if tool_name not in {"browser_computer", "browser_use", "computer_use"}:
            continue
        for candidate in _candidate_image_records(log.get("result")):
            resolved = _is_allowed_image_path(candidate.get("path"), roots)
            if resolved is None or str(resolved) in seen:
                continue
            seen.add(str(resolved))
            mime_type = mimetypes.guess_type(str(resolved))[0] or "image/png"
            data_url = "data:{};base64,{}".format(
                mime_type,
                base64.b64encode(resolved.read_bytes()).decode("ascii"),
            )
            item = {
                "id": "screenshot-{}".format(len(screenshots) + 1),
                "run_id": run_id,
                "tool_call_id": log.get("tool_call_id"),
                "tool_name": tool_name,
                "mime_type": mime_type,
                "data_url": data_url,
            }
            for meta_key in ("click_marker", "marker", "target", "target_window", "image_size", "action"):
                if meta_key in candidate:
                    item[meta_key] = candidate.get(meta_key)
            screenshots.append(item)

    return ok({"conversation_id": conversation_id, "run_id": run_id, "screenshots": screenshots})
