from __future__ import annotations

from typing import Any

from domain.external.event import ExternalEvent
from domain.external.principal import ExternalPrincipal

from .peer_store import PeerRecord, PeerStore
from .policy import P2PPolicy
from .protocol import P2PProtocolError, verify_envelope
from .replay_guard import ReplayGuard
from .settings import P2PSettings


def handle_inbound_envelope(
    input_data: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    settings: P2PSettings | None = None,
    peer_store: PeerStore | None = None,
    replay_guard: ReplayGuard | None = None,
    current_time_ms: int | None = None,
) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    settings = settings or P2PSettings.from_env(context.get("p2p") if isinstance(context.get("p2p"), dict) else None)
    if not settings.enabled:
        return {"status": "error", "code": "P2P_DISABLED", "error": "P2P is disabled"}

    envelope = input_data.get("envelope") if isinstance(input_data.get("envelope"), dict) else input_data
    if not isinstance(envelope, dict):
        return {"status": "error", "code": "ENVELOPE_INVALID", "error": "envelope must be a dict"}

    store = peer_store or PeerStore(settings.store_path)
    sender_id = str(envelope.get("sender_id") or "").strip()
    peer = store.get_peer(sender_id)
    if peer is None:
        return {"status": "denied", "code": "PEER_UNKNOWN", "error": "unknown peer"}
    if not peer.hmac_secret:
        return {"status": "denied", "code": "SHARED_SECRET_MISSING", "error": "peer shared secret missing"}

    try:
        verified_envelope = verify_envelope(
            envelope,
            peer.hmac_secret,
            current_time_ms=current_time_ms,
            max_clock_skew_seconds=settings.envelope_ttl_seconds,
        )
    except P2PProtocolError as exc:
        return {"status": "error", "code": exc.code, "error": str(exc)}

    decision = P2PPolicy(store).evaluate(verified_envelope, peer=peer)
    if not decision.allowed:
        return {"status": "denied", "code": decision.code, "error": decision.reason, "policy": decision.as_dict()}

    guard = replay_guard or ReplayGuard(settings.store_path, ttl_seconds=settings.replay_ttl_seconds)
    replay = guard.check_and_record(
        sender_id=sender_id,
        message_id=str(verified_envelope.get("message_id") or ""),
        nonce=str(verified_envelope.get("nonce") or ""),
        current_time_ms=current_time_ms,
        ttl_seconds=settings.replay_ttl_seconds,
    )
    if not replay.get("ok"):
        return {"status": "denied", "code": replay.get("code") or "REPLAY_DETECTED", "error": replay.get("reason"), "replay": replay}

    event = normalize_p2p_envelope(verified_envelope, peer=peer, verified=True)
    company_append = append_company_message_if_available(event, context=context)
    return {
        "status": "ok",
        "event": event.as_dict(),
        "peer": peer.as_dict(),
        "policy": decision.as_dict(),
        "replay": replay,
        "company_append": company_append,
    }


def normalize_p2p_envelope(envelope: dict[str, Any], *, peer: PeerRecord, verified: bool = True) -> ExternalEvent:
    body = envelope.get("body") if isinstance(envelope.get("body"), dict) else {}
    metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
    company_id = str(body.get("company_id") or metadata.get("company_id") or "").strip()
    channel_id = str(body.get("channel_id") or body.get("company_channel_id") or metadata.get("channel_id") or "").strip()
    scope_type = "company" if company_id else ("channel" if channel_id else "peer")
    scope_id = company_id or channel_id or peer.peer_id
    message_id = str(envelope.get("message_id") or "")
    payload = dict(envelope)
    text = _message_text(body)
    if text and "text" not in payload:
        payload["text"] = text
    return ExternalEvent(
        provider="p2p",
        workspace=ExternalPrincipal("p2p_node", str(envelope.get("recipient_id") or "local")),
        scope=ExternalPrincipal(scope_type, scope_id),
        actor=ExternalPrincipal("peer", peer.peer_id),
        conversation=ExternalPrincipal("external", _conversation_id(peer.peer_id, scope_type, scope_id)),
        event={
            "id": message_id,
            "message_id": message_id,
            "type": "message" if str(envelope.get("type") or "") in {"", "message", "p2p.message"} else str(envelope.get("type")),
            "message_type": "text" if text else "event",
        },
        payload=payload,
        verified=verified,
        metadata={
            "p2p": {
                "peer_id": peer.peer_id,
                "fingerprint": peer.fingerprint,
                "capabilities": list(peer.capabilities),
                "allowed_company_ids": list(peer.allowed_company_ids),
                "message_id": message_id,
                "nonce": str(envelope.get("nonce") or ""),
                "signature_verified": bool(verified),
            },
            "company_id": company_id,
            "channel_id": channel_id,
            "received_from_peer": peer.peer_id,
        },
    )


def append_company_message_if_available(event: ExternalEvent, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    body = event.payload.get("body") if isinstance(event.payload.get("body"), dict) else {}
    metadata = event.payload.get("metadata") if isinstance(event.payload.get("metadata"), dict) else {}
    company_id = str(body.get("company_id") or metadata.get("company_id") or event.metadata.get("company_id") or "").strip()
    channel_id = str(body.get("company_channel_id") or body.get("channel_id") or metadata.get("channel_id") or event.metadata.get("channel_id") or "").strip()
    if not company_id and not channel_id:
        return {"attempted": False, "reason": "no company/channel metadata"}

    content = _message_text(body)
    payload = {
        "company_id": company_id,
        "channel_id": channel_id,
        "sender_id": event.actor.id,
        "sender_name": str(body.get("sender_name") or metadata.get("sender_name") or event.actor.id),
        "content": content,
        "metadata": {"external_event": event.as_dict(), "source": "p2p"},
    }
    append_fn = context.get("company_append_message")
    if callable(append_fn):
        try:
            return {"attempted": True, "ok": True, "result": append_fn(payload)}
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}

    service = context.get("company_service") or context.get("company")
    if service is None:
        return {"attempted": False, "reason": "company service not available"}
    for method_name in ("append_channel_message", "send_channel_message", "add_channel_message", "send_message"):
        method = getattr(service, method_name, None)
        if not callable(method):
            continue
        try:
            return {"attempted": True, "ok": True, "method": method_name, "result": method(**payload)}
        except TypeError:
            try:
                return {"attempted": True, "ok": True, "method": method_name, "result": method(payload)}
            except Exception as exc:
                return {"attempted": True, "ok": False, "method": method_name, "error": str(exc)}
        except Exception as exc:
            return {"attempted": True, "ok": False, "method": method_name, "error": str(exc)}
    return {"attempted": False, "reason": "company service has no supported append method"}


def _message_text(body: dict[str, Any]) -> str:
    for key in ("text", "message", "content"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _conversation_id(peer_id: str, scope_type: str, scope_id: str) -> str:
    return ":".join(["p2p", str(peer_id or "unknown"), str(scope_type or "peer"), str(scope_id or "unknown")])
