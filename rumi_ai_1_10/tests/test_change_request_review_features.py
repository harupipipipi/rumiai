from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _init_git_repo(path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for change_request review tests")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)


def _commit_all(path: Path, message: str = "initial") -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)


def _service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHANGE_REQUEST_STORE_PATH", str(tmp_path / "store" / "change_requests.json"))
    from domain.change_request import ChangeRequestService, ChangeRequestStore

    return ChangeRequestService(store=ChangeRequestStore())


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _init_git_repo(workspace)
    (workspace / "app.py").write_text("print('clean')\n", encoding="utf-8")
    _commit_all(workspace)
    (workspace / "app.py").write_text("print('dirty')\n", encoding="utf-8")
    return workspace


def test_comments_decisions_and_viewed_files_are_persisted(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    service = _service(tmp_path, monkeypatch)
    created = service.create(workspace_root=str(workspace), title="Review")
    cr_id = created["id"]

    commented = service.add_comment(
        cr_id,
        {
            "kind": "suggestion",
            "body": "Prefer a helper.",
            "path": "app.py",
            "line": 1,
            "suggested_patch": "diff --git a/app.py b/app.py\n",
        },
    )
    comment = commented["comment"]
    fetched = service.get(cr_id)
    assert fetched["unresolved_count"] == 1
    assert fetched["suggestion_count"] == 1
    assert fetched["comments"][0]["suggested_patch"]

    service.update_comment(cr_id, comment["id"], {"resolved": True})
    decided = service.submit_decision(cr_id, {"decision": "approve"})
    viewed = service.set_viewed_file(cr_id, {"path": "app.py", "viewed": True})
    fetched = service.get(cr_id)

    assert fetched["unresolved_count"] == 0
    assert decided["change_request"]["status"] == "approved"
    assert decided["change_request"]["decision"] == "approved"
    assert viewed["viewed_files"]["app.py"]["viewed"] is True


def test_run_check_uses_allowlist_and_persists_log_tail(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    (workspace / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    service = _service(tmp_path, monkeypatch)
    created = service.create(workspace_root=str(workspace), title="Review")

    with pytest.raises(ValueError):
        service.run_check(created["id"], {"command": "python -m pytest && rm -rf ."})

    result = service.run_check(created["id"], {"command": "python -m pytest test_sample.py -q"})
    check = result["check"]
    fetched = service.get(created["id"])

    assert check["status"] == "passed"
    assert check["log_ref"].startswith("store://change_request/")
    assert fetched["check_summary"]["passed"] == 1


def test_commit_seal_blocks_drift_and_commit_updates_status(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    service = _service(tmp_path, monkeypatch)
    created = service.create(workspace_root=str(workspace), title="Review")

    (workspace / "app.py").write_text("print('drift')\n", encoding="utf-8")
    blocked = service.commit(created["id"], {"message": "sealed"})
    assert blocked["blocked"] is True
    assert blocked["reason"] == "seal_mismatch"

    refreshed = service.refresh(created["id"])["change_request"]
    service.submit_decision(refreshed["id"], {"decision": "approve"})
    committed = service.commit(refreshed["id"], {"message": "sealed"})

    assert committed["committed"] is True
    assert committed["change_request"]["status"] == "committed"
    assert committed["commit"]["commit_hash"]


def test_commit_block_ignores_client_approved_flag(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    service = _service(tmp_path, monkeypatch)
    created = service.create(workspace_root=str(workspace), title="Review")

    from blocks.change_request.commit import run as commit_run

    result = commit_run({"id": created["id"], "message": "sealed", "approved": True}, {})
    assert result["status"] == "ok"
    assert result["data"]["approval_required"] is True
