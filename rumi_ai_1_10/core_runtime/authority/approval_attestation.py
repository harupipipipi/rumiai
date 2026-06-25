"""Verification for device-signed mobile approval challenges."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from typing import Any

from .approval_challenge_store import ApprovalChallengeStore
from .device_key_registry import DeviceKeyRegistry
from .models import AuthorityRequest
from .request_store import AuthorityRequestStore


@dataclass(frozen=True)
class ApprovalAttestationResult:
    ok: bool
    error: str = ""
    status_code: int = 403
    audit: dict[str, Any] = field(default_factory=dict)


def verify_mobile_approval_attestation(
    *,
    request: AuthorityRequest,
    actor_principal: Any,
    decision: str,
    scope: str,
    attestation: dict[str, Any] | None,
    challenge_store: ApprovalChallengeStore,
    device_key_registry: DeviceKeyRegistry,
    request_store: AuthorityRequestStore,
) -> ApprovalAttestationResult:
    if not isinstance(attestation, dict):
        return ApprovalAttestationResult(False, "Mobile approval attestation is required", 403)

    challenge_id = str(attestation.get("challenge_id") or "").strip()
    payload_hash = str(attestation.get("payload_hash") or "").strip()
    signature = str(attestation.get("signature") or "").strip()
    if not challenge_id or not payload_hash or not signature:
        return ApprovalAttestationResult(False, "Mobile approval attestation is incomplete", 400)

    challenge = challenge_store.get_challenge(challenge_id)
    if challenge is None:
        return ApprovalAttestationResult(False, "Approval challenge was not found", 404)
    if challenge.consumed:
        return ApprovalAttestationResult(False, "Approval challenge was already used", 409)
    if challenge_store.challenge_expired(challenge):
        return ApprovalAttestationResult(False, "Approval challenge expired", 409)
    if not hmac.compare_digest(challenge.payload_hash, payload_hash):
        return ApprovalAttestationResult(False, "Approval challenge payload hash does not match", 403)

    actor_profile_id = _actor_field(actor_principal, "profile_id")
    actor_device_id = _actor_field(actor_principal, "device_id")
    actor_token_id = _actor_field(actor_principal, "token_id")
    request_profile_id = str(request.profile_id or "").strip()
    resource_hash = request_store.resource_hash(request.resource)
    expected = {
        "request_id": request.request_id,
        "profile_id": actor_profile_id,
        "device_id": actor_device_id,
        "token_id": actor_token_id,
        "permission_id": request.permission_id,
        "resource_hash": resource_hash,
        "decision": str(decision or "").strip().lower(),
        "scope": str(scope or "").strip().lower(),
    }
    actual = {
        "request_id": challenge.request_id,
        "profile_id": challenge.profile_id,
        "device_id": challenge.device_id,
        "token_id": challenge.token_id,
        "permission_id": challenge.permission_id,
        "resource_hash": challenge.resource_hash,
        "decision": challenge.decision,
        "scope": challenge.scope,
    }
    for key, expected_value in expected.items():
        if not expected_value or str(actual.get(key) or "") != expected_value:
            return ApprovalAttestationResult(
                False,
                f"Approval challenge {key} does not match",
                403,
                audit={"challenge_id": challenge.challenge_id, "mismatch": key},
            )
    if request_profile_id and request_profile_id != actor_profile_id:
        return ApprovalAttestationResult(False, "Approval request profile does not match token profile", 403)

    if not device_key_registry.verify_signature(
        profile_id=actor_profile_id,
        device_id=actor_device_id,
        payload_hash=payload_hash,
        signature=signature,
    ):
        return ApprovalAttestationResult(False, "Mobile approval signature is invalid", 403)

    if not challenge_store.consume_challenge(challenge_id=challenge_id, payload_hash=payload_hash):
        return ApprovalAttestationResult(False, "Approval challenge could not be consumed", 409)

    return ApprovalAttestationResult(
        True,
        audit={
            "mobile_attestation": True,
            "challenge_id": challenge.challenge_id,
            "token_id": actor_token_id,
            "device_id": actor_device_id,
            "payload_hash": payload_hash,
        },
    )


def _actor_field(actor_principal: Any, key: str) -> str:
    if isinstance(actor_principal, dict):
        return str(actor_principal.get(key) or "").strip()
    return str(getattr(actor_principal, key, "") or "").strip()
