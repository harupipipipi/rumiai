from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _fresh_approval_module(monkeypatch, db_path: Path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_APPROVAL_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CHAT_STORE_PATH",
        str(db_path.parent / "chat" / "conversations.json"),
    )
    for name in (
        "domain.safety.approval",
        "domain.safety.approval_state_json",
        "domain.safety.approval_store",
    ):
        sys.modules.pop(name, None)
    import domain.safety.approval as approval

    return approval


def test_approval_requests_survive_process_restart(tmp_path, monkeypatch):
    approval = _fresh_approval_module(monkeypatch, tmp_path / "approval.sqlite3")
    approval.reset_approval_state_for_tests()

    args = {"command": "git push origin main", "workspace_root": str(tmp_path)}
    request = approval.create_approval_request(
        "terminal.exec",
        "high",
        args,
        details={"command": args["command"], "conversation_id": "conv-audit"},
    )

    mirror_path = tmp_path / "chat" / "approval_state.json"
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    assert [item["request_id"] for item in mirror["requests"]] == [request["request_id"]]
    assert mirror["requests"][0]["status"] == "pending"

    conversation_mirror = tmp_path / "chat" / "conversations" / "conv-audit" / "approval_state.json"
    conversation_payload = json.loads(conversation_mirror.read_text(encoding="utf-8"))
    assert [item["request_id"] for item in conversation_payload["requests"]] == [request["request_id"]]

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


def test_json_only_pending_is_listed_for_recovery_and_sqlite_wins_conflicts(tmp_path, monkeypatch):
    approval = _fresh_approval_module(monkeypatch, tmp_path / "approval.sqlite3")
    approval.reset_approval_state_for_tests()

    args = {"path": "winner.txt", "content": "ok", "workspace_root": str(tmp_path)}
    sqlite_request = approval.create_approval_request("file.write", "high", args, details={"path": "winner.txt"})
    decision = approval.approve(sqlite_request["request_id"])
    assert decision["approved"] is True

    json_only = {
        "request_id": "apr_json_only_recovery",
        "operation": "terminal.exec",
        "risk_level": "high",
        "args_hash": approval.hash_arguments({"command": "echo recover"}),
        "details": {"command": "echo recover"},
        "created_at": sqlite_request["created_at"] + 10,
        "expires_at": sqlite_request["expires_at"],
        "status": "pending",
        "decision_at": None,
    }
    stale_conflict = {
        **sqlite_request,
        "operation": "terminal.exec",
        "details": {"command": "stale mirror"},
        "status": "pending",
        "decision_at": None,
    }
    mirror_path = tmp_path / "chat" / "approval_state.json"
    mirror_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": sqlite_request["created_at"],
                "requests": [json_only, stale_conflict],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    listed = approval.list_approval_requests()
    by_id = {item["request_id"]: item for item in listed}

    assert by_id["apr_json_only_recovery"]["status"] == "pending"
    assert by_id[sqlite_request["request_id"]]["status"] == "approved"
    assert by_id[sqlite_request["request_id"]]["operation"] == "file.write"

    pending = approval.list_approval_requests(status="pending")
    pending_ids = {item["request_id"] for item in pending}
    assert "apr_json_only_recovery" in pending_ids
    assert sqlite_request["request_id"] not in pending_ids
