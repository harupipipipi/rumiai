"""Core-authority one-shot bridge for high-authority host services."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import threading
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from core_runtime.authority.request_store import AuthorityRequestStore
from core_runtime.paths import USER_DATA_DIR
from core_runtime.runtime_locks import NamedLock
from tobkiri_host.broker import RequestEnvelope
from tobkiri_host.models import OpaqueAuthorityRef, RequestContext
from tobkiri_host.ports import OpaqueInvocationLease

_TTL_SECONDS = 30
_LOCK = threading.RLock()
_RECEIPT_ROOT = Path(USER_DATA_DIR) / "authority" / "effect_receipts"
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


@dataclass(frozen=True)
class HostAuthorityScope:
    """Host-authenticated identity used to bind an authority receipt.

    The effect request remains ordinary Pack data.  Every identity and
    activation binding in this view is extracted from the Host-generated
    envelope/context, never from the request payload.
    """

    envelope: RequestEnvelope
    caller_id: str
    caller_pack_id: str
    caller_function_id: str
    profile_id: str
    profile_revision: str
    activation_id: str
    activation_digest: str
    plan_digest: str
    profile_authority_digest: str
    workspace_id: str
    session_id: str
    security_epoch: int
    fencing_token: int
    request_digest: str
    target_principal_id: str
    target_domain_id: str


def require_authenticated_host_context(value: object) -> HostAuthorityScope:
    """Return an authenticated Host scope or fail closed.

    ``RequestEnvelope`` is intentionally the only accepted identity carrier.
    A Pack payload, a default profile, and a client-supplied object that merely
    resembles an envelope cannot satisfy this check.
    """

    envelope = value if isinstance(value, RequestEnvelope) else getattr(value, "envelope", None)
    if not isinstance(envelope, RequestEnvelope):
        raise PermissionError("Host-authenticated request envelope is required")
    context = envelope.context
    if not isinstance(context, RequestContext):
        raise PermissionError("Host-authenticated request context is invalid")
    if not isinstance(context.caller_principal, OpaqueAuthorityRef):
        raise PermissionError("Host caller principal is invalid")
    if not isinstance(envelope.target_principal, OpaqueAuthorityRef):
        raise PermissionError("Host target principal is invalid")
    if not isinstance(envelope.target_domain, OpaqueAuthorityRef):
        raise PermissionError("Host target domain is invalid")
    if not isinstance(envelope.lease, OpaqueInvocationLease):
        raise PermissionError("Host invocation lease is invalid")
    if not isinstance(envelope.payload, Mapping):
        raise PermissionError("Host envelope payload is invalid")
    if not _DIGEST.fullmatch(str(envelope.request_digest or "")):
        raise PermissionError("Host request digest is invalid")
    for field_name in (
        "activation_digest",
        "plan_digest",
        "profile_authority_digest",
        "target_backend_digest",
    ):
        if not _DIGEST.fullmatch(str(getattr(context, field_name) or "")):
            raise PermissionError(f"Host {field_name} is invalid")
    if (
        not context.request_id
        or not context.trace_id
        or not context.profile_id
        or not context.activation_id
        or not context.caller_session_id
        or not context.caller_domain_id
        or not context.handle_namespace
        or not envelope.contract_id
        or not envelope.contract_version
        or not envelope.operation_id
        or not isinstance(envelope.deadline_monotonic, (int, float))
        or isinstance(envelope.deadline_monotonic, bool)
        or not math.isfinite(envelope.deadline_monotonic)
        or envelope.deadline_monotonic <= time.monotonic()
    ):
        raise PermissionError("Host request context is incomplete or expired")

    profile_revision = _host_string(
        value,
        context,
        "profile_revision",
        context.profile_authority_digest,
    )
    if not profile_revision:
        raise PermissionError("Host profile revision is unavailable")
    caller_id = context.caller_principal.value
    caller_pack_id = _host_string(value, context, "caller_pack_id", caller_id)
    caller_function_id = _host_string(value, context, "caller_function_id", caller_id)
    if not caller_pack_id or not caller_function_id:
        raise PermissionError("Host caller binding is unavailable")
    return HostAuthorityScope(
        envelope=envelope,
        caller_id=caller_id,
        caller_pack_id=caller_pack_id,
        caller_function_id=caller_function_id,
        profile_id=context.profile_id,
        profile_revision=profile_revision,
        activation_id=context.activation_id,
        activation_digest=context.activation_digest,
        plan_digest=context.plan_digest,
        profile_authority_digest=context.profile_authority_digest,
        workspace_id=_host_string(value, context, "workspace_id"),
        session_id=context.caller_session_id,
        security_epoch=context.security_epoch,
        fencing_token=context.fencing_token,
        request_digest=envelope.request_digest,
        target_principal_id=envelope.target_principal.value,
        target_domain_id=envelope.target_domain.value,
    )


def _host_string(
    host_context: object,
    context: RequestContext,
    name: str,
    fallback: str = "",
) -> str:
    """Read optional binding metadata from the Host context only."""

    for source in (host_context, context):
        candidate = getattr(source, name, None)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return str(fallback or "").strip()


def create_authority_operation(
    host_context: Any,
) -> Callable[[str, Mapping[str, Any]], dict[str, Any]]:
    """Create authorize/redeem operations bound to one Host context."""

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name == "authorize":
            return _authorize(payload, host_context=host_context)
        if name == "redeem":
            return _redeem(payload, host_context=host_context)
        raise ValueError(f"unknown host authority operation: {name}")

    return operation


def _authorize(
    payload: Mapping[str, Any],
    host_context: object | None = None,
) -> dict[str, Any]:
    scope = _scope(payload, host_context)
    receipt = secrets.token_urlsafe(32)
    receipt_hash = _receipt_hash(receipt)
    now = time.time()
    record = {
        "scope": scope,
        "service_pack_id": str(payload.get("service_pack_id") or "").strip(),
        "issued_at": now,
        "expires_at": now + _TTL_SECONDS,
        "status": "pending_approval",
    }
    if not record["service_pack_id"]:
        raise ValueError("host authority service pack is required")
    with _LOCK, NamedLock(_RECEIPT_ROOT, "authority-receipts"):
        _write_receipt(receipt_hash, record)
    if bool(payload.get("approval_required", False)):
        token = str(payload.get("approval_token") or "")
        request_id = str(payload.get("approval_request_id") or "").strip()
        if not token or not request_id:
            _delete_receipt(receipt_hash)
            return {
                **_denied(scope, "approval_required"),
                "request": {
                    "principal_id": scope["caller_id"],
                    "permission_id": scope["authority"],
                    "profile_id": scope["profile_id"],
                    "resource": scope,
                    "risk_level": str(payload.get("risk") or "high"),
                },
            }
        consumed = AuthorityRequestStore().consume_one_shot(
            request_id=request_id,
            principal_id=scope["caller_id"],
            permission_id=scope["authority"],
            resource=scope,
            token=token,
        )
        if not consumed:
            _delete_receipt(receipt_hash)
            return _denied(scope, "approval_invalid_expired_or_used")
    with _LOCK, NamedLock(_RECEIPT_ROOT, "authority-receipts"):
        record["status"] = "issued"
        _write_receipt(receipt_hash, record)
    return {
        "authorized": True,
        "receipt": receipt,
        "receipt_hash": receipt_hash,
        "scope": scope,
        "service_pack_id": record["service_pack_id"],
        "expires_in_seconds": _TTL_SECONDS,
        "replay_policy": "redeem_once",
    }


def _redeem(
    payload: Mapping[str, Any],
    host_context: object | None = None,
) -> dict[str, Any]:
    receipt = str(payload.get("receipt") or "")
    if not receipt:
        raise ValueError("host authority receipt is required")
    receipt_hash = _receipt_hash(receipt)
    expected_scope = _scope(payload, host_context)
    service_pack_id = str(payload.get("service_pack_id") or "").strip()
    if not service_pack_id:
        raise ValueError("host authority service pack is required")
    now = time.time()
    with _LOCK, NamedLock(_RECEIPT_ROOT, "authority-receipts"):
        _prune(now)
        record = _read_receipt(receipt_hash)
        if record is None:
            return _denied(expected_scope, "receipt_missing_or_expired")
        if record.get("status") != "issued":
            return _denied(expected_scope, "receipt_already_redeemed")
        if record["service_pack_id"] != service_pack_id:
            return _denied(expected_scope, "receipt_service_mismatch")
        if record["scope"] != expected_scope:
            return _denied(expected_scope, "receipt_scope_mismatch")
        record["status"] = "effect_committing"
        record["redeemed_at"] = now
        _write_receipt(receipt_hash, record)
    return {
        "authorized": True,
        "redeemed": True,
        "receipt_hash": receipt_hash,
        "scope": expected_scope,
        "service_pack_id": service_pack_id,
    }


def _scope(
    payload: Mapping[str, Any],
    host_context: object | None = None,
) -> dict[str, Any]:
    host_scope = require_authenticated_host_context(host_context)
    operation = str(payload.get("operation") or "").strip()
    authority = str(payload.get("authority") or "").strip()
    arguments = payload.get("arguments")
    if not isinstance(arguments, Mapping):
        raise ValueError("host authority arguments must be an object")
    if not all((operation, authority)):
        raise ValueError("host authority scope is incomplete")
    return {
        "operation": operation,
        "authority": authority,
        "args_hash": hashlib.sha256(
            json.dumps(
                dict(arguments),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest(),
        "caller_id": host_scope.caller_id,
        "caller_pack_id": host_scope.caller_pack_id,
        "caller_function_id": host_scope.caller_function_id,
        "profile_id": host_scope.profile_id,
        "profile_revision": host_scope.profile_revision,
        "activation_id": host_scope.activation_id,
        "activation_digest": host_scope.activation_digest,
        "plan_digest": host_scope.plan_digest,
        "profile_authority_digest": host_scope.profile_authority_digest,
        "workspace_id": host_scope.workspace_id,
        "session_id": host_scope.session_id,
        "security_epoch": host_scope.security_epoch,
        "fencing_token": host_scope.fencing_token,
        "request_digest": host_scope.request_digest,
        "target_principal_id": host_scope.target_principal_id,
        "target_domain_id": host_scope.target_domain_id,
        "replay_policy": "one_shot",
    }


def _denied(scope: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {"authorized": False, "reason": reason, "scope": dict(scope)}


def _receipt_hash(receipt: str) -> str:
    return hashlib.sha256(receipt.encode("utf-8")).hexdigest()


def _prune(now: float) -> None:
    if not _RECEIPT_ROOT.exists():
        return
    for path in _RECEIPT_ROOT.glob("*.json"):
        value = _read_json(path)
        if float((value or {}).get("expires_at") or 0) <= now:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _receipt_path(receipt_hash: str) -> Path:
    return _RECEIPT_ROOT / f"{receipt_hash}.json"


def _read_receipt(receipt_hash: str) -> dict[str, Any] | None:
    return _read_json(_receipt_path(receipt_hash))


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _write_receipt(receipt_hash: str, value: Mapping[str, Any]) -> None:
    _RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    os.chmod(_RECEIPT_ROOT, 0o700)
    descriptor, temporary = tempfile.mkstemp(
        dir=_RECEIPT_ROOT,
        prefix=".receipt-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(value), handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, _receipt_path(receipt_hash))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _delete_receipt(receipt_hash: str) -> None:
    try:
        _receipt_path(receipt_hash).unlink()
    except FileNotFoundError:
        pass
