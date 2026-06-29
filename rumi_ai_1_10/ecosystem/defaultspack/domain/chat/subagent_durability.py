from __future__ import annotations

from typing import Any

from domain.chat.store import ChatStore


SUBAGENT_DURABLE_DRAFT_FLAG = "subagent_child_durable_draft"
SUBAGENT_PENDING_TEXT = (
    "The delegated agent is running. If this remains the latest message, "
    "the runner stopped before it could write a final response."
)
SUBAGENT_FAILED_TEXT = "The delegated agent could not complete before producing a response."
SUBAGENT_EMPTY_RESPONSE_TEXT = "The delegated agent completed without producing a visible response."
_FAILED_FINISH_REASONS = {"error", "failed", "failure", "timeout", "cancelled", "canceled"}
_FAILED_STATUSES = {"error", "failed", "failure", "timeout", "cancelled", "canceled"}


def is_subagent_child_conversation(
    conversation: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(conversation, dict):
        return False
    if isinstance(context, dict) and context.get("subagent_child_durable_draft") is True:
        return True
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    subagent = metadata.get("subagent") if isinstance(metadata.get("subagent"), dict) else {}
    if str(subagent.get("source") or "") == "subagent_tool":
        return True
    return (
        str(conversation.get("conversation_kind") or "") == "subagent"
        and bool(conversation.get("parent_conversation_id") or metadata.get("parent_conversation_id"))
    )


def should_create_subagent_durable_draft(
    conversation: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> bool:
    if isinstance(context, dict) and context.get("subagent_child_durable_draft") is False:
        return False
    return is_subagent_child_conversation(conversation, context)


def subagent_durable_draft_metadata(model: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params if isinstance(params, dict) else {}
    return {
        "source": "subagent_tool",
        SUBAGENT_DURABLE_DRAFT_FLAG: True,
        "status": "running",
        "model": model,
        "streaming": True,
        "draft": True,
        "thinking": {"state": "running"},
        "thinking_level": params.get("thinking_level"),
    }


def message_text(message: dict[str, Any]) -> str:
    raw = str(message.get("raw_text") or "").strip()
    if raw:
        return raw
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            elif isinstance(block, str):
                parts.append(block)
    return "\n".join(part for part in parts if part).strip()


def is_running_subagent_durable_draft(message: dict[str, Any]) -> bool:
    if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
        return False
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    if metadata.get(SUBAGENT_DURABLE_DRAFT_FLAG) is not True:
        return False
    finish_reason = str(message.get("finish_reason") or "").strip().lower()
    status = str(metadata.get("status") or "").strip().lower()
    return (
        finish_reason in {"", "streaming", "running"}
        or metadata.get("streaming") is True
        or metadata.get("draft") is True
        or status == "running"
    )


def is_failed_assistant_response(message: dict[str, Any]) -> bool:
    if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
        return False
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    finish_reason = str(message.get("finish_reason") or "").strip().lower()
    status = str(metadata.get("status") or message.get("status") or "").strip().lower()
    if finish_reason in _FAILED_FINISH_REASONS or status in _FAILED_STATUSES:
        return True
    if str(metadata.get("error_code") or metadata.get("error") or "").strip():
        return True
    text = message_text(message)
    return text in {SUBAGENT_FAILED_TEXT, SUBAGENT_EMPTY_RESPONSE_TEXT}


def has_completed_assistant_text(messages: list[Any]) -> bool:
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
            continue
        if is_running_subagent_durable_draft(message):
            continue
        if is_failed_assistant_response(message):
            continue
        if message_text(message):
            return True
    return False


def ensure_subagent_child_has_assistant_response(
    store: ChatStore,
    child_id: str,
    *,
    assistant_text: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    child = store.get_conversation(child_id) or {}
    messages = child.get("messages") if isinstance(child.get("messages"), list) else []
    if has_completed_assistant_text(messages):
        return None
    text = str(assistant_text or "").strip()
    if text:
        return _upsert_assistant_marker(
            store,
            child_id,
            metadata=metadata,
            text=text,
            status="completed",
            code="SUBAGENT_RESPONSE_REPAIRED",
            finish_reason="stop",
        )
    return _upsert_assistant_marker(
        store,
        child_id,
        metadata=metadata,
        text=SUBAGENT_EMPTY_RESPONSE_TEXT,
        status="error",
        code="SUBAGENT_EMPTY_RESPONSE",
        finish_reason="error",
    )


def mark_subagent_child_failed(
    store: ChatStore,
    child_id: str,
    *,
    metadata: dict[str, Any] | None = None,
    code: str,
    text: str = SUBAGENT_FAILED_TEXT,
) -> dict[str, Any] | None:
    child = store.get_conversation(child_id) or {}
    messages = child.get("messages") if isinstance(child.get("messages"), list) else []
    if has_completed_assistant_text(messages):
        _update_child_metadata(store, child_id, metadata=metadata, status="error", code=code)
        return None
    return _upsert_assistant_marker(
        store,
        child_id,
        metadata=metadata,
        text=text,
        status="error",
        code=code,
        finish_reason="error",
    )


def _upsert_assistant_marker(
    store: ChatStore,
    child_id: str,
    *,
    metadata: dict[str, Any] | None,
    text: str,
    status: str,
    code: str,
    finish_reason: str,
) -> dict[str, Any] | None:
    _update_child_metadata(store, child_id, metadata=metadata, status=status, code=code)
    child = store.get_conversation(child_id) or {}
    messages = child.get("messages") if isinstance(child.get("messages"), list) else []
    existing = _latest_repairable_assistant(messages)
    message_updates = {
        "content": [{"type": "text", "text": text}],
        "raw_text": text,
        "finish_reason": finish_reason,
        "usage": {},
        "metadata": {
            "source": "subagent_tool",
            "status": status,
            "error_code": code,
            "final": True,
        },
        "events": [],
        "tool_logs": [],
    }
    if existing:
        return store.update_message(child_id, str(existing.get("id") or ""), message_updates)
    return store.add_message(
        child_id,
        {
            "role": "assistant",
            **message_updates,
        },
    )


def _latest_repairable_assistant(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages if isinstance(messages, list) else []):
        if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
            continue
        if is_running_subagent_durable_draft(message):
            return message
        if is_failed_assistant_response(message):
            return message
        if not message_text(message):
            return message
    return None


def _update_child_metadata(
    store: ChatStore,
    child_id: str,
    *,
    metadata: dict[str, Any] | None,
    status: str,
    code: str,
) -> None:
    child = store.get_conversation(child_id) or {}
    updated_metadata = dict(child.get("metadata") if isinstance(child.get("metadata"), dict) else metadata or {})
    subagent_metadata = dict(updated_metadata.get("subagent") or {})
    subagent_metadata.update({"status": status, "error_code": code})
    updated_metadata["subagent"] = subagent_metadata
    try:
        store.update_conversation(child_id, {"metadata": updated_metadata})
    except Exception:
        pass
