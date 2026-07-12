from __future__ import annotations

from typing import Any

from .event import ExternalEvent
from .principal import ExternalPrincipal


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _conversation_id(provider: str, scope_type: str, scope_id: str) -> str:
    return ":".join([_clean(provider, "unknown"), _clean(scope_type, "unknown"), _clean(scope_id, "unknown")])


def normalize_line_event(event: dict[str, Any], *, verified: bool, destination: str = "") -> ExternalEvent:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    source_type = _clean(source.get("type"), "unknown")
    scope_type = source_type if source_type in {"group", "room", "user"} else "unknown"
    if scope_type == "group":
        scope_id = _clean(source.get("groupId"), "unknown")
    elif scope_type == "room":
        scope_id = _clean(source.get("roomId"), "unknown")
    elif scope_type == "user":
        scope_id = _clean(source.get("userId"), "unknown")
    else:
        scope_id = "unknown"
    actor_id = _clean(source.get("userId"), scope_id if scope_type == "user" else "unknown")
    conversation_id = _conversation_id("line", scope_type, scope_id)
    event_id = _clean(event.get("webhookEventId") or message.get("id"))
    message_id = _clean(message.get("id"))
    message_type = _clean(message.get("type"), "unknown")
    attachments = []
    if message_type not in {"", "unknown", "text"} and message_id:
        attachments.append(
            {
                "provider": "line",
                "message_id": message_id,
                "message_type": message_type,
                "content_api": f"https://api-data.line.me/v2/bot/message/{message_id}/content",
                "retrieval": "line_content_api",
                "status": "unsupported_inline",
            }
        )
    return ExternalEvent(
        provider="line",
        workspace=ExternalPrincipal("line_destination", _clean(destination or event.get("destination"), "unknown")),
        scope=ExternalPrincipal(scope_type, scope_id),
        actor=ExternalPrincipal("user", actor_id),
        conversation=ExternalPrincipal("external", conversation_id),
        event={
            "id": event_id,
            "message_id": message_id,
            "type": _clean(event.get("type"), "unknown"),
            "message_type": message_type,
        },
        payload=event,
        verified=verified,
        metadata={
            "reply_token": event.get("replyToken"),
            "mode": _clean(event.get("mode"), "active"),
            "source": source,
            "message": message,
            "attachments": attachments,
        },
    )


def normalize_discord_interaction(payload: dict[str, Any], *, verified: bool) -> ExternalEvent:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    member = payload.get("member") if isinstance(payload.get("member"), dict) else {}
    user = member.get("user") if isinstance(member.get("user"), dict) else payload.get("user")
    user = user if isinstance(user, dict) else {}
    guild_id = _clean(payload.get("guild_id"), "dm")
    channel_id = _clean(payload.get("channel_id") or user.get("id"), "interaction")
    actor_id = _clean(user.get("id"), "unknown")
    conversation_id = _conversation_id("discord", "channel", channel_id)
    return ExternalEvent(
        provider="discord",
        workspace=ExternalPrincipal("guild", guild_id),
        scope=ExternalPrincipal("channel", channel_id),
        actor=ExternalPrincipal("user", actor_id),
        conversation=ExternalPrincipal("external", conversation_id),
        event={
            "id": _clean(payload.get("id")),
            "message_id": _clean(payload.get("id")),
            "type": "message",
            "name": _clean(data.get("name")),
        },
        payload=payload,
        verified=verified,
        metadata={"interaction": data, "application_id": payload.get("application_id")},
    )


def normalize_discord_message(payload: dict[str, Any], *, verified: bool) -> ExternalEvent:
    data = payload.get("d") if isinstance(payload.get("d"), dict) else payload
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    guild_id = _clean(data.get("guild_id") or payload.get("guild_id"), "dm")
    channel_id = _clean(data.get("channel_id") or payload.get("channel_id"), "message")
    actor_type = "bot" if author.get("bot") else "user"
    actor_id = _clean(author.get("id") or data.get("user_id"), "unknown")
    conversation_id = _conversation_id("discord", "channel", channel_id)
    return ExternalEvent(
        provider="discord",
        workspace=ExternalPrincipal("guild", guild_id),
        scope=ExternalPrincipal("channel", channel_id),
        actor=ExternalPrincipal(actor_type, actor_id),
        conversation=ExternalPrincipal("external", conversation_id),
        event={
            "id": _clean(data.get("id") or payload.get("id")),
            "message_id": _clean(data.get("id") or payload.get("id")),
            "type": "message",
            "message_type": "text",
        },
        payload=data,
        verified=verified,
        metadata={"author": author, "raw_gateway_payload": payload if payload is not data else None},
    )


def normalize_slack_event(payload: dict[str, Any], *, verified: bool) -> ExternalEvent:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    team_id = _clean(payload.get("team_id") or event.get("team"), "unknown-team")
    channel_id = _clean(event.get("channel") or payload.get("channel"), "unknown-channel")
    thread_ts = _clean(event.get("thread_ts") or event.get("ts"), "")
    actor_id = _clean(event.get("user") or event.get("bot_id"), "unknown")
    event_id = _clean(payload.get("event_id") or event.get("client_msg_id") or event.get("event_ts") or event.get("ts"))
    scope_id = channel_id
    conversation_suffix = thread_ts or actor_id or channel_id
    return ExternalEvent(
        provider="slack",
        workspace=ExternalPrincipal("team", team_id),
        scope=ExternalPrincipal("channel", scope_id),
        actor=ExternalPrincipal("bot" if event.get("bot_id") else "user", actor_id),
        conversation=ExternalPrincipal("external", _conversation_id("slack", "channel", conversation_suffix)),
        event={
            "id": event_id,
            "message_id": _clean(event.get("client_msg_id") or event.get("ts") or event_id),
            "type": "message",
            "message_type": _clean(event.get("type"), "message"),
        },
        payload=payload,
        verified=verified,
        metadata={
            "team_id": team_id,
            "channel": channel_id,
            "user": actor_id,
            "thread_ts": thread_ts,
            "event_ts": event.get("event_ts") or event.get("ts"),
        },
    )


def normalize_generic_webhook(payload: dict[str, Any], *, webhook_id: str, verified: bool) -> ExternalEvent:
    scope_id = _clean(payload.get("scope_id") or payload.get("channel_id") or webhook_id, webhook_id)
    actor_id = _clean(payload.get("actor_id") or payload.get("user_id"), "unknown")
    event_id = _clean(payload.get("event_id") or payload.get("id"))
    return ExternalEvent(
        provider="generic",
        workspace=ExternalPrincipal("webhook", webhook_id),
        scope=ExternalPrincipal(_clean(payload.get("scope_type"), "webhook"), scope_id),
        actor=ExternalPrincipal(_clean(payload.get("actor_type"), "unknown"), actor_id),
        conversation=ExternalPrincipal("external", _conversation_id("webhook", "endpoint", webhook_id)),
        event={
            "id": event_id,
            "message_id": _clean(payload.get("message_id") or event_id),
            "type": _clean(payload.get("type"), "message"),
            "message_type": _clean(payload.get("message_type"), "text"),
        },
        payload=payload,
        verified=verified,
        metadata={"webhook_id": webhook_id, "declared_provider": payload.get("provider")},
    )
