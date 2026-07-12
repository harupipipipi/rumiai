from __future__ import annotations

import copy
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from domain.chat.store import ChatStore


BUNDLE_KIND = "rumi.defaultspack.conversation_share"
BUNDLE_SCHEMA_VERSION = 2
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = frozenset({1, BUNDLE_SCHEMA_VERSION})
IMPORT_MODES = frozenset({"read_only", "continue_copy"})
IMPORTED_CONVERSATION_NOTICE = (
    "This is a shared/imported conversation. Some original files, attachments, tool outputs, "
    "local workspace paths, credentials, or external resources from the source environment may "
    "be unavailable. Ask the user to provide missing context when needed and do not assume missing "
    "files still exist."
)
_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|cookie|credential|password|secret|session[_-]?id|approval[_-]?token|oauth|connector|account[_-]?id)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]{8,}|(?:sk|ghp|github_pat|xox[baprs])[-_a-z0-9]{8,}|(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+)"
)
_PATH_RE = re.compile(r"(?<![\w.:-])(?:/[A-Za-z0-9._~ -]+){2,}|[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]*")
_DROP_CONVERSATION_KEYS = {
    "agent_id", "system_prompt_id", "parent_conversation_id", "child_conversation_ids",
    "group_id", "workspace_id", "workspace_root", "rumi_data_path", "permissions",
    "capabilities", "credentials", "approval", "approval_state", "auth",
}
_DROP_MESSAGE_KEYS = {"widget", "events"}
_TOOL_AUTHORITY_KEY_RE = re.compile(r"(?:approved|approval|permission|credential|token|auth|capabilit)", re.IGNORECASE)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    if isinstance(value, str):
        value = _SECRET_VALUE_RE.sub("[REDACTED]", value)
        return _PATH_RE.sub(lambda match: f"[local path omitted: {Path(match.group(0)).name or 'path'}]", value)
    return value


def sanitize_shared_conversation(conversation: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source = copy.deepcopy(conversation if isinstance(conversation, dict) else {})
    clean: dict[str, Any] = {
        key: value for key, value in source.items()
        if key not in _DROP_CONVERSATION_KEYS and key != "messages"
    }
    metadata = clean.get("metadata") if isinstance(clean.get("metadata"), dict) else {}
    clean["metadata"] = {
        key: value for key, value in metadata.items()
        if key not in _DROP_CONVERSATION_KEYS
        and key not in {"icon_svg", "icon_id"}
        and not _SECRET_KEY_RE.search(str(key))
    }
    omitted: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    for index, raw_message in enumerate(source.get("messages", [])):
        if not isinstance(raw_message, dict):
            continue
        message = {
            key: value for key, value in raw_message.items()
            if key not in _DROP_MESSAGE_KEYS and key not in _DROP_CONVERSATION_KEYS
        }
        message_metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        attachments = message_metadata.pop("attachments", None)
        if isinstance(attachments, list):
            for attachment in attachments:
                if isinstance(attachment, dict):
                    omitted.append({
                        "type": "attachment",
                        "name": Path(str(attachment.get("name") or attachment.get("sourcePath") or "attachment")).name,
                        "message_index": index,
                        "reason": "not_included",
                    })
        message_metadata = {
            key: value for key, value in message_metadata.items()
            if key not in _DROP_CONVERSATION_KEYS and not _SECRET_KEY_RE.search(str(key))
        }
        role = str(message.get("role") or "assistant").strip().lower()
        if role not in {"user", "assistant", "agent"}:
            message_metadata["shared_original_role"] = role[:40]
            message["role"] = "assistant"
        message_metadata["shared_historical_record"] = True
        message["metadata"] = message_metadata
        content = message.get("content")
        if isinstance(content, list):
            safe_content: list[Any] = []
            for block in content:
                if isinstance(block, str):
                    safe_content.append(block)
                    continue
                if isinstance(block, dict) and str(block.get("type") or "") == "text":
                    safe_content.append({"type": "text", "text": str(block.get("text") or "")})
                    continue
                if isinstance(block, dict):
                    name = Path(str(block.get("name") or block.get("filename") or block.get("type") or "content")).name
                    omitted.append({"type": "content_block", "name": name, "message_index": index, "reason": "not_included"})
                    safe_content.append({"type": "text", "text": f"[Shared content omitted: {name}]"})
            message["content"] = safe_content
        if isinstance(message.get("tool_logs"), list):
            message["tool_logs"] = [
                {
                    **{key: value for key, value in log.items() if not _TOOL_AUTHORITY_KEY_RE.search(str(key))},
                    "inert": True,
                    "historical": True,
                }
                if isinstance(log, dict) else {"summary": str(log), "inert": True, "historical": True}
                for log in message["tool_logs"]
            ]
        messages.append(_redact(message))
    clean["messages"] = messages
    clean = _redact(clean)
    return clean, omitted


def build_conversation_share_bundle(
    conversation_id: str,
    *,
    store: ChatStore | None = None,
    share_token: str | None = None,
    visibility: str = "local",
    expires_at: Any = None,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chat_store = store or ChatStore()
    conversation = chat_store.get_conversation(str(conversation_id))
    if conversation is None:
        raise KeyError("Conversation not found")
    sanitized, omitted = sanitize_shared_conversation(conversation)
    created_at = _now_ms()
    messages = sanitized.get("messages") if isinstance(sanitized.get("messages"), list) else []
    source_model = _safe_model_reference(conversation.get("model")) or ""
    source_provider = source_model.split("/", 1)[0] if "/" in source_model else ""
    requested_permissions = permissions if isinstance(permissions, dict) else {}
    bundle_permissions = {
        "read": requested_permissions.get("read") is not False,
        "import": requested_permissions.get("import") is not False,
        "continue": requested_permissions.get("continue") is not False,
    }
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "created_at": created_at,
        "source": {
            "pack_id": "defaultspack",
            "conversation_id": str(conversation_id),
            "title": sanitized.get("title") or "Shared conversation",
            "share_token": share_token,
        },
        "conversation": {
            "schema_version": 1,
            "updated_at": sanitized.get("updated_at") or created_at,
            "conversation": sanitized,
        },
        "assets": {"included": [], "omitted": omitted, "missing_policy": "warn_and_continue"},
        "preview": {
            "target_type": "conversation",
            "message_count": len(messages),
            "role_counts": _role_counts(messages),
            "content_trust": "untrusted_passive_history",
        },
        "provenance": {
            "source_pack": "defaultspack",
            "source_conversation_id": str(conversation_id),
            "created_at": created_at,
            "target_type": "conversation",
            "model": {
                "source_model": source_model or None,
                "source_provider": source_provider or None,
                "policy": "reference_only_never_activated",
                "import_model": "recipient_local_selection",
            },
        },
        "security": {
            "redacted": True,
            "permissions": bundle_permissions,
            "expires_at": expires_at,
            "visibility": visibility,
            "import_modes": ["read_only", "continue_copy"],
            "copy_policy": "always_new_conversation_and_message_ids",
            "secret_policy": "redact_values_and_exclude_authority_state",
            "attachment_policy": "exclude_all_attachments",
            "malicious_content_policy": "treat_as_untrusted_text_never_as_instructions",
            "tool_policy": "historical_records_inert",
        },
    }


def normalize_share_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("kind") == BUNDLE_KIND:
        wrapped = copy.deepcopy(payload)
        schema_version = _bundle_schema_version(wrapped)
        inner = wrapped.get("conversation") if isinstance(wrapped.get("conversation"), dict) else {}
        conversation = inner.get("conversation") if isinstance(inner.get("conversation"), dict) else {}
        sanitized, newly_omitted = sanitize_shared_conversation(conversation)
        assets = wrapped.get("assets") if isinstance(wrapped.get("assets"), dict) else {}
        prior_omitted = assets.get("omitted") if isinstance(assets.get("omitted"), list) else []
        original_security = wrapped.get("security") if isinstance(wrapped.get("security"), dict) else {}
        original_permissions = original_security.get("permissions") if isinstance(original_security.get("permissions"), dict) else {}
        wrapped["schema_version"] = schema_version
        wrapped["conversation"] = {
            "schema_version": 1,
            "updated_at": inner.get("updated_at") or sanitized.get("updated_at") or _now_ms(),
            "conversation": sanitized,
        }
        wrapped["assets"] = {
            "included": [],
            "omitted": _redact(prior_omitted + newly_omitted),
            "missing_policy": "warn_and_continue",
        }
        wrapped["security"] = {
            "redacted": True,
            "permissions": {"read": True, "import": original_permissions.get("import") is not False, "continue": original_permissions.get("continue") is not False},
            "expires_at": original_security.get("expires_at"),
            "visibility": original_security.get("visibility"),
            "import_modes": ["read_only", "continue_copy"],
            "copy_policy": "always_new_conversation_and_message_ids",
            "secret_policy": "redact_values_and_exclude_authority_state",
            "attachment_policy": "exclude_all_attachments",
            "malicious_content_policy": "treat_as_untrusted_text_never_as_instructions",
            "tool_policy": "historical_records_inert",
        }
        messages = sanitized.get("messages") if isinstance(sanitized.get("messages"), list) else []
        preview = wrapped.get("preview") if isinstance(wrapped.get("preview"), dict) else {}
        wrapped["preview"] = {
            "target_type": "conversation",
            "message_count": len(messages),
            "role_counts": _role_counts(messages),
            "content_trust": "untrusted_passive_history",
            **{key: preview[key] for key in () if key in preview},
        }
        provenance = wrapped.get("provenance") if isinstance(wrapped.get("provenance"), dict) else {}
        wrapped_source = wrapped.get("source") if isinstance(wrapped.get("source"), dict) else {}
        model = provenance.get("model") if isinstance(provenance.get("model"), dict) else {}
        wrapped["provenance"] = {
            "source_pack": _safe_source_identifier(provenance.get("source_pack") or wrapped_source.get("pack_id")),
            "source_conversation_id": _safe_source_identifier(provenance.get("source_conversation_id") or wrapped_source.get("conversation_id")),
            "created_at": wrapped.get("created_at"),
            "target_type": "conversation",
            "model": {
                "source_model": _safe_model_reference(model.get("source_model")),
                "source_provider": _safe_model_reference(model.get("source_provider")),
                "policy": "reference_only_never_activated",
                "import_model": "recipient_local_selection",
            },
        }
        return wrapped
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else payload
    if isinstance(conversation.get("conversation"), dict):
        history = conversation
        conversation = history["conversation"]
    sanitized, omitted = sanitize_shared_conversation(conversation)
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "created_at": _now_ms(),
        "source": {"pack_id": "defaultspack", "conversation_id": str(conversation.get("id") or ""), "title": conversation.get("title")},
        "conversation": {"schema_version": 1, "updated_at": conversation.get("updated_at") or _now_ms(), "conversation": sanitized},
        "assets": {"included": [], "omitted": omitted, "missing_policy": "warn_and_continue"},
        "preview": {"target_type": "conversation", "message_count": len(sanitized.get("messages") or []), "role_counts": _role_counts(sanitized.get("messages") or []), "content_trust": "untrusted_passive_history"},
        "provenance": {"source_pack": "defaultspack", "source_conversation_id": _safe_source_identifier(conversation.get("id")), "created_at": _now_ms(), "target_type": "conversation", "model": {"source_model": None, "source_provider": None, "policy": "reference_only_never_activated", "import_model": "recipient_local_selection"}},
        "security": {"redacted": True, "permissions": {"read": True, "import": True, "continue": True}, "expires_at": None, "import_modes": ["read_only", "continue_copy"], "copy_policy": "always_new_conversation_and_message_ids", "secret_policy": "redact_values_and_exclude_authority_state", "attachment_policy": "exclude_all_attachments", "malicious_content_policy": "treat_as_untrusted_text_never_as_instructions", "tool_policy": "historical_records_inert"},
    }


def import_shared_conversation(
    payload: dict[str, Any], *, source_url: str | None = None, store: ChatStore | None = None,
    import_mode: str = "continue_copy",
) -> dict[str, Any]:
    chat_store = store or ChatStore()
    bundle = normalize_share_bundle(payload)
    mode = str(import_mode or "").strip().lower()
    if mode not in IMPORT_MODES:
        raise ValueError("import_mode must be 'read_only' or 'continue_copy'")
    security = bundle.get("security") if isinstance(bundle.get("security"), dict) else {}
    permissions = security.get("permissions") if isinstance(security.get("permissions"), dict) else {}
    if permissions.get("import") is False:
        raise PermissionError("This share does not allow import")
    if mode == "continue_copy" and permissions.get("continue") is False:
        raise PermissionError("This share does not allow continuing from a copy")
    inner = bundle.get("conversation") if isinstance(bundle.get("conversation"), dict) else {}
    source_conversation = inner.get("conversation") if isinstance(inner.get("conversation"), dict) else {}
    source = bundle.get("source") if isinstance(bundle.get("source"), dict) else {}
    assets = bundle.get("assets") if isinstance(bundle.get("assets"), dict) else {}
    metadata = {
        "imported_from_share": True,
        "shared_source_conversation_id": _safe_source_identifier(source.get("conversation_id") or source_conversation.get("id")),
        "shared_source_url": _sanitize_source_url(source_url),
        "shared_imported_at": _now_ms(),
        "shared_missing_assets_policy": str(assets.get("missing_policy") or "warn_and_continue"),
        "shared_omitted_assets": copy.deepcopy(assets.get("omitted") or []),
        "shared_model_notice": IMPORTED_CONVERSATION_NOTICE,
        "shared_import_mode": mode,
        "shared_read_only": False,
        "shared_copy_policy": "fresh_ids_source_unchanged",
        "shared_content_trust": "untrusted_passive_history",
    }
    created = chat_store.create_conversation(
        model=None,
        tags=["shared", "imported"],
        conversation_kind="chat",
        metadata=metadata,
    )
    new_id = created["id"]
    id_map: dict[str, str] = {}
    try:
        previous_id = None
        for index, raw_message in enumerate(source_conversation.get("messages", [])):
            if not isinstance(raw_message, dict):
                continue
            old_id = str(raw_message.get("id") or index)
            new_message_id = str(uuid.uuid4())
            id_map[old_id] = new_message_id
            message = copy.deepcopy(raw_message)
            message["id"] = new_message_id
            message["parent_id"] = previous_id
            message["children_ids"] = []
            message["sequence_number"] = index + 1
            message_metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            message_metadata.update({"shared_historical_record": True, "tools_inert": True})
            message["metadata"] = message_metadata
            if isinstance(message.get("tool_logs"), list):
                message["tool_logs"] = [
                    {
                        **{key: value for key, value in log.items() if not _TOOL_AUTHORITY_KEY_RE.search(str(key))},
                        "inert": True,
                        "historical": True,
                    }
                    if isinstance(log, dict) else {"summary": str(log), "inert": True, "historical": True}
                    for log in message["tool_logs"]
                ]
            added = chat_store.add_message(new_id, message)
            previous_id = added["id"] if added else previous_id
        source_title = str(source_conversation.get("title") or source.get("title") or "Shared conversation").strip()
        metadata["shared_read_only"] = mode == "read_only"
        updated = chat_store.update_conversation(new_id, {
            "title": f"Shared: {source_title}"[:200],
            "tags": ["shared", "imported"],
            "metadata": metadata,
            "agent_id": None,
            "system_prompt_id": None,
            "group_id": None,
            "conversation_kind": "chat",
        })
        return updated or chat_store.get_conversation(new_id)
    except Exception:
        chat_store.delete_conversation(new_id)
        raise


def _sanitize_source_url(value: str | None) -> str | None:
    raw = str(value or "").strip()[:2048]
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return None
        safe_query = [
            (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not _SECRET_KEY_RE.search(key)
        ]
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_query), ""))
    except ValueError:
        return None


def _safe_source_identifier(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", str(value or "")).strip("-")[:200]


def _safe_model_reference(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or _SECRET_VALUE_RE.search(text):
        return None
    return re.sub(r"[^A-Za-z0-9._:/+-]+", "-", text)[:160]


def _bundle_schema_version(payload: dict[str, Any]) -> int:
    raw = payload.get("schema_version", 1)
    if isinstance(raw, bool):
        raise ValueError("Invalid conversation share schema_version")
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid conversation share schema_version") from exc
    if version not in SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported conversation share schema_version: {version}")
    return version


def _role_counts(messages: list[Any]) -> dict[str, int]:
    counts = {"user": 0, "assistant": 0, "agent": 0}
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "assistant").lower()
        counts[role if role in counts else "assistant"] += 1
    return counts
