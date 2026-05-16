from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _fresh_approval_module(monkeypatch, db_path: Path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_APPROVAL_DB_PATH", str(db_path))
    for name in ("domain.safety.approval", "domain.safety.approval_store"):
        sys.modules.pop(name, None)
    import domain.safety.approval as approval

    return approval


def test_approval_requests_survive_process_restart(tmp_path, monkeypatch):
    approval = _fresh_approval_module(monkeypatch, tmp_path / "approval.sqlite3")
    approval.reset_approval_state_for_tests()

    args = {"command": "git push origin main", "workspace_root": str(tmp_path)}
    request = approval.create_approval_request("terminal.exec", "high", args, details={"command": args["command"]})

    approval = _fresh_approval_module(monkeypatch, tmp_path / "approval.sqlite3")
    listed = approval.list_approval_requests()

    assert [item["request_id"] for item in listed] == [request["request_id"]]
    assert listed[0]["status"] == "pending"
    assert listed[0]["operation"] == "terminal.exec"


def test_one_shot_token_replay_is_rejected_after_restart(tmp_path, monkeypatch):
    approval = _fresh_approval_module(monkeypatch, tmp_path / "approval.sqlite3")
    approval.reset_approval_state_for_tests()

    args = {"path": "approved.txt", "content": "ok", "workspace_root": str(tmp_path)}
    request = approval.create_approval_request("file.write", "high", args, details={"path": "approved.txt"})
    decision = approval.approve(request["request_id"])

    assert decision["approved"] is True
    token = decision["token"]
    assert approval.verify_execution_token(token, "file.write", approval.hash_arguments(args)).valid is True

    approval = _fresh_approval_module(monkeypatch, tmp_path / "approval.sqlite3")
    replay = approval.verify_execution_token(token, "file.write", approval.hash_arguments(args))

    assert replay.valid is False
    assert replay.code == "APPROVAL_TOKEN_USED"
