from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.authority.debug_cli_operator import authority_snapshot  # noqa: E402
from core_runtime.authority.models import AuthorityRequest  # noqa: E402
from domain.safety import debug_cli_operator as runtime_operator  # noqa: E402
from tobkiri import cli  # noqa: E402


def _authority_request(**overrides):
    values = {
        "request_id": "auth-1",
        "status": "pending",
        "principal_id": "profile:debug",
        "permission_id": "model.invoke",
        "resource": {"kind": "model", "model_id": "m1"},
        "reason": "debug",
        "risk_level": "high",
        "created_at": "2026-07-29T00:00:00Z",
        "expires_at": "2026-07-29T01:00:00Z",
        "conversation_id": "conversation-1",
        "profile_id": "debug",
        "node_id": "agent.ai",
        "graph_id": "default",
    }
    values.update(overrides)
    return AuthorityRequest(**values)


def test_authority_snapshot_digest_changes_with_exact_resource():
    original = authority_snapshot(_authority_request())
    changed = authority_snapshot(_authority_request(resource={"kind": "model", "model_id": "m2"}))

    assert len(original["digest"]) == 64
    assert len(original["target_digest"]) == 64
    assert original["digest"] != changed["digest"]
    assert original["target_digest"] != changed["target_digest"]


def test_runtime_operator_checks_digest_and_exact_provenance(monkeypatch):
    request = {
        "request_id": "apr-1",
        "status": "pending",
        "args_hash": "a" * 64,
        "operation": "computer.click",
        "expires_at": 2_000_000_000,
        "details": {
            "permission_id": "computer.control",
            "function_id": "computer.click",
            "conversation_id": "conversation-1",
        },
    }

    class Broker:
        def available(self):
            return True

        def verify_debug_cli_operator(self, _operator):
            return {"ok": True, "verified": True}

    monkeypatch.setattr(runtime_operator, "get_approval_request", lambda _request_id: request)
    monkeypatch.setattr(
        runtime_operator.ViewerBrokerClient,
        "from_environment",
        classmethod(lambda _cls: Broker()),
    )
    operator = {
        "kind": "debug_cli_operator",
        "origin": "launcher_debug_cli",
        "scope": "once",
        "request_id": "apr-1",
        "canonical_arguments_digest": "a" * 64,
        "operation": "computer.click",
        "permission_id": "computer.control",
        "tool": "computer.click",
        "action": "computer.click",
        "conversation_owner": "conversation-1",
        "expires_at": 1_900_000_000,
    }

    assert runtime_operator.verify_debug_cli_decision("apr-1", "a" * 64, operator) == request
    with pytest.raises(runtime_operator.DebugCliOperatorError, match="digest changed"):
        runtime_operator.verify_debug_cli_decision("apr-1", "b" * 64, operator)
    with pytest.raises(runtime_operator.DebugCliOperatorError, match="action mismatch"):
        runtime_operator.verify_debug_cli_decision(
            "apr-1", "a" * 64, {**operator, "action": "computer.type"}
        )


def test_cli_has_only_individual_approval_commands():
    parser = cli._parser()
    parser.parse_args(["debug", "approvals", "list"])
    parser.parse_args(["debug", "approvals", "show", "apr-1"])
    parser.parse_args(
        [
            "debug",
            "approvals",
            "approve",
            "apr-1",
            "--expected-digest",
            "a" * 64,
        ]
    )
    parser.parse_args(["debug", "approvals", "deny", "apr-1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["debug", "approvals", "approve-all"])


def test_cli_refuses_changed_digest_before_requesting_operator(monkeypatch):
    monkeypatch.setattr(
        cli,
        "_request_by_id",
        lambda _request_id: {
            "_approval_source": "runtime",
            "request_id": "apr-1",
            "args_hash": "a" * 64,
        },
    )
    signed = False

    def sign(_request):
        nonlocal signed
        signed = True
        return {}, "a" * 64

    monkeypatch.setattr(cli, "_signed_operator", sign)
    args = argparse.Namespace(
        request_id="apr-1",
        expected_digest="b" * 64,
        decision="approve",
    )

    with pytest.raises(cli.CliError, match="expected digest"):
        cli._approval_decide(args)
    assert signed is False


def test_cli_approve_resumes_exact_conversation_without_returning_token_in_resume_result(
    monkeypatch,
):
    request = {
        "_approval_source": "runtime",
        "request_id": "apr-1",
        "operation": "computer.click",
        "args_hash": "a" * 64,
        "details": {
            "conversation_id": "conversation-1",
            "function_id": "computer_use",
            "action": "computer.click",
            "arguments": {"x": 12, "y": 34},
        },
    }
    monkeypatch.setattr(cli, "_request_by_id", lambda _request_id: request)
    monkeypatch.setattr(cli, "_signed_operator", lambda _request: ({"signed": True}, "a" * 64))
    monkeypatch.setattr(
        cli,
        "_api_request",
        lambda *_args, **_kwargs: {
            "approved": True,
            "request_id": "apr-1",
            "token": "one-shot-secret",
        },
    )
    captured = {}

    def resume(conversation_id, payload):
        captured["conversation_id"] = conversation_id
        captured["payload"] = payload
        return {"resumed": True, "terminal_event": "done"}

    monkeypatch.setattr(cli, "_api_resume", resume)
    result = cli._approval_decide(
        argparse.Namespace(
            request_id="apr-1",
            expected_digest="a" * 64,
            decision="approve",
        )
    )

    assert result["resumed"] is True
    assert captured["conversation_id"] == "conversation-1"
    assert (
        captured["payload"]["message"]["metadata"]["approval_followup"]["approval_token"]
        == "one-shot-secret"
    )
    assert cli._redact_output(result)["token"] == "[redacted]"


def test_authority_accepts_launcher_verified_debug_operator_once(tmp_path, monkeypatch):
    from core_runtime.authority import service as service_module
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService

    class HmacKey:
        def get_active_key(self):
            return "debug-authority-test-key-" + ("x" * 32)

    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")
    store = AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=HmacKey())
    service = AuthorityService(request_store=store)
    decision = service.check(
        principal_id="profile:debug",
        permission_id="model.invoke",
        resource={"kind": "model", "provider_id": "test", "model_id": "m1"},
        profile_id="debug",
        conversation_id="conversation-1",
    )
    monkeypatch.setattr(
        service_module,
        "verify_authority_debug_operator",
        lambda request, digest, operator: (
            request.request_id == decision.request_id
            and digest == "d" * 64
            and operator == {"signed": True},
            "",
            {
                "decision_source": "delegated_debug_cli",
                "human_approved": False,
            },
        ),
    )

    approved = service.approve_request(
        decision.request_id,
        scope="once",
        debug_cli_operator={"signed": True},
        expected_digest="d" * 64,
    )
    replay = service.approve_request(
        decision.request_id,
        scope="once",
        debug_cli_operator={"signed": True},
        expected_digest="d" * 64,
    )

    assert approved["success"] is True
    assert approved["approved"] is True
    assert approved["scope"] == "once"
    assert replay["success"] is False
    assert replay["status_code"] == 409


def test_coding_approval_rejects_token_and_request_id_without_operator(
    tmp_path, monkeypatch
):
    from blocks.coding import approval_approve
    from domain.tool_policy.internal_context import mark_tool_server_approval_context

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        approval_approve,
        "approve",
        lambda request_id: {
            "request_id": request_id,
            "approved": True,
            "status": "approved",
            "token": "one-shot-secret",
        },
    )
    plain = approval_approve.run({"approval_request_id": "apr-1"}, {})

    ui_context = {"source": "defaultspack_local_ui"}
    mark_tool_server_approval_context(ui_context)
    interactive = approval_approve.run(
        {"approval_request_id": "apr-1"},
        ui_context,
    )

    monkeypatch.setattr(
        approval_approve,
        "verify_debug_cli_decision",
        lambda request_id, digest, operator: {
            "request_id": request_id,
            "args_hash": digest,
            "operator": operator,
        },
    )
    delegated = approval_approve.run(
        {
            "approval_request_id": "apr-2",
            "expected_digest": "a" * 64,
            "debug_cli_operator": {"signed": True},
        },
        {},
    )

    assert plain["status"] == "error"
    assert plain["error"]["code"] == "APPROVAL_OPERATOR_REQUIRED"
    assert interactive["status"] == "ok"
    assert delegated["status"] == "ok"


def test_coding_interactive_ui_provenance_requires_browser_fetch_headers(
    monkeypatch,
):
    from transport.http import _local_ui_approval_route_authorized

    monkeypatch.setenv("RUMI_DEFAULTSPACK_LOCAL_TOKEN", "local-test-token")
    bearer_only = {"Authorization": "Bearer local-test-token"}
    interactive = {
        **bearer_only,
        "Origin": "http://127.0.0.1:8766",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
    }

    assert (
        _local_ui_approval_route_authorized(
            "POST", "/api/coding/approvals/approve", bearer_only
        )
        is False
    )
    assert (
        _local_ui_approval_route_authorized(
            "POST", "/api/coding/approvals/approve", interactive
        )
        is True
    )
