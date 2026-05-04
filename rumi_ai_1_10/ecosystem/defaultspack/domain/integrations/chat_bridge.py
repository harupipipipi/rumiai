from __future__ import annotations

from typing import Any, Dict, List

from domain.chat.store import ChatStore
from domain.integrations.store import IntegrationConversationStore


def dispatch_external_message(
    *,
    provider: str,
    text: str,
    external_key: str,
    title: str,
    event_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    model: str | None = None,
    tools: List[Any] | None = None,
    params: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cleaned_text = str(text or "").strip()
    if not cleaned_text:
        return {
            "status": "ignored",
            "reason": "empty message",
            "assistant_text": "",
        }

    integration_store = IntegrationConversationStore()
    if integration_store.is_event_processed(provider, event_id):
        return {
            "status": "duplicate",
            "event_id": event_id,
            "assistant_text": "",
        }

    chat_store = ChatStore()
    external_metadata = metadata if isinstance(metadata, dict) else {}
    conversation = integration_store.get_or_create_conversation(
        provider=provider,
        external_key=external_key,
        title=title,
        metadata=external_metadata,
        chat_store=chat_store,
        model=model,
    )

    from blocks.chat.send import run as send_run

    request: Dict[str, Any] = {
        "conversation_id": conversation["id"],
        "message": {
            "role": "user",
            "content": cleaned_text,
            "metadata": {
                "source": "external_integration",
                "external": {
                    "provider": provider,
                    "external_key": external_key,
                    "event_id": event_id,
                    **external_metadata,
                },
            },
        },
        "params": params if isinstance(params, dict) else {},
    }
    if tools is not None:
        request["tools"] = tools

    result = send_run(request, context or {})
    if not isinstance(result, dict) or result.get("status") != "ok":
        return {
            "status": "error",
            "conversation_id": conversation["id"],
            "error": result.get("error") if isinstance(result, dict) else str(result),
            "assistant_text": "",
        }

    assistant = result.get("data") if isinstance(result.get("data"), dict) else {}
    payload = {
        "status": "ok",
        "provider": provider,
        "event_id": event_id,
        "conversation_id": conversation["id"],
        "assistant_message_id": assistant.get("id"),
        "assistant_text": extract_assistant_text(assistant),
    }
    integration_store.mark_event_processed(provider, event_id, payload)
    return payload


def extract_assistant_text(message: Dict[str, Any]) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()
