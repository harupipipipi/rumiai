from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any


PROTOCOL_VERSION = "rumi-p2p-envelope-v1"
SIGNATURE_PREFIX = "hmac-sha256="


class P2PProtocolError(ValueError):
    def __init__(self, message: str, code: str = "P2P_PROTOCOL_ERROR") -> None:
        super().__init__(message)
        self.code = code


def now_ms() -> int:
    return int(time.time() * 1000)


def canonical_envelope_bytes(envelope: dict[str, Any]) -> bytes:
    unsigned = _without_signature(envelope)
    return json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def make_envelope(
    *,
    sender_id: str,
    recipient_id: str = "",
    message_type: str = "message",
    body: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    ttl_seconds: int = 300,
    timestamp_ms: int | None = None,
    message_id: str = "",
    nonce: str = "",
) -> dict[str, Any]:
    created_at = int(timestamp_ms if timestamp_ms is not None else now_ms())
    ttl_ms = max(1, int(ttl_seconds or 300)) * 1000
    return {
        "version": PROTOCOL_VERSION,
        "message_id": str(message_id or "msg-" + uuid.uuid4().hex),
        "nonce": str(nonce or secrets.token_urlsafe(18)),
        "sender_id": str(sender_id or ""),
        "recipient_id": str(recipient_id or ""),
        "timestamp_ms": created_at,
        "expires_at_ms": created_at + ttl_ms,
        "type": str(message_type or "message"),
        "body": dict(body if isinstance(body, dict) else {}),
        "metadata": dict(metadata if isinstance(metadata, dict) else {}),
    }


def sign_envelope(envelope: dict[str, Any], shared_secret: str) -> dict[str, Any]:
    _require_secret(shared_secret)
    signed = copy.deepcopy(envelope)
    digest = hmac.new(str(shared_secret).encode("utf-8"), canonical_envelope_bytes(signed), hashlib.sha256).hexdigest()
    signed["signature"] = SIGNATURE_PREFIX + digest
    return signed


def verify_envelope(
    envelope: dict[str, Any],
    shared_secret: str,
    *,
    current_time_ms: int | None = None,
    max_clock_skew_seconds: int = 300,
) -> dict[str, Any]:
    _require_secret(shared_secret)
    if not isinstance(envelope, dict):
        raise P2PProtocolError("envelope must be a dict", "ENVELOPE_INVALID")
    _validate_required(envelope)
    timestamp_ms = _int_field(envelope, "timestamp_ms")
    expires_at_ms = _int_field(envelope, "expires_at_ms")
    now = int(current_time_ms if current_time_ms is not None else now_ms())
    if expires_at_ms <= timestamp_ms:
        raise P2PProtocolError("envelope expiry must be after timestamp", "ENVELOPE_EXPIRES_INVALID")
    max_window_ms = max(1, int(max_clock_skew_seconds)) * 1000
    if expires_at_ms - timestamp_ms > max_window_ms:
        raise P2PProtocolError("envelope validity window is too long", "ENVELOPE_EXPIRES_INVALID")
    if expires_at_ms < now:
        raise P2PProtocolError("envelope expired", "ENVELOPE_EXPIRED")
    if timestamp_ms > now + max_window_ms:
        raise P2PProtocolError("envelope timestamp is too far in the future", "ENVELOPE_TIMESTAMP_INVALID")
    if timestamp_ms < now - max_window_ms:
        raise P2PProtocolError("envelope timestamp is too old", "ENVELOPE_TIMESTAMP_INVALID")

    provided = str(envelope.get("signature") or "")
    if not provided:
        raise P2PProtocolError("missing envelope signature", "SIGNATURE_MISSING")
    expected = sign_envelope(envelope, shared_secret)["signature"]
    raw_expected = expected.removeprefix(SIGNATURE_PREFIX)
    if not (hmac.compare_digest(provided, expected) or hmac.compare_digest(provided, raw_expected)):
        raise P2PProtocolError("envelope signature mismatch", "SIGNATURE_INVALID")
    return copy.deepcopy(envelope)


def _without_signature(envelope: dict[str, Any]) -> dict[str, Any]:
    unsigned = copy.deepcopy(envelope)
    unsigned.pop("signature", None)
    return unsigned


def _validate_required(envelope: dict[str, Any]) -> None:
    if str(envelope.get("version") or "") != PROTOCOL_VERSION:
        raise P2PProtocolError("unsupported envelope version", "ENVELOPE_VERSION_UNSUPPORTED")
    for key in ("message_id", "nonce", "sender_id", "timestamp_ms", "expires_at_ms", "type"):
        if envelope.get(key) in (None, ""):
            raise P2PProtocolError(f"missing envelope field: {key}", "ENVELOPE_INVALID")
    if not isinstance(envelope.get("body"), dict):
        raise P2PProtocolError("envelope body must be a dict", "ENVELOPE_INVALID")
    if not isinstance(envelope.get("metadata"), dict):
        raise P2PProtocolError("envelope metadata must be a dict", "ENVELOPE_INVALID")


def _int_field(envelope: dict[str, Any], key: str) -> int:
    try:
        return int(envelope.get(key))
    except (TypeError, ValueError):
        raise P2PProtocolError(f"invalid envelope field: {key}", "ENVELOPE_INVALID")


def _require_secret(shared_secret: str) -> None:
    if not str(shared_secret or "").strip():
        raise P2PProtocolError("missing shared secret", "SHARED_SECRET_MISSING")
