from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture
def broker(monkeypatch):
    from blocks.ui import frontend_capability

    frontend_capability._SEEN_REQUESTS.clear()
    monkeypatch.setattr(frontend_capability.time, "time", lambda: 1_000.0)
    audit_events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        frontend_capability,
        "audit_event",
        lambda _context, event_type, payload: audit_events.append(
            (event_type, dict(payload))
        ),
    )
    frontend_capability._test_audit_events = audit_events
    plan = SimpleNamespace(profile_id="profile-1", plan_hash="plan-1")
    monkeypatch.setattr(frontend_capability, "active_resolved_profile", lambda: plan)
    return frontend_capability


def _contribution(
    *,
    contribution_id: str,
    action_contract: str | None = None,
    data_source_contract: str | None = None,
):
    return SimpleNamespace(
        contribution_id=contribution_id,
        owner_pack_id="workflow-pack",
        resolved_plan_hash="plan-1",
        action_contract=action_contract,
        data_source_contract=data_source_contract,
        isolated=None,
    )


def _request(
    request_id: str,
    *,
    contribution_id: str,
    contract_id: str,
    operation: str = "query",
    input_data: dict | None = None,
):
    return {
        "request_id": request_id,
        "expires_at": 1_030,
        "profile_id": "profile-1",
        "plan_hash": "plan-1",
        "owner_pack_id": "workflow-pack",
        "contribution_id": contribution_id,
        "contract_id": contract_id,
        "payload": {
            "operation": operation,
            "input": dict(input_data or {}),
        },
    }


def test_data_source_invocation_is_profile_bound_and_preserves_query_contract(
    broker,
    monkeypatch,
):
    contribution = _contribution(
        contribution_id="workflows.list",
        data_source_contract="rumi.resource.workflow.list.v1",
    )
    monkeypatch.setattr(
        broker,
        "build_frontend_catalog",
        lambda _plan: SimpleNamespace(contributions=(contribution,)),
    )
    calls: list[tuple[object, str, str, dict]] = []
    monkeypatch.setattr(
        broker,
        "invoke_global_contract",
        lambda registry, contract_id, operation, payload: calls.append(
            (registry, contract_id, operation, payload)
        )
        or {"items": [{"id": "one", "label": "One"}]},
    )
    registry = object()

    result = broker.run(
        _request(
            "query-1",
            contribution_id="workflows.list",
            contract_id="rumi.resource.workflow.list.v1",
            input_data={"query": "active", "cursor": "page-2", "limit": 50},
        ),
        {"interface_registry": registry},
    )

    assert result["status"] == "ok"
    assert calls == [
        (
            registry,
            "rumi.resource.workflow.list.v1",
            "query",
            {
                "query": "active",
                "cursor": "page-2",
                "limit": 50,
                "profile_id": "profile-1",
            },
        )
    ]
    assert [event for event, _payload in broker._test_audit_events] == [
        "frontend_capability.executed"
    ]


def test_action_requires_local_approval_and_preserves_idempotency(
    broker,
    monkeypatch,
):
    contribution = _contribution(
        contribution_id="workflows.select",
        action_contract="rumi.action.workflow.select.v1",
    )
    monkeypatch.setattr(
        broker,
        "build_frontend_catalog",
        lambda _plan: SimpleNamespace(contributions=(contribution,)),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        broker,
        "invoke_global_contract",
        lambda _registry, _contract, _operation, payload: calls.append(payload)
        or {"selected": payload["value"]},
    )
    request = _request(
        "action-denied",
        contribution_id="workflows.select",
        contract_id="rumi.action.workflow.select.v1",
        operation="invoke",
        input_data={
            "value": "workflow-1",
            "requested_value_scope": "draft",
            "idempotency_key": "idem-1",
        },
    )

    denied = broker.run(request, {"interface_registry": object()})
    approved = broker.run(
        {**request, "request_id": "action-approved"},
        {"interface_registry": object(), "_tool_server_approved": True},
    )

    assert denied["error"]["code"] == "CAPABILITY_DENIED"
    assert approved == {"status": "ok", "data": {"selected": "workflow-1"}}
    assert calls == [
        {
            "value": "workflow-1",
            "requested_value_scope": "draft",
            "idempotency_key": "idem-1",
            "profile_id": "profile-1",
        }
    ]
    assert [event for event, _payload in broker._test_audit_events] == [
        "frontend_capability.denied",
        "frontend_capability.executed",
    ]


@pytest.mark.parametrize(
    ("override", "expected_code"),
    [
        ({"request_id": "same-request"}, "STALE_OR_REPLAYED"),
        ({"owner_pack_id": "forged-pack", "request_id": "forged-owner"}, "CAPABILITY_DENIED"),
        ({"plan_hash": "old-plan", "request_id": "stale-plan"}, "STALE_RESOLUTION"),
        ({"contract_id": "rumi.resource.other.v1", "request_id": "undeclared"}, "CAPABILITY_DENIED"),
    ],
)
def test_replay_stale_and_forged_bindings_fail_closed(
    broker,
    monkeypatch,
    override,
    expected_code,
):
    contribution = _contribution(
        contribution_id="workflows.list",
        data_source_contract="rumi.resource.workflow.list.v1",
    )
    monkeypatch.setattr(
        broker,
        "build_frontend_catalog",
        lambda _plan: SimpleNamespace(contributions=(contribution,)),
    )
    monkeypatch.setattr(
        broker,
        "invoke_global_contract",
        lambda *_args: {"unexpected": True},
    )
    base = _request(
        "same-request",
        contribution_id="workflows.list",
        contract_id="rumi.resource.workflow.list.v1",
    )
    if override["request_id"] == "same-request":
        first = broker.run(base, {"interface_registry": object()})
        assert first["status"] == "ok"

    result = broker.run({**base, **override}, {"interface_registry": object()})

    assert result["status"] == "error"
    assert result["error"]["code"] == expected_code


def test_contract_validation_failure_is_returned_without_partial_success(
    broker,
    monkeypatch,
):
    contribution = _contribution(
        contribution_id="workflows.list",
        data_source_contract="rumi.resource.workflow.list.v1",
    )
    monkeypatch.setattr(
        broker,
        "build_frontend_catalog",
        lambda _plan: SimpleNamespace(contributions=(contribution,)),
    )

    def reject_schema(*_args):
        raise broker.GlobalContractInvocationError(
            "invalid_schema",
            "query input did not match the registered contract",
        )

    monkeypatch.setattr(broker, "invoke_global_contract", reject_schema)

    result = broker.run(
        _request(
            "invalid-schema",
            contribution_id="workflows.list",
            contract_id="rumi.resource.workflow.list.v1",
        ),
        {"interface_registry": object()},
    )

    assert result == {
        "status": "error",
        "error": {
            "code": "invalid_schema",
            "message": "query input did not match the registered contract",
        },
    }
    assert broker._test_audit_events[-1][0] == "frontend_capability.failed"
    assert broker._test_audit_events[-1][1]["code"] == "invalid_schema"


def test_oversized_contract_input_is_rejected_before_provider_dispatch(
    broker,
    monkeypatch,
):
    contribution = _contribution(
        contribution_id="workflows.list",
        data_source_contract="rumi.resource.workflow.list.v1",
    )
    monkeypatch.setattr(
        broker,
        "build_frontend_catalog",
        lambda _plan: SimpleNamespace(contributions=(contribution,)),
    )
    calls: list[object] = []
    monkeypatch.setattr(
        broker,
        "invoke_global_contract",
        lambda *_args: calls.append(object()),
    )

    result = broker.run(
        _request(
            "oversized",
            contribution_id="workflows.list",
            contract_id="rumi.resource.workflow.list.v1",
            input_data={"query": "x" * (broker._MAX_CONTRACT_INPUT_BYTES + 1)},
        ),
        {"interface_registry": object()},
    )

    assert result["error"]["code"] == "CAPABILITY_INPUT_TOO_LARGE"
    assert calls == []
    assert broker._test_audit_events[-1][0] == "frontend_capability.denied"
