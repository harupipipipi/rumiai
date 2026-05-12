from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .event import ExternalEvent


@dataclass
class ExternalOrigin:
    provider: str
    workspace_id: str
    source_type: str
    source_id: str
    actor_id: str
    conversation_id: str
    reply_token: str = ""
    reply_expires_at_ms: int | None = None
    mode: str = "active"
    can_reply: bool = False
    can_push: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def line_source_target(source: dict[str, Any]) -> tuple[str, str]:
    source_type = str(source.get("type") or "").strip()
    if source_type == "user":
        return "user", str(source.get("userId") or "").strip()
    if source_type == "group":
        return "group", str(source.get("groupId") or "").strip()
    if source_type == "room":
        return "room", str(source.get("roomId") or "").strip()
    return "unknown", ""


def origin_from_external_event(event: ExternalEvent | dict[str, Any]) -> ExternalOrigin:
    if isinstance(event, ExternalEvent):
        provider = event.provider
        workspace_id = event.workspace.id
        scope_type = event.scope.type
        scope_id = event.scope.id
        actor_id = event.actor.id
        conversation_id = event.conversation.id
        payload = event.payload
        metadata = event.metadata
        received_at = event.received_at
    else:
        provider = str(event.get("provider") or "")
        workspace = event.get("workspace") if isinstance(event.get("workspace"), dict) else {}
        scope = event.get("scope") if isinstance(event.get("scope"), dict) else {}
        actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
        conversation = event.get("conversation") if isinstance(event.get("conversation"), dict) else {}
        workspace_id = str(workspace.get("id") or "")
        scope_type = str(scope.get("type") or "")
        scope_id = str(scope.get("id") or "")
        actor_id = str(actor.get("id") or "")
        conversation_id = str(conversation.get("id") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        received_at = int(event.get("received_at") or 0)

    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    if provider == "line":
        source_type, source_id = line_source_target(source)
        mode = str(payload.get("mode") or metadata.get("mode") or "active").strip() or "active"
    else:
        source_type = scope_type or "unknown"
        source_id = scope_id or ""
        mode = str(metadata.get("mode") or "active").strip() or "active"

    reply_token = str(metadata.get("reply_token") or payload.get("replyToken") or "").strip()
    reply_expires_at_ms = received_at + 60_000 if reply_token and received_at else None
    return ExternalOrigin(
        provider=provider or "unknown",
        workspace_id=workspace_id or "unknown",
        source_type=source_type or "unknown",
        source_id=source_id,
        actor_id=actor_id or "unknown",
        conversation_id=conversation_id or "",
        reply_token=reply_token,
        reply_expires_at_ms=reply_expires_at_ms,
        mode=mode,
        can_reply=bool(reply_token) and mode != "standby",
        can_push=bool(source_id) and mode != "standby",
    )
