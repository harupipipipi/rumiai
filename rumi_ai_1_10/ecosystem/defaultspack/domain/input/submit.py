from __future__ import annotations

from typing import Any

from domain.integrations.store import IntegrationConversationStore
from domain.input.conversation_resolver import ExternalConversationResolver
from domain.input.envelope import RumiInputEnvelope


def submit_input(envelope: RumiInputEnvelope | dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(envelope, dict):
        envelope = RumiInputEnvelope.from_dict(envelope)
    cleaned_text = str(envelope.input or "").strip()
    if not cleaned_text:
        return {"status": "ignored", "reason": "empty message", "assistant_text": ""}

    source = envelope.source if isinstance(envelope.source, dict) else {}
    provider = str(source.get("provider") or "external").strip()
    event_id = str(source.get("event_id") or "").strip()
    chat = envelope.chat if isinstance(envelope.chat, dict) else {}
    external_key = str(chat.get("external_key") or chat.get("conversation_id") or "").strip()
    if not external_key:
        external_key = str(source.get("external_key") or event_id or provider).strip()

    integration_store = IntegrationConversationStore()
    if integration_store.is_event_processed(provider, event_id):
        return {"status": "duplicate", "event_id": event_id, "assistant_text": ""}

    metadata = dict(envelope.metadata)
    metadata.setdefault("source", source)
    resolver = ExternalConversationResolver(integration_store=integration_store)
    conversation = resolver.resolve(
        provider=provider,
        external_key=external_key,
        title=str(chat.get("title") or f"{provider} {external_key}"),
        metadata=metadata,
        model=str(chat.get("model") or "") or None,
    )

    from blocks.chat.send import run as send_run

    request: dict[str, Any] = {
        "conversation_id": conversation["id"],
        "message": {
            "role": str(envelope.role or "user"),
            "content": cleaned_text,
            "metadata": {
                "source": "external_integration",
                "external": {
                    "provider": provider,
                    "external_key": external_key,
                    "event_id": event_id,
                    **metadata,
                },
            },
        },
        "params": dict(envelope.params),
        "tools": list(envelope.tools),
    }

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
        "assistant_text": _extract_assistant_text(assistant),
    }
    integration_store.mark_event_processed(provider, event_id, payload)
    return payload


def _extract_assistant_text(message: dict[str, Any]) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()
