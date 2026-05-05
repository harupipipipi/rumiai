from __future__ import annotations

import sys
from pathlib import Path


DEFAULTSPACK = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))


def test_approval_store_redacts_secrets_and_consumes_once(tmp_path):
    from domain.approval.store import ApprovalStore

    store = ApprovalStore(tmp_path / "approvals.json", now=lambda: 1000.0)
    request = store.request(
        "computer.clipboard.write",
        {
            "api_key": "sk-live",
            "key": "enter",
            "nested": {"refresh_token": "refresh-secret"},
        },
        risk_level="high",
    )

    assert request["approval_id"].startswith("appr_")
    assert "approval_token" not in request
    assert request["payload"]["api_key"] == "[redacted]"
    assert request["payload"]["key"] == "enter"
    assert request["payload"]["nested"]["refresh_token"] == "[redacted]"

    approved = store.approve_once(request["approval_id"])
    assert approved["ok"] is True
    assert approved["approval_token"]
    assert store.consume(
        approval_id=request["approval_id"],
        approval_token=approved["approval_token"],
        action="computer.clipboard.write",
        payload={
            "api_key": "sk-live",
            "key": "enter",
            "nested": {"refresh_token": "refresh-secret"},
        },
    )
    assert not store.consume(
        approval_id=request["approval_id"],
        approval_token=approved["approval_token"],
        action="computer.clipboard.write",
        payload={
            "api_key": "sk-live",
            "key": "enter",
            "nested": {"refresh_token": "refresh-secret"},
        },
    )
    assert "token_hash" not in store.get(request["approval_id"])


def test_approval_store_denied_request_cannot_be_approved(tmp_path):
    from domain.approval.store import ApprovalStore

    store = ApprovalStore(tmp_path / "approvals.json", now=lambda: 1000.0)
    request = store.request("computer.app.open", {"app": "Terminal"}, risk_level="high")
    denied = store.deny(request["approval_id"], reason="not now")
    approved = store.approve_once(request["approval_id"])

    assert denied["ok"] is True
    assert denied["approval"]["status"] == "denied"
    assert approved["ok"] is False
    assert approved["error"] == "approval_denied"


def test_session_approval_can_be_reused_until_expiry(tmp_path):
    from domain.approval.store import ApprovalStore

    now = {"value": 1000.0}
    store = ApprovalStore(tmp_path / "approvals.json", now=lambda: now["value"])
    request = store.request("computer.app.open", {"app": "Finder"}, risk_level="high")
    approved = store.approve_session(request["approval_id"], session_id="session-1", ttl_seconds=60)

    assert approved["ok"] is True
    assert store.consume(
        approval_id=request["approval_id"],
        approval_token=approved["approval_token"],
        action="computer.app.open",
        payload={"app": "Finder"},
        session_id="session-1",
    )
    assert store.consume(
        approval_id=request["approval_id"],
        approval_token=approved["approval_token"],
        action="computer.app.open",
        payload={"app": "Finder"},
        session_id="session-1",
    )

    now["value"] = 1070.0
    assert not store.consume(
        approval_id=request["approval_id"],
        approval_token=approved["approval_token"],
        action="computer.app.open",
        payload={"app": "Finder"},
        session_id="session-1",
    )


def test_approval_blocks_issue_server_side_token(tmp_path, monkeypatch):
    from domain.approval.store import ApprovalStore
    from blocks.approval.approve import run as approve_run
    from blocks.approval.get import run as get_run

    store_path = tmp_path / "approvals.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_APPROVAL_STORE_PATH", str(store_path))
    monkeypatch.delenv("RUMI_DEFAULTSPACK_APPROVALS_PATH", raising=False)
    request = ApprovalStore().request("computer.app.open", {"app": "Finder"}, risk_level="high")

    approved = approve_run({"approval_id": request["approval_id"]}, {})
    fetched = get_run({"approval_id": request["approval_id"]}, {})

    assert approved["status"] == "ok"
    assert approved["data"]["approval_token"]
    assert fetched["status"] == "ok"
    assert fetched["data"]["has_token"] is True
    assert "token_hash" not in fetched["data"]
