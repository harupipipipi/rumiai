from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any


_TOKEN_VERSION = "v1"
_DEFAULT_EXPIRES_IN_SECONDS = 300
_RUNTIME_SECRET = os.environ.get("RUMI_DEFAULTSPACK_APPROVAL_SECRET") or secrets.token_urlsafe(32)
_LOCK = threading.RLock()
_REQUESTS: dict[str, "ApprovalRequest"] = {}
_USED_TOKEN_IDS: set[str] = set()

_ARG_HASH_IGNORE_KEYS = {
    "approval_token",
    "approved",
    "_headers",
    "_method",
    "_raw_body",
    "_raw_body_base64",
}


@dataclass
class ApprovalRequest:
    request_id: str
    operation: str
    risk_level: str
    args_hash: str
    details: dict[str, Any]
    created_at: int
    expires_at: int
    status: str = "pending"
    decision_at: int | None = None


@dataclass
class ApprovalDecision:
    request_id: str
    status: str
    approved: bool
    token: str = ""
    expires_at: int | None = None
    reason: str = ""


@dataclass
class TokenVerification:
    valid: bool
    code: str = ""
    message: str = ""
    request_id: str = ""


def _now() -> int:
    return int(time.time())


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _ARG_HASH_IGNORE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def hash_arguments(args: dict[str, Any] | None) -> str:
    canonical = json.dumps(
        _canonicalize(args or {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def display_summary(operation: str, args: dict[str, Any] | None) -> str:
    args = args or {}
    if operation.startswith("file."):
        return f"{operation}: {args.get('path') or args.get('snapshot_id') or '<workspace>'}"
    if operation.startswith("terminal."):
        return f"{operation}: {args.get('command') or '<command>'}"
    if operation.startswith("git."):
        target = args.get("branch") or args.get("remote") or args.get("message") or "<repository>"
        return f"{operation}: {target}"
    return operation


def create_approval_request(
    operation: str,
    risk_level: str,
    args: dict[str, Any] | None = None,
    *,
    expires_in: int = _DEFAULT_EXPIRES_IN_SECONDS,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    request = ApprovalRequest(
        request_id="apr_" + uuid.uuid4().hex,
        operation=str(operation),
        risk_level=str(risk_level or "high"),
        args_hash=hash_arguments(args or details or {}),
        details=dict(details or {}),
        created_at=now,
        expires_at=now + max(1, int(expires_in or _DEFAULT_EXPIRES_IN_SECONDS)),
    )
    with _LOCK:
        _REQUESTS[request.request_id] = request
    payload = asdict(request)
    payload["display_summary"] = display_summary(operation, args or details or {})
    return payload


def deny(request_id: str, reason: str = "") -> dict[str, Any]:
    with _LOCK:
        request = _REQUESTS.get(str(request_id))
        if request is None:
            return asdict(
                ApprovalDecision(str(request_id), "missing", False, reason="approval request not found")
            )
        request.status = "denied"
        request.decision_at = _now()
        return asdict(ApprovalDecision(request.request_id, request.status, False, reason=reason))


def approve(request_id: str) -> dict[str, Any]:
    with _LOCK:
        request = _REQUESTS.get(str(request_id))
        now = _now()
        if request is None:
            return asdict(
                ApprovalDecision(str(request_id), "missing", False, reason="approval request not found")
            )
        if request.expires_at < now:
            request.status = "expired"
            request.decision_at = now
            return asdict(
                ApprovalDecision(request.request_id, request.status, False, reason="approval request expired")
            )
        request.status = "approved"
        request.decision_at = now
        token = issue_execution_token(request.request_id, request.args_hash, expires_at=request.expires_at)
        return asdict(
            ApprovalDecision(
                request.request_id,
                request.status,
                True,
                token=token,
                expires_at=request.expires_at,
            )
        )


def issue_execution_token(request_id: str, args_hash: str, *, expires_at: int | None = None) -> str:
    payload = {
        "version": _TOKEN_VERSION,
        "jti": "tok_" + uuid.uuid4().hex,
        "request_id": str(request_id),
        "args_hash": str(args_hash),
        "expires_at": int(expires_at or (_now() + _DEFAULT_EXPIRES_IN_SECONDS)),
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded = _b64url_encode(body)
    signature = hmac.new(
        _RUNTIME_SECRET.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return encoded + "." + _b64url_encode(signature)


def verify_execution_token(
    token: str,
    operation: str,
    args_hash: str,
    *,
    consume: bool = True,
) -> TokenVerification:
    token = str(token or "")
    if "." not in token:
        return TokenVerification(False, "APPROVAL_TOKEN_MISSING", "approval token is required")
    encoded, supplied_signature = token.rsplit(".", 1)
    expected_signature = _b64url_encode(
        hmac.new(_RUNTIME_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return TokenVerification(False, "APPROVAL_SIGNATURE_INVALID", "approval token signature is invalid")
    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
    except Exception:
        return TokenVerification(False, "APPROVAL_TOKEN_INVALID", "approval token payload is invalid")
    if payload.get("version") != _TOKEN_VERSION:
        return TokenVerification(False, "APPROVAL_TOKEN_INVALID", "approval token version is invalid")
    if int(payload.get("expires_at") or 0) < _now():
        return TokenVerification(False, "APPROVAL_EXPIRED", "approval token expired")
    if str(payload.get("args_hash") or "") != str(args_hash):
        return TokenVerification(
            False,
            "APPROVAL_ARGUMENTS_CHANGED",
            "approval token does not match request arguments",
        )
    request_id = str(payload.get("request_id") or "")
    jti = str(payload.get("jti") or "")
    with _LOCK:
        request = _REQUESTS.get(request_id)
        if request is None:
            return TokenVerification(False, "APPROVAL_REQUEST_MISSING", "approval request is missing")
        if request.operation != operation:
            return TokenVerification(
                False,
                "APPROVAL_OPERATION_MISMATCH",
                "approval token operation mismatch",
                request_id,
            )
        if request.status != "approved":
            return TokenVerification(
                False,
                "APPROVAL_NOT_APPROVED",
                "approval request is not approved",
                request_id,
            )
        if jti in _USED_TOKEN_IDS:
            return TokenVerification(
                False,
                "APPROVAL_TOKEN_USED",
                "approval token has already been used",
                request_id,
            )
        if consume:
            _USED_TOKEN_IDS.add(jti)
    return TokenVerification(True, request_id=request_id)


def reset_approval_state_for_tests() -> None:
    with _LOCK:
        _REQUESTS.clear()
        _USED_TOKEN_IDS.clear()
