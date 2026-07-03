"""Regression coverage for denying or expiring local coding approvals."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_coding_approval_deny_marks_request_denied_and_blocks_execution_token():
    from blocks.coding import approval_deny
    from blocks.coding._approval import approval_required
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    args = {"command": "git push origin master"}
    payload = approval_required("terminal.exec", "high", args=args, command=args["command"])
    request_id = payload["approval_request_id"]

    denied = approval_deny.run({"approval_request_id": request_id, "reason": "User canceled"})

    assert denied["status"] == "ok"
    assert denied["data"]["status"] == "denied"
    stored = approval.get_approval_request(request_id)
    assert stored is not None
    assert stored["status"] == "denied"

    later_approval = approval.approve(request_id)
    assert later_approval["approved"] is False
    assert later_approval["status"] == "denied"

    forged_token = approval.issue_execution_token(
        request_id,
        payload["args_hash"],
        expires_at=stored["expires_at"],
        operation="terminal.exec",
    )
    verification = approval.verify_execution_token(
        forged_token,
        "terminal.exec",
        approval.hash_arguments(args),
        consume=False,
    )
    assert verification.valid is False
    assert verification.code == "APPROVAL_NOT_APPROVED"


def test_expired_pending_approval_cannot_be_approved_or_executed(monkeypatch):
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    monkeypatch.setattr(approval, "_now", lambda: 1_000)
    args = {"command": "rm -rf build"}
    request = approval.create_approval_request("terminal.exec", "high", args=args, expires_in=1)

    monkeypatch.setattr(approval, "_now", lambda: 1_010)
    decision = approval.approve(request["request_id"])

    assert decision["approved"] is False
    assert decision["status"] == "expired"
    stored = approval.get_approval_request(request["request_id"])
    assert stored is not None
    assert stored["status"] == "expired"

    forged_token = approval.issue_execution_token(
        request["request_id"],
        request["args_hash"],
        expires_at=2_000,
        operation="terminal.exec",
    )
    verification = approval.verify_execution_token(
        forged_token,
        "terminal.exec",
        approval.hash_arguments(args),
        consume=False,
    )
    assert verification.valid is False
    assert verification.code == "APPROVAL_NOT_APPROVED"


def test_approved_token_expires_before_execution(monkeypatch):
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    monkeypatch.setattr(approval, "_now", lambda: 2_000)
    args = {"command": "git push origin master"}
    request = approval.create_approval_request("terminal.exec", "high", args=args, expires_in=1)
    decision = approval.approve(request["request_id"])
    assert decision["approved"] is True

    monkeypatch.setattr(approval, "_now", lambda: 2_010)
    verification = approval.verify_execution_token(
        str(decision["token"]),
        "terminal.exec",
        approval.hash_arguments(args),
        consume=False,
    )

    assert verification.valid is False
    assert verification.code == "APPROVAL_EXPIRED"
