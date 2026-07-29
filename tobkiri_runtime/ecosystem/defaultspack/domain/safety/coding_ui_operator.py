"""Verification for native, one-shot Launcher coding approval decisions."""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from typing import Any


class CodingUiOperatorError(ValueError):
    pass


_LOCK = threading.RLock()
_USED_NONCES: set[str] = set()


def _message(payload: dict[str, Any]) -> bytes:
    return "\n".join(
        [
            f"v{int(payload.get('version') or 0)}",
            str(payload.get("origin") or ""),
            str(payload.get("window_label") or ""),
            str(payload.get("request_id") or ""),
            str(payload.get("expected_digest") or ""),
            str(payload.get("decision") or ""),
            str(int(payload.get("issued_at") or 0)),
            str(int(payload.get("expires_at") or 0)),
            str(payload.get("nonce") or ""),
        ]
    ).encode("utf-8")


def verify_coding_ui_operator(
    payload: Any,
    *,
    request_id: str,
    expected_digest: str,
    decision: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CodingUiOperatorError("native ui_operator is required")
    normalized = {
        "version": payload.get("version"),
        "kind": str(payload.get("kind") or ""),
        "origin": str(payload.get("origin") or ""),
        "window_label": str(payload.get("window_label") or ""),
        "request_id": str(payload.get("request_id") or ""),
        "expected_digest": str(payload.get("expected_digest") or ""),
        "decision": str(payload.get("decision") or ""),
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
        "nonce": str(payload.get("nonce") or ""),
    }
    if (
        normalized["version"] != 3
        or normalized["kind"] != "coding_ui_operator"
        or normalized["origin"] != "tauri_webview_window"
        or normalized["window_label"] != "defaultspack-main"
    ):
        raise CodingUiOperatorError("native ui_operator provenance is invalid")
    if normalized["request_id"] != request_id:
        raise CodingUiOperatorError("native ui_operator request mismatch")
    if not hmac.compare_digest(normalized["expected_digest"], expected_digest):
        raise CodingUiOperatorError("native ui_operator digest mismatch")
    if normalized["decision"] != decision:
        raise CodingUiOperatorError("native ui_operator decision mismatch")
    try:
        normalized["issued_at"] = int(normalized["issued_at"] or 0)
        normalized["expires_at"] = int(normalized["expires_at"] or 0)
    except (TypeError, ValueError) as exc:
        raise CodingUiOperatorError("native ui_operator timestamps are invalid") from exc
    now = int(time.time())
    if (
        normalized["issued_at"] > now + 5
        or normalized["expires_at"] <= now
        or normalized["expires_at"] > normalized["issued_at"] + 60
    ):
        raise CodingUiOperatorError("native ui_operator expired")
    secret = os.environ.get("RUMI_PANEL_BOOTSTRAP_SECRET", "").encode("utf-8")
    signature = str(payload.get("signature") or "")
    if not secret or not signature:
        raise CodingUiOperatorError("native ui_operator signing secret is unavailable")
    expected_signature = hmac.new(secret, _message(normalized), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise CodingUiOperatorError("native ui_operator signature is invalid")
    nonce_key = hashlib.sha256(normalized["nonce"].encode("utf-8")).hexdigest()
    with _LOCK:
        if nonce_key in _USED_NONCES:
            raise CodingUiOperatorError("native ui_operator has already been used")
        _USED_NONCES.add(nonce_key)
    return normalized
