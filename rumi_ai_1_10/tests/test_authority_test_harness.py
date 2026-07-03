from __future__ import annotations

import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _HmacKey:
    def get_active_key(self) -> str:
        return "authority-test-harness-key-" + ("x" * 32)


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "authority-harness-panel-" + ("p" * 32))
    from core_runtime.authority.approval_challenge_store import ApprovalChallengeStore
    from core_runtime.authority.device_key_registry import DeviceKeyRegistry
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService
    from core_runtime.capability_grant_manager import CapabilityGrantManager

    grants = CapabilityGrantManager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="authority-harness-capability-" + ("y" * 32),
    )
    store = AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey())
    service = AuthorityService(
        capability_grant_manager=grants,
        request_store=store,
        approval_challenge_store=ApprovalChallengeStore(
            tmp_path / "approval_challenges",
            hmac_key_manager=_HmacKey(),
        ),
        device_key_registry=DeviceKeyRegistry(
            tmp_path / "device_keys",
            secret_key="authority-harness-device-" + ("z" * 32),
        ),
    )
    return service, grants, store


def _resource(provider_id: str = "openai") -> dict:
    return {
        "kind": "model",
        "provider_id": provider_id,
        "api_id": "qa",
        "model_id": "gpt-test",
    }


def _pending_model_request(service, provider_id: str = "openai"):
    return service.check(
        principal_id="profile:qa",
        permission_id="model.invoke",
        resource=_resource(provider_id),
        reason="agent QA model call",
        profile_id="qa",
    )


def _approve_rule(provider_id: str = "openai") -> dict:
    return {
        "rule_id": "qa-model-approve",
        "decision": "approve",
        "permission_id": "model.invoke",
        "resource": {"provider_id": provider_id},
        "scope": "once",
        "expires_in_seconds": 60,
    }


def test_authority_test_mode_disabled_does_not_settle_request(tmp_path, monkeypatch):
    from core_runtime.authority.test_harness import settle_authority_test_request

    service, _, store = _service(tmp_path, monkeypatch)
    monkeypatch.delenv("RUMI_AUTHORITY_TEST_MODE", raising=False)
    decision = _pending_model_request(service)

    result = settle_authority_test_request(service, decision.request_id, rule=_approve_rule())

    assert result["success"] is False
    assert result["status_code"] == 404
    assert store.get_request(decision.request_id).status == "pending"
    assert list((tmp_path / "authority" / "one_shot").glob("*.json")) == []


def test_authority_test_mode_rejected_for_packaged_production_profile():
    from core_runtime.authority.test_harness import authority_test_mode_status

    status = authority_test_mode_status(
        {
            "RUMI_AUTHORITY_TEST_MODE": "1",
            "RUMI_ENVIRONMENT": "production",
            "RUMI_PACKAGED": "1",
        }
    )

    assert status.enabled is False
    assert status.status_code == 403
    assert "RUMI_ENVIRONMENT=production" in status.markers
    assert "RUMI_PACKAGED=true" in status.markers


def test_authority_test_harness_auto_approve_uses_one_shot_and_audit_marker(tmp_path, monkeypatch):
    from core_runtime.authority.test_harness import settle_authority_test_request

    service, _, store = _service(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_MODE", "1")
    monkeypatch.setenv("RUMI_ENVIRONMENT", "test")
    decision = _pending_model_request(service)
    assert list((tmp_path / "authority" / "one_shot").glob("*.json")) == []

    result = settle_authority_test_request(
        service,
        decision.request_id,
        rule=_approve_rule(),
        scenario_id="agent-qa",
    )

    assert result["success"] is True
    assert result["authority_mode"] == "test"
    assert result["scope"] == "once"
    assert result["authority_followup"]["request_id"] == decision.request_id
    assert result["authority_followup"]["permission_id"] == "model.invoke"
    assert len(list((tmp_path / "authority" / "one_shot").glob("*.json"))) == 1

    first = service.check(
        principal_id="profile:qa",
        permission_id="model.invoke",
        resource=_resource(),
        profile_id="qa",
        request_id=decision.request_id,
        approval_token=result["authority_followup"]["approval_token"],
    )
    second = service.check(
        principal_id="profile:qa",
        permission_id="model.invoke",
        resource=_resource(),
        profile_id="qa",
        request_id=decision.request_id,
        approval_token=result["authority_followup"]["approval_token"],
    )

    assert first.allowed is True
    assert second.allowed is False
    events = store.list_events(100)
    settled = [item for item in events if item["action"] == "authority_test_harness_settled"]
    assert settled
    assert settled[-1]["details"]["authority_mode"] == "test"
    assert settled[-1]["details"]["scenario_id"] == "agent-qa"
    assert settled[-1]["verified"] is True


def test_authority_test_harness_requires_scoped_matching_policy(tmp_path, monkeypatch):
    from core_runtime.authority.test_harness import settle_authority_test_request

    service, _, store = _service(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_MODE", "1")
    monkeypatch.setenv("RUMI_ENVIRONMENT", "test")
    decision = _pending_model_request(service)

    missing_resource = settle_authority_test_request(
        service,
        decision.request_id,
        rule={
            "rule_id": "too-broad",
            "decision": "approve",
            "permission_id": "model.invoke",
        },
    )
    wrong_resource = settle_authority_test_request(
        service,
        decision.request_id,
        rule={
            "rule_id": "wrong-provider",
            "decision": "approve",
            "permission_id": "model.invoke",
            "resource": {"provider_id": "anthropic"},
        },
    )

    assert missing_resource["success"] is False
    assert missing_resource["status_code"] == 412
    assert wrong_resource["success"] is False
    assert wrong_resource["status_code"] == 412
    assert store.get_request(decision.request_id).status == "pending"


def test_authority_test_harness_auto_deny_leaves_no_usable_grant(tmp_path, monkeypatch):
    from core_runtime.authority.test_harness import settle_authority_test_request

    service, _, store = _service(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_MODE", "1")
    monkeypatch.setenv("RUMI_ENVIRONMENT", "test")
    decision = _pending_model_request(service)

    result = settle_authority_test_request(
        service,
        decision.request_id,
        rule={
            "rule_id": "qa-model-deny",
            "decision": "deny",
            "permission_id": "model.invoke",
            "resource": {"provider_id": "openai"},
            "reason": "negative QA path",
        },
    )
    next_decision = service.check(
        principal_id="profile:qa",
        permission_id="model.invoke",
        resource=_resource(),
        profile_id="qa",
    )

    assert result["success"] is True
    assert result["denied"] is True
    assert store.get_request(decision.request_id).status == "denied"
    assert next_decision.allowed is False
    assert next_decision.approval_required is True
    assert list((tmp_path / "authority" / "one_shot").glob("*.json")) == []


def test_authority_test_harness_synthetic_timeout_and_cancel(tmp_path, monkeypatch):
    from core_runtime.authority.test_harness import settle_authority_test_request

    service, _, store = _service(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_MODE", "1")
    monkeypatch.setenv("RUMI_ENVIRONMENT", "test")
    timeout_request = _pending_model_request(service, "openai")

    timeout = settle_authority_test_request(
        service,
        timeout_request.request_id,
        rule={
            "rule_id": "qa-timeout",
            "decision": "synthetic_timeout",
            "permission_id": "model.invoke",
            "resource": {"provider_id": "openai"},
        },
    )
    late_approval = settle_authority_test_request(
        service,
        timeout_request.request_id,
        rule=_approve_rule(),
    )
    cancel_request = _pending_model_request(service, "anthropic")
    cancel = settle_authority_test_request(
        service,
        cancel_request.request_id,
        rule={
            "rule_id": "qa-cancel",
            "decision": "synthetic_cancel",
            "permission_id": "model.invoke",
            "resource": {"provider_id": "anthropic"},
        },
    )

    assert timeout["success"] is True
    assert timeout["status"] == "expired"
    assert store.get_request(timeout_request.request_id).status == "expired"
    assert late_approval["success"] is False
    assert late_approval["status_code"] == 409
    assert cancel["success"] is True
    assert cancel["cancelled"] is True
    assert store.get_request(cancel_request.request_id).status == "denied"


def test_authority_test_harness_racing_duplicate_settlement_settles_once(tmp_path, monkeypatch):
    from core_runtime.authority.test_harness import settle_authority_test_request

    service, _, store = _service(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_MODE", "1")
    monkeypatch.setenv("RUMI_ENVIRONMENT", "test")
    decision = _pending_model_request(service)
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def settle():
        barrier.wait(timeout=2)
        result = settle_authority_test_request(
            service,
            decision.request_id,
            rule=_approve_rule(),
            scenario_id="race",
        )
        with lock:
            results.append(result)

    threads = [threading.Thread(target=settle) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    successes = [item for item in results if item["success"]]
    failures = [item for item in results if not item["success"]]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0]["status_code"] == 409
    assert store.get_request(decision.request_id).status == "approved"
    assert len(list((tmp_path / "authority" / "one_shot").glob("*.json"))) == 1


def test_authority_test_settle_http_endpoint_is_token_gated_and_agent_friendly(
    tmp_path,
    monkeypatch,
):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    service, _, _ = _service(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_MODE", "1")
    monkeypatch.setenv("RUMI_ENVIRONMENT", "test")
    monkeypatch.setenv("RUMI_AUTHORITY_TEST_TOKEN", "settle-secret")
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    decision = _pending_model_request(service)
    server = DefaultsHttpServer.__new__(DefaultsHttpServer)

    missing = server._handle_authority_test_settle({"request_id": decision.request_id}, {})
    settled = server._handle_authority_test_settle(
        {
            "request_id": decision.request_id,
            "_headers": {"X-Rumi-Authority-Test-Token": "settle-secret"},
            "settlement": _approve_rule(),
        },
        {},
    )

    assert missing["status"] == "error"
    assert missing["_http_status"] == 401
    assert settled["status"] == "ok"
    assert settled["data"]["authority_mode"] == "test"
    assert settled["data"]["authority_followup"]["request_id"] == decision.request_id


def test_authority_test_settle_route_is_registered():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    handler, params, source, path_inject, _ = server._match_route(
        "POST",
        "/api/authority/test/settle",
    )

    assert handler == server._handle_authority_test_settle
    assert params == {}
    assert source == "fallback"
    assert path_inject == {}
