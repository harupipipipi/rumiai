from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_signed_approval_token_binds_operation_and_arguments(tmp_path, monkeypatch):
    from blocks.coding.file_write import run as file_write_run
    from domain.safety.approval import approve, reset_approval_state_for_tests

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    reset_approval_state_for_tests()

    args = {"path": "approved.txt", "content": "ok", "workspace_root": str(tmp_path)}
    request = file_write_run(args, {})

    assert request["status"] == "ok"
    assert request["data"]["approval_required"] is True
    approval = approve(request["data"]["approval_request_id"])
    assert approval["approved"] is True

    written = file_write_run({**args, "approval_token": approval["token"]}, {})
    assert written["status"] == "ok"
    assert written["data"]["written"] is True
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "ok"

    replay = file_write_run({**args, "approval_token": approval["token"]}, {})
    assert replay["status"] == "error"
    assert replay["error"]["code"] == "APPROVAL_TOKEN_USED"


def test_signed_approval_token_rejects_argument_tampering(tmp_path, monkeypatch):
    from blocks.coding.file_write import run as file_write_run
    from domain.safety.approval import approve, reset_approval_state_for_tests

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    reset_approval_state_for_tests()

    args = {"path": "approved.txt", "content": "ok", "workspace_root": str(tmp_path)}
    request = file_write_run(args, {})
    approval = approve(request["data"]["approval_request_id"])

    tampered = file_write_run(
        {**args, "content": "changed", "approval_token": approval["token"]},
        {},
    )

    assert tampered["status"] == "error"
    assert tampered["error"]["code"] == "APPROVAL_ARGUMENTS_CHANGED"
    assert not (tmp_path / "approved.txt").exists()


def test_terminal_stream_starts_real_read_only_process(tmp_path, monkeypatch):
    from blocks.coding.terminal_stream import run as terminal_stream_run

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))

    result = terminal_stream_run({"command": "pwd", "workspace_root": str(tmp_path)}, {})

    assert result["status"] == "ok"
    assert result["data"]["started"] is True
    assert result["data"]["exit_code"] == 0
    assert str(tmp_path) in result["data"]["stdout"]


def test_git_branch_switch_requires_signed_one_shot_approval(tmp_path, monkeypatch):
    from blocks.coding.git_branch import run as git_branch_run
    from domain.safety.approval import approve, reset_approval_state_for_tests

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    reset_approval_state_for_tests()
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True, text=True)

    args = {
        "action": "switch",
        "branch": "feature/local-first",
        "create": True,
        "workspace_root": str(tmp_path),
    }
    request = git_branch_run(args, {})

    assert request["status"] == "ok"
    assert request["data"]["approval_required"] is True
    assert request["data"]["operation"] == "git.branch.create"

    approval = approve(request["data"]["approval_request_id"])
    switched = git_branch_run({**args, "approval_token": approval["token"]}, {})

    assert switched["status"] == "ok"
    assert switched["data"]["branch"] == "feature/local-first"
    assert switched["data"]["created"] is True

    replay = git_branch_run({**args, "approval_token": approval["token"]}, {})
    assert replay["status"] == "error"
    assert replay["error"]["code"] == "APPROVAL_TOKEN_USED"
