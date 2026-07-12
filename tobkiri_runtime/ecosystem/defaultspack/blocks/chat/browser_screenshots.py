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


def _number(value):
    try:
        return float(value)
    except Exception:
        return None


def _scale_marker_to_model(marker, record):
    if not isinstance(marker, dict):
        return marker
    model_size = record.get("model_image_size")
    if not isinstance(model_size, dict):
        return marker
    model_width = _number(model_size.get("width"))
    model_height = _number(model_size.get("height"))
    if not model_width or not model_height:
        return marker
    target = record.get("target_window") if isinstance(record.get("target_window"), dict) else None
    action_space = record.get("action_coordinate_system") if isinstance(record.get("action_coordinate_system"), dict) else None
    reference = target or action_space
    ref_width = _number(reference.get("width")) if isinstance(reference, dict) else None
    ref_height = _number(reference.get("height")) if isinstance(reference, dict) else None
    ref_x = _number(reference.get("x")) if isinstance(reference, dict) else 0
    ref_y = _number(reference.get("y")) if isinstance(reference, dict) else 0
    screen_x = _number(marker.get("screen_x"))
    screen_y = _number(marker.get("screen_y"))
    if ref_width and ref_height and screen_x is not None and screen_y is not None:
        scaled = dict(marker)
        scaled["x"] = round((screen_x - (ref_x or 0)) * max(model_width - 1, 0) / max(ref_width - 1, 1))
        scaled["y"] = round((screen_y - (ref_y or 0)) * max(model_height - 1, 0) / max(ref_height - 1, 1))
        scaled["coordinate_space"] = "model_image"
        return scaled
    image_size = record.get("image_size")
    image_width = _number(image_size.get("width")) if isinstance(image_size, dict) else None
    image_height = _number(image_size.get("height")) if isinstance(image_size, dict) else None
    marker_x = _number(marker.get("x"))
    marker_y = _number(marker.get("y"))
    if image_width and image_height and marker_x is not None and marker_y is not None:
        scaled = dict(marker)
        scaled["x"] = round(marker_x * max(model_width - 1, 0) / max(image_width - 1, 1))
        scaled["y"] = round(marker_y * max(model_height - 1, 0) / max(image_height - 1, 1))
        scaled["coordinate_space"] = "model_image"
        return scaled
    return marker


def _scale_drag_marker_to_model(marker, record):
    if not isinstance(marker, dict):
        return marker
    scaled = dict(marker)
    if isinstance(scaled.get("from"), dict):
        scaled["from"] = _scale_marker_to_model(scaled.get("from"), record)
    if isinstance(scaled.get("to"), dict):
        scaled["to"] = _scale_marker_to_model(scaled.get("to"), record)
    return scaled


def _display_record_for_image(value, inherited, key, item):
    record = dict(inherited)
    model_path = value.get("model_image_path") if isinstance(value, dict) else None
    if isinstance(model_path, str) and model_path:
        record["path"] = model_path
        record["source_path"] = item
        record["path_key"] = "model_image_path"
        if isinstance(value.get("model_image_size"), dict):
            record["image_size"] = value.get("model_image_size")
        for marker_key in ("click_marker", "marker"):
            if marker_key in record:
                record[marker_key] = _scale_marker_to_model(record.get(marker_key), record)
        if "drag_marker" in record:
            record["drag_marker"] = _scale_drag_marker_to_model(record.get("drag_marker"), record)
        return record
    record["path"] = item
    record["path_key"] = key
    return record


def _candidate_image_records(value, inherited=None):
    inherited = dict(inherited or {})
    if isinstance(value, dict):
        local = dict(inherited)
        for meta_key in (
            "click_marker",
            "marker",
            "drag_marker",
            "target",
            "target_window",
            "image_size",
            "model_image_size",
            "action_coordinate_system",
            "action",
        ):
            if meta_key in value:
                local[meta_key] = value.get(meta_key)
        for key, item in value.items():
            if key in {"path", "screenshot_path"} and isinstance(item, str):
                yield _display_record_for_image(value, local, key, item)
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
    try:
        limit = int(input_data.get("limit", 8))
    except Exception:
        limit = 8
    limit = max(1, min(limit, 12))

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
        if tool_name not in {"browser_companion", "browser_computer", "browser_use", "computer_use"}:
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
            for meta_key in ("click_marker", "marker", "drag_marker", "target", "target_window", "image_size", "action"):
                if meta_key in candidate:
                    item[meta_key] = candidate.get(meta_key)
            screenshots.append(item)

    omitted_count = max(len(screenshots) - limit, 0)
    if omitted_count:
        screenshots = screenshots[-limit:]
    return ok(
        {
            "conversation_id": conversation_id,
            "run_id": run_id,
            "screenshots": screenshots,
            "omitted_count": omitted_count,
        }
    )
