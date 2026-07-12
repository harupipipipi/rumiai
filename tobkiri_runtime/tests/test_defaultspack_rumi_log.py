from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _init_git_repo(path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for .rumi log tests")
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)


def _commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)


def _porcelain(path: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_git_commit_records_local_rumi_event_without_dirtying_status(tmp_path):
    from domain.coding.git_ops import GitOps
    from domain.coding.rumi_log import RumiLogStore

    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("clean\n", encoding="utf-8")
    _commit_all(tmp_path, "initial")
    (tmp_path / "a.txt").write_text("dirty\n", encoding="utf-8")

    result = GitOps(tmp_path).commit(
        "agent change",
        paths=["a.txt"],
        actor_id="commit-a1",
        agent_role="commit-pair-a",
        session_id="session-1",
    )

    events = RumiLogStore(tmp_path).list_events(limit=10)
    assert result["commit_hash"]
    assert events[0]["kind"] == "git.commit"
    assert events[0]["actor_id"] == "commit-a1"
    assert events[0]["agent_role"] == "commit-pair-a"
    assert events[0]["commit_hash"] == result["commit_hash"]
    assert events[0]["paths"] == ["a.txt"]
    assert ".rumi" not in _porcelain(tmp_path)


def test_rumi_log_seed_plan_is_idempotent(tmp_path):
    from domain.coding.rumi_log import RumiLogStore

    _init_git_repo(tmp_path)
    store = RumiLogStore(tmp_path)
    first = store.seed_local_plan()
    second = store.seed_local_plan()

    assert first["created"] is True
    assert second["created"] is False
    events = store.list_events(limit=20)
    assert len(events) == 14
    assert {event["kind"] for event in events} == {"plan.created", "agent.assigned", "task.created", "agent.message"}
    summary = store.summary()
    assert summary["plan_count"] == 1
    assert summary["task_count"] == 4
    assert summary["conversation_count"] == 4
    assert summary["mention_count"] >= 4
    assert ".rumi" not in _porcelain(tmp_path)


def test_rumi_log_block_lists_and_appends(tmp_path, monkeypatch):
    from blocks.coding.rumi_log import run as rumi_log_run
    from domain.coding.workspace_store import WorkspaceStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(tmp_path / "workspaces.json"))
    _init_git_repo(tmp_path)
    WorkspaceStore().create(tmp_path, workspace_id="rumi-log-test", trusted=True)
    seeded = rumi_log_run(
        {"workspace_root": str(tmp_path), "action": "seed_local_plan"},
        {},
    )
    assert seeded["status"] == "ok", seeded
    assert seeded["data"]["created"] is True

    appended = rumi_log_run(
        {
            "workspace_root": str(tmp_path),
            "action": "append",
            "kind": "agent.note",
            "actor_id": "ui-widget",
            "task_id": "T-105",
            "message": "watch commit pair",
        },
        {},
    )
    assert appended["status"] == "ok", appended
    assert appended["data"]["event"]["kind"] == "agent.note"
    assert appended["data"]["event"]["metadata"]["task_id"] == "T-105"

    listed = rumi_log_run({"workspace_root": str(tmp_path), "method": "GET", "limit": 5}, {})
    assert listed["status"] == "ok", listed
    assert listed["data"]["summary"]["total"] == 15
    assert listed["data"]["events"][0]["message"] == "watch commit pair"


def test_rumi_log_mutation_rejects_unregistered_raw_workspace_root(tmp_path, monkeypatch):
    from blocks.coding.rumi_log import run as rumi_log_run

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(tmp_path / "workspaces.json"))
    _init_git_repo(tmp_path)

    seeded = rumi_log_run(
        {"workspace_root": str(tmp_path), "action": "seed_local_plan"},
        {},
    )
    appended = rumi_log_run(
        {
            "workspace_root": str(tmp_path),
            "action": "append",
            "kind": "agent.note",
            "message": "should not write",
        },
        {},
    )

    assert seeded["status"] == "error"
    assert seeded["error"]["code"] == "WORKSPACE_UNTRUSTED"
    assert appended["status"] == "error"
    assert appended["error"]["code"] == "WORKSPACE_UNTRUSTED"
    assert not (tmp_path / ".rumi").exists()
