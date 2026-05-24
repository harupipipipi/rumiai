import mimetypes
from pathlib import Path

from blocks._common import error
from domain.coding.workspace_store import WorkspaceStore
from domain.chat.store import ChatStore


def _pack_root():
    return Path(__file__).resolve().parents[2]


def _allowed_roots(store, conversation_id, conversation=None):
    pack_root = _pack_root()
    roots = [
        store.conversation_workspace_dir(conversation_id).resolve(),
        (pack_root / "user_data" / "artifacts").resolve(),
    ]
    metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
    if isinstance(metadata, dict):
        workspace_store = WorkspaceStore()
        workspace_id = str(metadata.get("workspace_id") or metadata.get("workspaceId") or "").strip()
        workspace_record = workspace_store.get(workspace_id) if workspace_id else None
        if workspace_record and workspace_record.get("trusted") is True:
            try:
                roots.append(Path(str(workspace_record.get("root_path") or "")).expanduser().resolve())
            except Exception:
                pass
        for key in ("workspace_root", "workspaceRoot", "rootPath"):
            root = metadata.get(key)
            if not isinstance(root, str) or not root.strip():
                continue
            try:
                record = workspace_store.find_by_root(root)
            except Exception:
                record = None
            if record and record.get("trusted") is True:
                try:
                    roots.append(Path(str(record.get("root_path") or root)).expanduser().resolve())
                except Exception:
                    pass
    unique_roots = []
    seen = set()
    for root in roots:
        marker = str(root)
        if marker in seen:
            continue
        seen.add(marker)
        unique_roots.append(root)
    return unique_roots


def _resolve_allowed_path(raw_path, roots):
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path).expanduser()
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.extend(root / path for root in roots)
    for root in roots:
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if not resolved.is_file():
                continue
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

    resolved = _resolve_allowed_path(input_data.get("path"), _allowed_roots(store, conversation_id, conversation))
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
