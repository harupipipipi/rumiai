from __future__ import annotations

import re
from typing import Any

from domain.external.source_store import ExternalSourceStore
from domain.external.targeting import origin_from_external_event


CHAT_LINK_PROMPT = "chatidを入力するか、新規チャットをする場合は /newchat で。"

_CHANGE_COMMANDS = {"change", "chatid", "usechat"}
_NEWCHAT_COMMANDS = {"newchat", "new-chat", "new_chat"}
_PLAIN_CHAT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,159}$")


def prepare_source_record(event, context: dict[str, Any], *, verified: bool | None = None) -> dict[str, Any]:
    origin = origin_from_external_event(event)
    source_record = context.get("source_record") if isinstance(context.get("source_record"), dict) else None
    if not isinstance(source_record, dict) or not isinstance(source_record.get("source"), dict):
        source_record = ExternalSourceStore().record_origin(
            origin,
            verified=bool(getattr(event, "verified", False) if verified is None else verified),
        )
    context["source_record"] = source_record
    if isinstance(getattr(event, "metadata", None), dict):
        event.metadata["origin"] = origin.as_dict()
        event.metadata["source_record"] = source_record
    linked_id = linked_conversation_id(context)
    if linked_id:
        context.setdefault("conversation_id", linked_id)
        if isinstance(getattr(event, "metadata", None), dict):
            event.metadata["linked_conversation_id"] = linked_id
    return source_record


def handle_chat_link_message(
    event,
    context: dict[str, Any],
    text: str,
    *,
    model: str | None = None,
) -> dict[str, Any] | None:
    prepare_source_record(event, context)
    cleaned = _clean_message_text(text)
    command, arg = _parse_command(cleaned)
    if command in _NEWCHAT_COMMANDS:
        return _new_chat_result(event, context, model=model)
    if command in _CHANGE_COMMANDS:
        candidate = _strip_wrapping_quotes(arg)
        if not candidate:
            return _response(event.provider, CHAT_LINK_PROMPT, action="prompt")
        return _link_existing_result(event, context, candidate)

    if cleaned and _PLAIN_CHAT_ID_RE.match(cleaned):
        conversation = _get_conversation(cleaned)
        if isinstance(conversation, dict):
            return _link_conversation_result(event, context, conversation)

    if not linked_conversation_id(context):
        return _response(event.provider, CHAT_LINK_PROMPT, action="prompt")
    return None


def linked_conversation_id(context: dict[str, Any]) -> str:
    source = _context_source(context)
    conversation_id = str(source.get("linked_conversation_id") or "").strip()
    if not conversation_id:
        return ""
    conversation = _get_conversation(conversation_id)
    if not isinstance(conversation, dict):
        return ""
    return str(conversation.get("id") or conversation_id).strip()


def envelope_overrides(context: dict[str, Any]) -> dict[str, Any] | None:
    conversation_id = linked_conversation_id(context)
    if not conversation_id:
        return None
    return {"target": {"conversation_id": conversation_id, "direct": True}}


def _link_existing_result(event, context: dict[str, Any], chat_id: str) -> dict[str, Any]:
    conversation = _get_conversation(chat_id)
    if not isinstance(conversation, dict):
        return _response(event.provider, f"chatidが見つかりません。\n{CHAT_LINK_PROMPT}", action="not_found")
    return _link_conversation_result(event, context, conversation)


def _link_conversation_result(event, context: dict[str, Any], conversation: dict[str, Any]) -> dict[str, Any]:
    origin = origin_from_external_event(event)
    conversation_id = str(conversation.get("id") or "").strip()
    title = str(conversation.get("title") or "").strip()
    store = ExternalSourceStore()
    result = store.set_linked_conversation(
        origin.provider,
        origin.source_type,
        origin.source_id,
        conversation_id,
        title=title,
        actor_id=origin.actor_id,
        enabled=True,
    )
    if not result.get("success"):
        return _response(event.provider, "chatidリンクに失敗しました。", action="error")
    context["source_record"] = {"saved": True, "key": result.get("key"), "source": result.get("source")}
    context["conversation_id"] = conversation_id
    if isinstance(getattr(event, "metadata", None), dict):
        event.metadata["source_record"] = context["source_record"]
        event.metadata["linked_conversation_id"] = conversation_id
    suffix = f"\n{title}" if title and title != "New Conversation" else ""
    return _response(event.provider, f"この会話はchatid {conversation_id} を続けます。{suffix}", action="linked", conversation_id=conversation_id)


def _new_chat_result(event, context: dict[str, Any], *, model: str | None = None) -> dict[str, Any]:
    origin = origin_from_external_event(event)
    try:
        from domain.chat.store import ChatStore

        store = ChatStore()
        conversation = store.create_conversation(
            model=str(model or "").strip() or None,
            tags=[f"integration:{origin.provider}"],
            metadata={
                "external_chat_link": {
                    "provider": origin.provider,
                    "source_type": origin.source_type,
                    "source_id": origin.source_id,
                }
            },
        )
        title = f"{origin.provider} {origin.source_type} {_short_id(origin.source_id)}"
        conversation = store.update_conversation(conversation["id"], {"title": title}) or conversation
    except Exception as exc:
        return _response(event.provider, f"新規チャットの作成に失敗しました: {exc}", action="error")
    linked = _link_conversation_result(event, context, conversation)
    linked["external_chat_link"]["action"] = "newchat"
    conversation_id = str(linked["external_chat_link"].get("conversation_id") or conversation.get("id") or "").strip()
    title = str(conversation.get("title") or "").strip()
    suffix = f"\n{title}" if title and title != "New Conversation" else ""
    linked["assistant_text"] = f"新規チャットを開始しました。\nchatid: {conversation_id}{suffix}"
    linked["response_plan"]["messages"][0]["text"] = linked["assistant_text"]
    return linked


def _response(provider: str, text: str, *, action: str, conversation_id: str = "") -> dict[str, Any]:
    plan = {
        "provider": provider,
        "messages": [{"type": "text", "text": text}],
        "metadata": {"external_chat_link": {"action": action, **({"conversation_id": conversation_id} if conversation_id else {})}},
    }
    return {
        "status": "ok",
        "assistant_text": text,
        "external_chat_link": {"action": action, **({"conversation_id": conversation_id} if conversation_id else {})},
        "response_plan": plan,
    }


def _parse_command(text: str) -> tuple[str, str]:
    if not text.startswith("/"):
        return "", ""
    body = text[1:].strip()
    if not body:
        return "", ""
    command, _sep, rest = body.partition(" ")
    return command.strip().lower(), rest.strip()


def _clean_message_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^(?:<@[A-Z0-9][A-Z0-9_-]*>\s*)+", "", cleaned, flags=re.IGNORECASE).strip()
    return _strip_wrapping_quotes(cleaned)


def _strip_wrapping_quotes(text: str) -> str:
    value = str(text or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _context_source(context: dict[str, Any]) -> dict[str, Any]:
    record = context.get("source_record") if isinstance(context.get("source_record"), dict) else {}
    source = record.get("source") if isinstance(record.get("source"), dict) else record
    return source if isinstance(source, dict) else {}


def _get_conversation(conversation_id: str) -> dict[str, Any] | None:
    try:
        from domain.chat.store import ChatStore

        return ChatStore().get_conversation(str(conversation_id or "").strip())
    except Exception:
        return None


def _short_id(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 12:
        return text or "unknown"
    return text[:6] + "..." + text[-4:]
