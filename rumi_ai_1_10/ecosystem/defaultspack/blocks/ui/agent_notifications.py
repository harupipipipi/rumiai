"""Server-owned projection for the desktop agent notification center."""

from __future__ import annotations

import hashlib

from blocks._common import ok
from domain.chat.cancellation import get_chat_cancellation_registry
from domain.chat.store import ChatStore


_FAILED_FINISH_REASONS = {"failed", "error", "cancelled", "interrupted"}
_FAILED_STATES = {"failed", "error", "interrupted"}


def _record(value):
    return value if isinstance(value, dict) else {}


def _text(message):
    raw = message.get("raw_text")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            str(block.get("text") or "").strip()
            for block in content if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return ""


def _pending(message):
    metadata = _record(message.get("metadata"))
    if _record(metadata.get("pending_authority_approval") or metadata.get("pendingAuthorityApproval")):
        return True
    if _record(metadata.get("pending_approval") or metadata.get("pendingApproval")):
        return True
    return any(
        isinstance(event, dict)
        and str(event.get("type") or event.get("phase") or "").lower() == "approval_requested"
        for event in (message.get("events") or [])
    )


def _failed(message):
    if str(message.get("finish_reason") or "").lower() in _FAILED_FINISH_REASONS:
        return True
    metadata = _record(message.get("metadata"))
    transport = _record(metadata.get("transport"))
    if str(transport.get("status") or "").lower() in _FAILED_STATES:
        return True
    for event in message.get("events") or []:
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").lower() == "task_failed":
            return True
        if str(event.get("status") or "").lower() in {"failed", "error"}:
            return True
    return False


def _streaming(message):
    metadata = _record(message.get("metadata"))
    return metadata.get("streaming") is True or str(message.get("finish_reason") or "").lower() == "streaming"


def _source(conversation):
    metadata = _record(conversation.get("metadata"))
    for key in ("workspace_label", "workspace_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    provider = metadata.get("external_provider")
    if isinstance(provider, str) and provider.strip():
        return provider.strip().upper()
    kind = str(conversation.get("conversation_kind") or "")
    return {"coding": "Coding", "operations_company": "Operations", "mimo_coding_company": "Mimo Coding"}.get(kind, "Chat")


def _projection(conversation, registry):
    messages = [item for item in (conversation.get("messages") or []) if isinstance(item, dict)]
    latest = messages[-1] if messages else {}
    conversation_id = str(conversation.get("id") or "")
    if registry.has_active_callbacks(conversation_id) or _streaming(latest):
        status = "running"
    elif _failed(latest):
        status = "failed"
    elif _pending(latest):
        status = "waiting"
    else:
        status = "done"
    text = " ".join(_text(latest).split())
    fallback = {"running": "Agent が実行中です", "waiting": "承認または判断を待っています", "failed": "Agent の実行が失敗しました", "done": "Agent の応答が完了しました"}[status]
    tools = []
    for event in latest.get("events") or []:
        name = str(event.get("tool_name") or "").strip() if isinstance(event, dict) else ""
        if name and name not in tools:
            tools.append(name)
    updated_at = int(conversation.get("updated_at") or latest.get("created_at") or 0)
    summary = (fallback if status in {"running", "waiting"} else text or fallback)[:180]
    return {
        "id": f"{conversation_id}:{status}", "conversation_id": conversation_id,
        "title": str(conversation.get("title") or "Untitled conversation").strip(),
        "status": status, "summary": summary, "source": _source(conversation),
        "tool_names": tools[:4], "updated_at": updated_at,
        "fingerprint": f"{conversation_id}:{status}:{updated_at}:{summary}",
    }


def run(input_data, context):
    del input_data, context
    store = ChatStore()
    conversations, _ = store.list_conversations(limit=120, is_archived=False, include_messages=True)
    registry = get_chat_cancellation_registry()
    namespace = hashlib.sha256(str(store._storage_path.resolve()).encode("utf-8")).hexdigest()[:20]
    return ok({"storage_namespace": namespace, "items": [_projection(item, registry) for item in conversations]})
