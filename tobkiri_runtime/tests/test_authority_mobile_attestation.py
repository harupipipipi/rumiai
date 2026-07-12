from __future__ import annotations

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _HmacKey:
    def get_active_key(self) -> str:
        return "authority-attestation-test-key-" + ("x" * 32)


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")
    from core_runtime.authority.approval_challenge_store import ApprovalChallengeStore
    from core_runtime.authority.device_key_registry import DeviceKeyRegistry
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.capability_grant_manager import CapabilityGrantManager

    grants = CapabilityGrantManager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="capability-attestation-test-key-" + ("y" * 32),
    )
    store = AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey())
    challenges = ApprovalChallengeStore(tmp_path / "challenges", hmac_key_manager=_HmacKey())
    devices = DeviceKeyRegistry(tmp_path / "devices", secret_key="device-key-test-" + ("z" * 32))
    service = AuthorityService(
        capability_grant_manager=grants,
        request_store=store,
        approval_challenge_store=challenges,
        device_key_registry=devices,
    )
    return service, grants


def _mobile_actor():
    from core_runtime.access_tokens import AuthenticatedPrincipal

    return AuthenticatedPrincipal(
        token_id="tok-mobile-approver",
        profile_id="work",
        surface_id="mobile-approver",
        device_id="phone-1",
        role="mobile_approver",
        audiences=("kernel_api",),
        issued_at="",
        expires_at=None,
    )


def _grant_mobile_approver(grants, permission_id="authority.request.approve"):
    for principal_id in (
        "profile:work",
        "profile:work__surface:mobile-approver",
        "profile:work__surface:mobile-approver__device:phone-1",
    ):
        grants.grant_permission(principal_id, permission_id, {})


def _pending_request(service):
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )
    assert decision.request_id
    return decision.request_id


def _keypair(service):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    service.register_device_key(profile_id="work", device_id="phone-1", public_key=public_key)
    return private_key


def _attestation(private_key, challenge_result):
    payload_hash = challenge_result["payload_hash"]
    signature = private_key.sign(bytes.fromhex(payload_hash))
    return {
        "challenge_id": challenge_result["challenge"]["challenge_id"],
        "payload_hash": payload_hash,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def test_mobile_approver_requires_device_signed_challenge(tmp_path, monkeypatch):
    service, grants = _service(tmp_path, monkeypatch)
    _grant_mobile_approver(grants)
    request_id = _pending_request(service)
    actor = _mobile_actor()

    unsigned = service.approve_request(request_id, scope="once", actor_principal=actor)

    assert unsigned["success"] is False
    assert unsigned["status_code"] == 403
    assert "attestation" in unsigned["error"]


def test_mobile_approver_signed_challenge_issues_one_shot(tmp_path, monkeypatch):
    service, grants = _service(tmp_path, monkeypatch)
    _grant_mobile_approver(grants)
    private_key = _keypair(service)
    request_id = _pending_request(service)
    actor = _mobile_actor()

    challenge = service.create_approval_challenge(
        request_id,
        decision="approve",
        scope="once",
        actor_principal=actor,
    )
    approval = service.approve_request(
        request_id,
        scope="once",
        actor_principal=actor,
        attestation=_attestation(private_key, challenge),
    )

    assert challenge["success"] is True
    assert challenge["challenge"]["device_id"] == "phone-1"
    assert approval["success"] is True
    assert approval["scope"] == "once"
    assert approval["token"]


def test_mobile_signed_challenge_cannot_be_expanded_after_signing(tmp_path, monkeypatch):
    service, grants = _service(tmp_path, monkeypatch)
    _grant_mobile_approver(grants)
    private_key = _keypair(service)
    request_id = _pending_request(service)
    actor = _mobile_actor()

    challenge = service.create_approval_challenge(
        request_id,
        decision="approve",
        scope="once",
        actor_principal=actor,
    )
    assert challenge["success"] is True
    assert challenge["challenge"]["approval_expires_in_seconds"] == 300
    attestation = _attestation(private_key, challenge)

    widened = service.approve_request(
        request_id,
        scope="once",
        actor_principal=actor,
        related_permissions=["api_key.use", "network.egress"],
        attestation=attestation,
    )
    inflated_ttl = service.approve_request(
        request_id,
        scope="once",
        actor_principal=actor,
        expires_in_seconds=315360000,
        attestation=attestation,
    )
    approval = service.approve_request(
        request_id,
        scope="once",
        actor_principal=actor,
        attestation=attestation,
    )

    assert widened["success"] is False
    assert widened["status_code"] == 403
    assert "related permissions" in widened["error"]
    assert inflated_ttl["success"] is False
    assert inflated_ttl["status_code"] == 403
    assert "TTL is fixed" in inflated_ttl["error"]
    assert approval["success"] is True
    assert approval.get("related_approvals") == []


def test_mobile_challenge_rejects_unregistered_device(tmp_path, monkeypatch):
    service, grants = _service(tmp_path, monkeypatch)
    _grant_mobile_approver(grants)
    request_id = _pending_request(service)

    challenge = service.create_approval_challenge(
        request_id,
        decision="approve",
        actor_principal=_mobile_actor(),
    )

    assert challenge["success"] is False
    assert challenge["status_code"] == 403
    assert "device key" in challenge["error"]


def test_mobile_attestation_rejects_wrong_device_signature(tmp_path, monkeypatch):
    service, grants = _service(tmp_path, monkeypatch)
    _grant_mobile_approver(grants)
    _keypair(service)
    wrong_key = Ed25519PrivateKey.generate()
    request_id = _pending_request(service)
    actor = _mobile_actor()
    challenge = service.create_approval_challenge(
        request_id,
        decision="approve",
        actor_principal=actor,
    )

    approval = service.approve_request(
        request_id,
        scope="once",
        actor_principal=actor,
        attestation=_attestation(wrong_key, challenge),
    )

    assert approval["success"] is False
    assert approval["status_code"] == 403
    assert "signature" in approval["error"]


def test_mobile_attestation_fails_if_grant_revoked_after_challenge(tmp_path, monkeypatch):
    service, grants = _service(tmp_path, monkeypatch)
    _grant_mobile_approver(grants)
    private_key = _keypair(service)
    request_id = _pending_request(service)
    actor = _mobile_actor()
    challenge = service.create_approval_challenge(
        request_id,
        decision="approve",
        actor_principal=actor,
    )
    grants.revoke_permission(
        "profile:work__surface:mobile-approver__device:phone-1",
        "authority.request.approve",
    )

    approval = service.approve_request(
        request_id,
        scope="once",
        actor_principal=actor,
        attestation=_attestation(private_key, challenge),
    )

    assert approval["success"] is False
    assert approval["status_code"] == 403
    assert "grant" in approval["error"]
