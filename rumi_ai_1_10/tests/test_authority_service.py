from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _HmacKey:
    def get_active_key(self) -> str:
        return "authority-test-key-" + ("x" * 32)


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.capability_grant_manager import CapabilityGrantManager

    grants = CapabilityGrantManager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="capability-test-key-" + ("y" * 32),
    )
    store = AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey())
    return AuthorityService(capability_grant_manager=grants, request_store=store), grants, store


def test_authority_denies_model_without_grant(tmp_path, monkeypatch):
    service, _, store = _service(tmp_path, monkeypatch)

    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        reason="test invoke",
        profile_id="work",
    )

    assert decision.allowed is False
    assert decision.approval_required is True
    assert decision.request_id
    requests = store.list_requests("pending")
    assert len(requests) == 1
    assert requests[0].resource["provider_id"] == "openai"


def test_authority_allows_model_with_profile_grant(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    grants.grant_permission(
        "profile:work",
        "model.invoke",
        {"provider_ids": ["openai"], "api_ids": ["work"], "model_ids": ["gpt-5.4"]},
    )

    allowed = service.check(
        principal_id="profile:work__graph:startup__node:agent.ai",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )
    denied = service.check(
        principal_id="profile:work__graph:startup__node:agent.ai",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "work", "model_id": "claude-sonnet"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.approval_required is True


def test_authority_approve_once_consumes_token(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"}
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
    )
    approval = service.approve_request(decision.request_id, scope="once")

    first = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
        request_id=decision.request_id,
        approval_token=approval["token"],
    )
    second = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
        request_id=decision.request_id,
        approval_token=approval["token"],
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.approval_required is True
