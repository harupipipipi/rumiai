from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _HmacKey:
    def get_active_key(self) -> str:
        return "authority-test-key-" + ("x" * 32)


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "panel-bootstrap-test-secret-" + ("p" * 32))
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.capability_grant_manager import CapabilityGrantManager

    grants = CapabilityGrantManager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="capability-test-key-" + ("y" * 32),
    )
    store = AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey())
    return AuthorityService(capability_grant_manager=grants, request_store=store), grants, store


def _ui_operator(request_id: str):
    from core_runtime.authority.ui_operator import sign_ui_operator

    return sign_ui_operator(request_id, nonce="nonce-" + request_id)


def _grant_profile_chain(grants, principal_id: str, permission_id: str, config: dict | None = None) -> None:
    parts = [part for part in principal_id.split("__") if part]
    for index in range(1, len(parts) + 1):
        grants.grant_permission("__".join(parts[:index]), permission_id, dict(config or {}))


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


def test_authority_allows_model_with_profile_and_child_grants(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    child_principal = "profile:work__graph:startup__node:agent.ai"
    _grant_profile_chain(
        grants,
        child_principal,
        "model.invoke",
        {"provider_ids": ["openai"], "api_ids": ["work"], "model_ids": ["gpt-5.4"]},
    )

    allowed = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )
    denied = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "work", "model_id": "claude-sonnet"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.approval_required is True


def test_authority_approval_cannot_widen_requested_resource(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="profile",
        config={
            "provider_ids": ["openai", "anthropic"],
            "api_ids": ["work", "personal"],
            "model_ids": ["gpt-5.4", "claude-sonnet"],
        },
        ui_operator=_ui_operator(decision.request_id),
    )
    allowed = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )
    widened = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "personal", "model_id": "claude-sonnet"},
        profile_id="work",
    )

    assert approval["success"] is True
    assert approval["config"] == {"provider_ids": ["openai"], "api_ids": ["work"], "model_ids": ["gpt-5.4"]}
    assert allowed.allowed is True
    assert widened.allowed is False
    assert widened.approval_required is True


def test_authority_empty_config_lists_do_not_grant_everything(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": []})

    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )

    assert decision.allowed is False
    assert decision.approval_required is True


def test_authority_config_lattice_empty_child_inherits_parent_facets():
    from core_runtime.authority.config_lattice import meet_authority_configs

    assert meet_authority_configs({"provider_ids": ["openai"]}, {}) == {"provider_ids": ["openai"]}


def test_authority_config_lattice_child_provider_must_be_subset_of_parent():
    from core_runtime.authority.config_lattice import is_authority_config_subset, meet_authority_configs

    parent = {"provider_ids": ["openai"]}
    child = {"provider_ids": ["anthropic"]}

    assert is_authority_config_subset(child, parent) is False
    assert meet_authority_configs(parent, child) == {"provider_ids": []}


def test_authority_config_lattice_empty_list_is_deny_all():
    from core_runtime.authority.config_lattice import meet_authority_configs

    assert meet_authority_configs({"provider_ids": ["openai"]}, {"provider_ids": []}) == {"provider_ids": []}


def test_authority_config_lattice_rejects_unknown_keys():
    from core_runtime.authority.config_lattice import AuthorityConfigError, validate_authority_config

    with pytest.raises(AuthorityConfigError):
        validate_authority_config({"provider_ids": ["openai"], "unexpected": ["anthropic"]})


def test_authority_config_lattice_ignores_persisted_metadata_keys():
    from core_runtime.authority.config_lattice import meet_authority_configs

    assert meet_authority_configs({"mode": "builtin", "provider_ids": ["openai"]}) == {
        "provider_ids": ["openai"]
    }


def test_authority_profile_child_graph_node_inherits_parent_grant_when_missing(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    child_principal = "profile:work__graph:startup__node:agent.ai"
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": ["openai"]})

    allowed = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )
    denied = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "work", "model_id": "claude-sonnet"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    assert allowed.allowed is True
    assert allowed.grant_config == {"provider_ids": ["openai"]}
    assert denied.allowed is False
    assert denied.approval_required is True


def test_authority_profile_surface_child_still_requires_explicit_grant(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    surface_principal = "profile:work__surface:mobile__device:phone-1"
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": ["openai"]})

    decision = service.check(
        principal_id=surface_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )

    assert decision.allowed is False
    assert decision.approval_required is True


def test_authority_profile_principal_ignores_conversation_and_global_grants(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    grants.grant_permission("conversation:c1", "model.invoke", {"provider_ids": ["openai"]})
    grants.grant_permission("global", "model.invoke", {"provider_ids": ["openai"]})

    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
        conversation_id="c1",
    )

    assert decision.allowed is False
    assert decision.approval_required is True


def test_authority_stub_and_rumi_require_grants(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)

    stub = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "stub", "api_id": "local", "model_id": "default"},
        profile_id="work",
    )
    rumi = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "rumi", "api_id": "local", "model_id": "default"},
        profile_id="work",
    )

    assert stub.allowed is False
    assert stub.approval_required is True
    assert rumi.allowed is False
    assert rumi.approval_required is True


def test_authority_profile_child_empty_config_inherits_parent_constraints(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    child_principal = "profile:work__graph:startup__node:agent.ai"
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": ["openai"]})
    grants.grant_permission("profile:work__graph:startup", "model.invoke", {})
    grants.grant_permission(child_principal, "model.invoke", {})

    allowed = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )
    denied = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "work", "model_id": "claude-sonnet"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    assert allowed.allowed is True
    assert allowed.grant_config == {"provider_ids": ["openai"]}
    assert denied.allowed is False
    assert denied.approval_required is True


def test_authority_profile_child_cannot_widen_parent_provider(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    child_principal = "profile:work__graph:startup__node:agent.ai"
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": ["openai"]})
    grants.grant_permission("profile:work__graph:startup", "model.invoke", {})
    grants.grant_permission(child_principal, "model.invoke", {"provider_ids": ["anthropic"]})

    decision = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "work", "model_id": "claude-sonnet"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    assert decision.allowed is False
    assert decision.approval_required is True


def test_authority_profile_child_disabled_permission_blocks_parent_grant(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    child_principal = "profile:work__graph:startup__node:agent.ai"
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": ["openai"]})
    grants.grant_permission("profile:work__graph:startup", "model.invoke", {})
    grants.grant_permission(child_principal, "model.invoke", {})
    assert grants.revoke_permission(child_principal, "model.invoke") is True

    decision = service.check(
        principal_id=child_principal,
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    assert decision.allowed is False
    assert decision.approval_required is True


def test_authority_approve_once_consumes_token(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"}
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
    )
    approval = service.approve_request(
        decision.request_id,
        scope="once",
        ui_operator=_ui_operator(decision.request_id),
    )

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


def test_authority_non_consuming_check_does_not_spend_one_shot_token(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"}
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
    )
    approval = service.approve_request(
        decision.request_id,
        scope="once",
        ui_operator=_ui_operator(decision.request_id),
    )

    preflight = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
        request_id=decision.request_id,
        approval_token=approval["token"],
        consume_approval_token=False,
    )
    reusable_preflight = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
        request_id=decision.request_id,
        approval_token=approval["token"],
        consume_approval_token=False,
    )
    consumed = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
        request_id=decision.request_id,
        approval_token=approval["token"],
    )
    after_consumed = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
        request_id=decision.request_id,
        approval_token=approval["token"],
        consume_approval_token=False,
    )

    assert preflight.allowed is True
    assert reusable_preflight.allowed is True
    assert consumed.allowed is True
    assert after_consumed.allowed is False
    assert after_consumed.approval_required is True


def test_authority_approve_once_can_bundle_model_api_key_and_network_tokens(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    model_resource = {
        "kind": "model",
        "provider_id": "openai",
        "api_id": "work",
        "model_id": "gpt-5.4",
        "domain": "api.openai.com",
        "port": 443,
    }
    api_resource = {**model_resource, "kind": "api_key"}
    network_resource = {**model_resource, "kind": "network"}
    decision = service.check(
        principal_id="conversation:c1",
        permission_id="model.invoke",
        resource=model_resource,
        conversation_id="c1",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="once",
        related_permissions=["api_key.use", "network.egress"],
        ui_operator=_ui_operator(decision.request_id),
    )
    related = {item["permission_id"]: item for item in approval["related_approvals"]}

    model_allowed = service.check(
        principal_id="conversation:c1",
        permission_id="model.invoke",
        resource=model_resource,
        conversation_id="c1",
        request_id=approval["request_id"],
        approval_token=approval["token"],
    )
    api_allowed = service.check(
        principal_id="conversation:c1",
        permission_id="api_key.use",
        resource=api_resource,
        conversation_id="c1",
        request_id=related["api_key.use"]["request_id"],
        approval_token=related["api_key.use"]["token"],
    )
    network_allowed = service.check(
        principal_id="conversation:c1",
        permission_id="network.egress",
        resource=network_resource,
        conversation_id="c1",
        request_id=related["network.egress"]["request_id"],
        approval_token=related["network.egress"]["token"],
    )

    assert approval["permission_id"] == "model.invoke"
    assert related["api_key.use"]["resource"]["kind"] == "api_key"
    assert related["network.egress"]["resource"]["kind"] == "network"
    assert model_allowed.allowed is True
    assert api_allowed.allowed is True
    assert network_allowed.allowed is True


def test_authority_persistent_approval_can_bundle_model_api_key_and_network_grants(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "model",
        "provider_id": "openai",
        "api_id": "work",
        "model_id": "gpt-5.4",
        "domain": "api.openai.com",
        "port": 443,
    }
    decision = service.check(
        principal_id="conversation:c1",
        permission_id="model.invoke",
        resource=resource,
        conversation_id="c1",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="conversation",
        related_permissions=["api_key.use", "network.egress"],
        ui_operator=_ui_operator(decision.request_id),
    )
    grant = grants.get_grant("conversation:c1")

    assert approval["success"] is True
    assert grant is not None
    assert "model.invoke" in grant.permissions
    assert "api_key.use" in grant.permissions
    assert "network.egress" in grant.permissions


def test_authority_request_display_metadata_explains_provider_endpoint_and_key(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "model",
        "provider_id": "opencode-go",
        "api_id": "legacy",
        "model_id": "deepseek-v4-pro",
        "pack_id": "defaultspack",
        "app_display_name": "defaultspack v2",
        "provider_display_name": "OpenCode Go provider",
        "model_display_name": "DeepSeek V4 Pro via OpenCode Go",
        "credential_label": "OpenCode Go API key",
        "endpoint_url": "https://opencode.ai/zen/go/v1/chat/completions",
        "endpoint_path": "/chat/completions",
        "domain": "opencode.ai",
        "port": 443,
    }
    decision = service.check(
        principal_id="conversation:c1",
        permission_id="model.invoke",
        resource=resource,
        conversation_id="c1",
    )

    view = service.get_request(decision.request_id)["request"]
    display = view["display_metadata"]

    assert display["title"] == (
        "defaultspack v2 / OpenCode Go provider に OpenCode Go API key の使用と "
        "https://opencode.ai/zen/go/v1/chat/completions へのアクセスを許可しますか？"
    )
    assert "OpenCode Go API key の使用" in display["summary"]
    assert "https://opencode.ai/zen/go/v1/chat/completions へのアクセス" in display["summary"]
    assert "使用 と" not in display["summary"]
    assert "アクセス を" not in display["summary"]
    assert display["model_display_name"] == "DeepSeek V4 Pro via OpenCode Go"
    assert display["endpoint_host"] == "opencode.ai"
    assert "provider provider" not in display["title"]
    assert "provider provider" not in display["summary"]


def test_authority_request_display_metadata_exposes_safe_host_execution_summary(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "critical_host_function",
        "pack_id": "third_party_pack",
        "function_id": "run_shell",
        "host_operation": "shell.exec",
        "args_summary": {
            "executable": "/bin/rm",
            "argument_count": 3,
            "cwd": "/tmp/project",
            "target_paths": ["/tmp/unsafe-target"],
            "target_urls": ["https://alice:secret@example.test/hook?token=query-secret#frag"],
        },
        "confirmation_phrase": "RUMI-HOST-TEST",
        "typed_confirmation_required": True,
    }
    decision = service.check(
        principal_id="third_party_pack",
        permission_id="host.process.exec_guarded",
        resource=resource,
        reason="Direct host execution requires typed confirmation",
    )

    view = service.get_request(decision.request_id)["request"]
    display = view["display_metadata"]

    assert display["title"] == "Host操作 shell.exec を許可しますか？"
    assert "third_party_pack / run_shell" in display["summary"]
    assert display["access_summary"] == (
        "shell.exec / one-shot / exec: /bin/rm / args: 3 / cwd: /tmp/project / "
        "paths: /tmp/unsafe-target / urls: https://example.test/hook"
    )
    assert display["host_execution_summary"] == {
        "executable": "/bin/rm",
        "argument_count": 3,
        "cwd": "/tmp/project",
        "target_paths": ["/tmp/unsafe-target"],
        "target_urls": ["https://example.test/hook"],
    }
    assert display["confirmation_phrase"] == "RUMI-HOST-TEST"
    display_json = json.dumps(display, ensure_ascii=False)
    assert "secret" not in display_json.lower()
    assert "token" not in display_json.lower()
    assert "alice" not in display_json.lower()


def test_authority_approve_once_ignores_stream_transport_flag(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "model",
        "provider_id": "opencode-go",
        "api_id": "legacy",
        "model_id": "qwen3.5-plus",
        "stream": True,
    }
    decision = service.check(
        principal_id="conversation:c1",
        permission_id="model.invoke",
        resource=resource,
        conversation_id="c1",
    )
    approval = service.approve_request(
        decision.request_id,
        scope="once",
        ui_operator=_ui_operator(decision.request_id),
    )

    followup = service.check(
        principal_id="conversation:c1",
        permission_id="model.invoke",
        resource={**resource, "stream": False},
        conversation_id="c1",
        request_id=decision.request_id,
        approval_token=approval["token"],
    )

    assert followup.allowed is True


def test_authority_critical_host_approval_requires_typed_confirmation(tmp_path, monkeypatch):
    service, _, store = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "critical_host_function",
        "operation": "shell.exec",
        "confirmation_phrase": "RUMI-HOST-TEST",
        "typed_confirmation_required": True,
    }
    decision = service.check(
        principal_id="pack:untrusted",
        permission_id="host.process.exec_guarded",
        resource=resource,
        reason="Direct host execution requires typed confirmation",
    )

    view = service.get_request(decision.request_id)["request"]
    display = view["display_metadata"]
    wrong = service.approve_request(
        decision.request_id,
        scope="once",
        config={"confirmation_text": "RUMI-HOST-WRONG"},
        ui_operator=_ui_operator(decision.request_id),
    )
    persistent = service.approve_request(
        decision.request_id,
        scope="conversation",
        config={"confirmation_text": "RUMI-HOST-TEST"},
        ui_operator=_ui_operator(decision.request_id),
    )
    approved = service.approve_request(
        decision.request_id,
        scope="once",
        config={"confirmation_text": "RUMI-HOST-TEST"},
        ui_operator=_ui_operator(decision.request_id),
    )

    assert view["allowed_scopes"] == ["once"]
    assert display["typed_confirmation_required"] is True
    assert display["confirmation_phrase"] == "RUMI-HOST-TEST"
    assert wrong["success"] is False
    assert wrong["status_code"] == 400
    assert persistent["success"] is False
    assert persistent["status_code"] == 400
    assert approved["success"] is True
    assert store.get_request(decision.request_id).status == "approved"


def test_authority_service_resolves_from_di(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")

    from core_runtime.authority import AuthorityService, get_authority_service
    from core_runtime.capability_grant_manager import reset_capability_grant_manager
    from core_runtime.di_container import get_container, reset_container

    reset_container()
    reset_capability_grant_manager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="capability-test-key-" + ("z" * 32),
    )

    try:
        container = get_container()
        assert container.has("capability_grant_manager")
        assert isinstance(get_authority_service(), AuthorityService)
    finally:
        reset_container()


def test_authority_persistent_approval_keeps_resource_constraints(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    resource = {"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"}
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="profile",
        config={"allow_stream": True},
        ui_operator=_ui_operator(decision.request_id),
    )

    assert approval["success"] is True
    assert approval["config"] == {
        "provider_ids": ["openai"],
        "api_ids": ["work"],
        "model_ids": ["gpt-5.4"],
    }

    grant = grants.get_grant("profile:work")
    assert grant is not None
    assert grant.permissions["model.invoke"].config == approval["config"]

    allowed = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource=resource,
        profile_id="work",
    )
    denied = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "anthropic", "api_id": "personal", "model_id": "claude"},
        profile_id="work",
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.approval_required is True


def test_authority_persistent_host_grant_unions_resource_action_fields(tmp_path, monkeypatch):
    service, grants, _ = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "host_intent",
        "host_action": "host.process.open_url",
        "operation": "host.process.open_url.preview",
    }
    decision = service.check(
        principal_id="profile:work",
        permission_id="host.process.open_url",
        resource=resource,
        profile_id="work",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="profile",
        config={"host_actions": ["host.process.open_url.preview", "host.process.open_url"]},
        ui_operator=_ui_operator(decision.request_id),
    )

    assert approval["success"] is True
    assert approval["config"] == {
        "host_actions": ["host.process.open_url", "host.process.open_url.preview"],
    }

    grant = grants.get_grant("profile:work")
    assert grant is not None
    assert grant.permissions["host.process.open_url"].config == approval["config"]

    host_action_allowed = service.check(
        principal_id="profile:work",
        permission_id="host.process.open_url",
        resource={"kind": "host_intent", "host_action": "host.process.open_url"},
        profile_id="work",
    )
    operation_allowed = service.check(
        principal_id="profile:work",
        permission_id="host.process.open_url",
        resource={"kind": "host_intent", "operation": "host.process.open_url.preview"},
        profile_id="work",
    )
    unrelated_denied = service.check(
        principal_id="profile:work",
        permission_id="host.process.open_url",
        resource={"kind": "host_intent", "operation": "host.process.launch_app"},
        profile_id="work",
    )

    assert host_action_allowed.allowed is True
    assert operation_allowed.allowed is True
    assert unrelated_denied.allowed is False
    assert unrelated_denied.approval_required is True


def test_authority_persistent_host_grant_dedupes_matching_action_fields(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    resource = {
        "kind": "host_intent",
        "host_action": "host.process.open_url",
        "operation": "host.process.open_url",
    }
    decision = service.check(
        principal_id="profile:work",
        permission_id="host.process.open_url",
        resource=resource,
        profile_id="work",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="profile",
        ui_operator=_ui_operator(decision.request_id),
    )

    assert approval["success"] is True
    assert approval["config"] == {"host_actions": ["host.process.open_url"]}


def test_authority_approve_requires_signed_ui_operator(tmp_path, monkeypatch):
    service, _, store = _service(tmp_path, monkeypatch)
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )

    approval = service.approve_request(decision.request_id, scope="once")

    assert approval["success"] is False
    assert approval["status_code"] == 403
    assert store.get_request(decision.request_id).status == "pending"


def test_authority_request_cannot_be_approved_twice(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )

    first = service.approve_request(
        decision.request_id,
        scope="once",
        ui_operator=_ui_operator(decision.request_id),
    )
    second = service.approve_request(
        decision.request_id,
        scope="once",
        ui_operator=_ui_operator(decision.request_id),
    )

    assert first["success"] is True
    assert second["success"] is False
    assert second["status_code"] == 409


def test_authority_rejects_global_scope(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )

    approval = service.approve_request(
        decision.request_id,
        scope="global",
        ui_operator=_ui_operator(decision.request_id),
    )

    assert approval["success"] is False
    assert approval["status_code"] == 400


def test_authority_signed_deny_and_request_views(tmp_path, monkeypatch):
    service, _, store = _service(tmp_path, monkeypatch)
    decision = service.check(
        principal_id="profile:work__graph:startup__node:agent.ai",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        reason="Need OpenAI model",
        conversation_id="conv_1",
        profile_id="work",
        graph_id="startup",
        node_id="agent.ai",
    )

    listed = service.list_requests("pending")
    single = service.get_request(decision.request_id)
    denied = service.deny_request(
        decision.request_id,
        reason="not now",
        ui_operator=_ui_operator(decision.request_id),
    )

    assert listed["count"] == 1
    assert listed["pending"][0]["display_metadata"]["title"] == "openai / work / gpt-5.4"
    assert listed["pending"][0]["allowed_scopes"] == ["once", "conversation", "profile", "node"]
    assert single["request"]["request_id"] == decision.request_id
    assert denied["success"] is True
    assert denied["denied"] is True
    assert store.get_request(decision.request_id).status == "denied"


def test_authority_mobile_approver_is_profile_scoped(tmp_path, monkeypatch):
    from core_runtime.access_tokens import AuthenticatedPrincipal

    service, _, _ = _service(tmp_path, monkeypatch)
    work = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "work", "model_id": "gpt-5.4"},
        profile_id="work",
    )
    personal = service.check(
        principal_id="profile:personal",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "openai", "api_id": "personal", "model_id": "gpt-5.4"},
        profile_id="personal",
    )
    actor = AuthenticatedPrincipal(
        token_id="tok",
        profile_id="work",
        surface_id="mobile-approver",
        device_id="phone-1",
        role="mobile_approver",
        audiences=("kernel_api",),
        issued_at="",
        expires_at=None,
    )

    listed = service.list_requests("pending", actor_principal=actor)
    hidden = service.get_request(personal.request_id, actor_principal=actor)
    cross_profile_approval = service.approve_request(
        personal.request_id,
        scope="once",
        actor_principal=actor,
        ui_operator=_ui_operator(personal.request_id),
    )
    persistent = service.approve_request(
        work.request_id,
        scope="profile",
        actor_principal=actor,
        ui_operator=_ui_operator(work.request_id),
    )

    assert [item["request_id"] for item in listed["requests"]] == [work.request_id]
    assert hidden["success"] is False
    assert hidden["status_code"] == 404
    assert cross_profile_approval["success"] is False
    assert cross_profile_approval["status_code"] == 404
    assert persistent["success"] is False
    assert persistent["status_code"] == 403


def test_authority_scoped_grants_are_profile_filtered(tmp_path, monkeypatch):
    from core_runtime.access_tokens import AuthenticatedPrincipal

    service, grants, _ = _service(tmp_path, monkeypatch)
    grants.grant_permission("profile:work", "model.invoke", {"provider_ids": ["openai"]})
    grants.grant_permission("profile:work__graph:startup", "model.invoke", {"model_ids": ["gpt-5.4"]})
    grants.grant_permission("profile:personal", "model.invoke", {"provider_ids": ["anthropic"]})
    actor = AuthenticatedPrincipal(
        token_id="tok",
        profile_id="work",
        surface_id="mobile",
        device_id="phone-1",
        role="mobile_client",
        audiences=("kernel_api",),
        issued_at="",
        expires_at=None,
    )

    own_default = service.list_grants(actor_principal=actor)
    own_child = service.list_grants("profile:work__graph:startup", actor_principal=actor)
    other = service.list_grants("profile:personal", actor_principal=actor)
    core_all = service.list_grants(actor_principal=AuthenticatedPrincipal.legacy_root())

    assert set(own_default["grants"]) == {"profile:work"}
    assert set(own_child["grants"]) == {"profile:work__graph:startup"}
    assert other["success"] is False
    assert other["status_code"] == 404
    assert set(core_all["grants"]) >= {"profile:work", "profile:personal"}


def test_authority_events_are_core_only(tmp_path, monkeypatch):
    from core_runtime.access_tokens import AuthenticatedPrincipal

    service, _, store = _service(tmp_path, monkeypatch)
    store.audit("authority_request_denied", {"principal_id": "profile:personal"})
    actor = AuthenticatedPrincipal(
        token_id="tok",
        profile_id="work",
        surface_id="mobile",
        device_id="phone-1",
        role="mobile_client",
        audiences=("kernel_api",),
        issued_at="",
        expires_at=None,
    )

    scoped = service.events(actor_principal=actor)
    core = service.events(actor_principal=AuthenticatedPrincipal.legacy_root())

    assert scoped["success"] is False
    assert scoped["status_code"] == 403
    assert core["_sse"] is True
    assert core["events"]


def test_authority_request_resource_redacts_secret_like_keys(tmp_path, monkeypatch):
    service, _, store = _service(tmp_path, monkeypatch)

    decision = service.check(
        principal_id="profile:work",
        permission_id="model.invoke",
        resource={
            "kind": "model",
            "provider_id": "openai",
            "api_id": "work",
            "model_id": "gpt-5.4",
            "apiKey": "sk-test",
            "access_token": "access-secret",
            "refresh-token": "refresh-secret",
            "x-api-key": "header-secret",
            "bearer": "bearer-secret",
            "input_tokens": 42,
            "metadata": {"safe": "ok", "clientSecret": "nested-secret"},
        },
        profile_id="work",
    )

    stored = store.get_request(decision.request_id)

    assert stored is not None
    assert stored.resource["input_tokens"] == 42
    assert stored.resource["metadata"] == {"safe": "ok"}
    assert "apiKey" not in stored.resource
    assert "access_token" not in stored.resource
    assert "refresh-token" not in stored.resource
    assert "x-api-key" not in stored.resource
    assert "bearer" not in stored.resource


def test_authority_audit_events_are_verified_and_tamper_marked(tmp_path, monkeypatch):
    _, _, store = _service(tmp_path, monkeypatch)
    store.audit("authority_test_event", {"provider_id": "openai"})

    events = store.list_events()

    assert events[-1]["action"] == "authority_test_event"
    assert events[-1]["verified"] is True
    assert "_hmac_signature" not in events[-1]

    lines = store._audit_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[-1])
    tampered["details"]["provider_id"] = "anthropic"
    store._audit_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    tampered_events = store.list_events()

    assert tampered_events[-1]["action"] == "authority_audit_tampered"
    assert tampered_events[-1]["verified"] is False
    assert tampered_events[-1]["tampered"] is True
    assert tampered_events[-1]["details"] == {}


def test_authority_resource_allowed_rejects_empty_constraints():
    from core_runtime.authority.service import AuthorityService

    assert AuthorityService._resource_allowed({"provider_ids": []}, {"provider_id": "openai"}) is False
