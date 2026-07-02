from __future__ import annotations

import json
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
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(tmp_path / "store" / "coding_workspaces.json"))
    from domain.change_request import ChangeRequestService, ChangeRequestStore

    return ChangeRequestService(store=ChangeRequestStore())


def _trusted_workspace_id(workspace: Path, workspace_id: str = "trusted-review") -> str:
    from domain.coding.workspace_store import WorkspaceStore

    WorkspaceStore().create(workspace, workspace_id=workspace_id, trusted=True)
    return workspace_id


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
    (workspace / "test_sample.py").write_text(
        "def test_ok():\n    print('BEGIN_FULL_LOG' + ('x' * 13000))\n    assert True\n",
        encoding="utf-8",
    )
    service = _service(tmp_path, monkeypatch)
    workspace_id = _trusted_workspace_id(workspace)
    created = service.create(workspace_root=str(workspace), workspace_id=workspace_id, title="Review")

    with pytest.raises(ValueError):
        service.run_check(created["id"], {"command": "python -m pytest && rm -rf ."})
    with pytest.raises(ValueError):
        service.run_check(created["id"], {"command": "cargo test --manifest-path=../../other-project/Cargo.toml"})
    with pytest.raises(ValueError):
        service.run_check(created["id"], {"command": ["python", "-m", "pytest", "--rootdir", "../outside"]})

    result = service.run_check(created["id"], {"command": "python -m pytest test_sample.py -q -s"})
    check = result["check"]
    fetched = service.get(created["id"])
    stored_payload = json.loads(service.store.storage_path.read_text(encoding="utf-8"))
    stored_check = stored_payload["change_requests"][created["id"]]["checks"][0]
    artifact_log = service.store.check_log_path(created["id"], check["id"]).read_text(encoding="utf-8")

    assert check["status"] == "passed"
    assert check["log_ref"].startswith("store://change_request/")
    assert check["full_log_ref"] == check["log_ref"]
    assert "full_log" not in check
    assert "full_log" not in stored_check
    assert "BEGIN_FULL_LOG" in artifact_log
    assert "BEGIN_FULL_LOG" not in stored_check["log_tail"]
    assert len(stored_check["stdout_tail"]) <= 12000
    assert len(stored_check["stderr_tail"]) <= 12000
    assert len(stored_check["log_tail"]) <= 12000
    assert fetched["check_summary"]["passed"] == 1


def test_change_request_collection_requires_registered_trusted_workspace(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    _service(tmp_path, monkeypatch)

    from blocks.change_request.collection import run as collection_run

    raw = collection_run({"_method": "POST", "workspace_root": str(workspace), "title": "Review"}, {})
    assert raw["status"] == "error"
    assert raw["error"]["code"] == "WORKSPACE_UNTRUSTED"

    workspace_id = _trusted_workspace_id(workspace)
    trusted = collection_run({"_method": "POST", "workspace_id": workspace_id, "title": "Review"}, {})
    assert trusted["status"] == "ok"
    assert trusted["data"]["workspace_id"] == workspace_id


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
    assert result["data"]["blocked"] is True
    assert result["data"]["reason"] == "phase1_review_only"

    monkeypatch.setenv("RUMI_REVIEW_ENABLE_COMMIT", "1")
    result = commit_run({"id": created["id"], "message": "sealed", "approved": True}, {})
    assert result["status"] == "ok"
    assert result["data"]["approval_required"] is True
