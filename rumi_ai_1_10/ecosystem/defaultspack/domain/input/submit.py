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
    if not integration_store.claim_event(
        provider,
        event_id,
        metadata={"external_key": external_key},
    ):
        if integration_store.is_event_processed(provider, event_id):
            return {"status": "duplicate", "event_id": event_id, "assistant_text": ""}
        return {"status": "in_progress", "event_id": event_id, "assistant_text": ""}

    metadata = dict(envelope.metadata)
    metadata.setdefault("source", source)
    display_text = cleaned_text
    runtime_text = apply_external_source_context(display_text, envelope, source=source, metadata=metadata)
    runtime_text = apply_external_runtime_prompt(runtime_text, context)
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
            "content": display_text,
            "metadata": {
                "source": "external_integration",
                "external": {
                    "provider": provider,
                    "external_key": external_key,
                    "event_id": event_id,
                    **metadata,
                    "source_text": display_text,
                    **({"runtime_content": runtime_text} if runtime_text != display_text else {}),
                },
            },
        },
        "params": dict(envelope.params),
        "tools": list(envelope.tools),
    }

    try:
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
    finally:
        integration_store.release_event_claim(provider, event_id)


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


def apply_external_source_context(
    text: str,
    envelope: RumiInputEnvelope | dict[str, Any],
    *,
    source: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    if isinstance(envelope, dict):
        envelope = RumiInputEnvelope.from_dict(envelope)
    params = envelope.params if isinstance(envelope.params, dict) else {}
    external_input = params.get("external_input") if isinstance(params.get("external_input"), dict) else {}
    default_response = external_input.get("default_response") if isinstance(external_input.get("default_response"), dict) else {}
    if not bool(default_response.get("include_source_context", False)):
        return text
    source = source if isinstance(source, dict) else envelope.source if isinstance(envelope.source, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else envelope.metadata if isinstance(envelope.metadata, dict) else {}
    provider = str(source.get("provider") or metadata.get("provider") or "external").strip() or "external"
    external_event = metadata.get("external_event") if isinstance(metadata.get("external_event"), dict) else {}
    scope = external_event.get("scope") if isinstance(external_event.get("scope"), dict) else {}
    actor = external_event.get("actor") if isinstance(external_event.get("actor"), dict) else {}
    scope_text = _principal_label(scope)
    actor_text = _principal_label(actor)
    format_text = str(default_response.get("source_context_format") or "${provider}から来た入力です。")
    prefix = (
        format_text.replace("${provider}", provider)
        .replace("${scope}", scope_text)
        .replace("${actor}", actor_text)
    ).strip()
    details = []
    if scope_text:
        details.append(f"scope={scope_text}")
    if actor_text:
        details.append(f"actor={actor_text}")
    detail_text = f" ({', '.join(details)})" if details else ""
    return f"[External source: {prefix}{detail_text}]\n{text}".strip()


def apply_external_runtime_prompt(text: str, context: dict[str, Any] | None = None) -> str:
    context = context if isinstance(context, dict) else {}
    prefix = str(
        context.get("external_prompt_prefix")
        or context.get("external_instruction_prefix")
        or context.get("prompt_prefix")
        or ""
    ).strip()
    suffix = str(
        context.get("external_prompt_suffix")
        or context.get("external_instruction_suffix")
        or context.get("prompt_suffix")
        or ""
    ).strip()
    updated = str(text or "").strip()
    if prefix:
        updated = f"{prefix}\n\n{updated}".strip()
    if suffix:
        updated = f"{updated}\n\n{suffix}".strip()
    return updated


def _principal_label(value: dict[str, Any]) -> str:
    principal_type = str(value.get("type") or "").strip()
    principal_id = str(value.get("id") or "").strip()
    if principal_type and principal_id:
        return f"{principal_type}:{principal_id}"
    return principal_id or principal_type
