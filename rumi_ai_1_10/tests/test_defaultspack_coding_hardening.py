from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture(autouse=True)
def _prefer_defaultspack_domain():
    defaultspack_path = str(DEFAULTSPACK_ROOT)
    while defaultspack_path in sys.path:
        sys.path.remove(defaultspack_path)
    sys.path.insert(0, defaultspack_path)
    domain_module = sys.modules.get("domain")
    domain_file = str(getattr(domain_module, "__file__", "") or "") if domain_module else ""
    domain_path = ";".join(str(item) for item in getattr(domain_module, "__path__", []) or []) if domain_module else ""
    if domain_module is not None and defaultspack_path not in f"{domain_file};{domain_path}":
        for module_name in list(sys.modules):
            if module_name == "domain" or module_name.startswith("domain."):
                sys.modules.pop(module_name, None)


def _init_git_repo(path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is required for worktree checkpoint tests")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)


def _git_commit_all(path: Path, message: str = "initial") -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)


def test_restore_snapshot_rejects_path_traversal_snapshot_id(tmp_path):
    from domain.coding.file_ops import FileOps

    ops = FileOps(tmp_path)
    (tmp_path / "not-a-snapshot").mkdir()

    try:
        ops.restore_snapshot("../not-a-snapshot", ["."])
    except ValueError as exc:
        assert "Invalid snapshot id" in str(exc)
    else:
        raise AssertionError("restore_snapshot accepted a traversal snapshot id")


def test_checkpoint_restore_removes_file_created_after_checkpoint(tmp_path):
    from domain.coding.file_ops import FileOps

    ops = FileOps(tmp_path)
    checkpoint = ops.checkpoint_before_mutation("file.create", ["new.txt"])

    ops.create_file("new.txt", "hello")
    restored = ops.restore_snapshot(checkpoint["snapshot_id"], ["new.txt"])

    assert restored["removed"] == ["new.txt"]
    assert not (tmp_path / "new.txt").exists()


def test_worktree_checkpoint_captures_git_manifest_dirty_contents_and_terminal_log(tmp_path):
    from domain.coding.file_ops import FileOps
    from domain.coding.terminal import Terminal

    _init_git_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _git_commit_all(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    Terminal(tmp_path).execute("pwd")
    checkpoint = FileOps(tmp_path).checkpoint_before_mutation(
        "file.write",
        ["tracked.txt"],
        metadata={"path": "tracked.txt"},
    )

    manifest_path = tmp_path / checkpoint["path"] / "snapshot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    worktree = manifest["worktree"]
    manifest_paths = {entry["path"] for entry in worktree["manifest"]}
    captured_paths = {entry["path"] for entry in worktree["captured_files"]}

    assert manifest["kind"] == "worktree"
    assert "tracked.txt" in manifest_paths
    assert "untracked.txt" in manifest_paths
    assert {"tracked.txt", "untracked.txt"} <= captured_paths
    assert worktree["git"]["available"] is True
    assert worktree["git"]["head"]
    assert "tracked.txt" in worktree["git"]["status"]["modified"]
    assert ".rumi_snapshots" not in worktree["git"]["status"]["porcelain"]
    assert worktree["terminal"]["commands"][-1]["command"] == "pwd"


def test_worktree_checkpoint_skips_ignored_dependency_dirs_for_targeted_mutations(tmp_path):
    from domain.coding.file_ops import FileOps

    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _git_commit_all(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    vendor_file = tmp_path / "node_modules" / "pkg" / "index.js"
    vendor_file.parent.mkdir(parents=True)
    vendor_file.write_text("ignored dependency\n", encoding="utf-8")

    checkpoint = FileOps(tmp_path).checkpoint_before_mutation("file.write", ["tracked.txt"])
    manifest_path = tmp_path / checkpoint["path"] / "snapshot.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_paths = {entry["path"] for entry in manifest["worktree"]["manifest"]}
    captured_paths = {entry["path"] for entry in manifest["worktree"]["captured_files"]}

    assert "tracked.txt" in manifest_paths
    assert "tracked.txt" in captured_paths
    assert "node_modules/pkg/index.js" not in manifest_paths
    assert "node_modules/pkg/index.js" not in captured_paths


def test_worktree_checkpoint_restore_recovers_dirty_untracked_and_clean_tracked_files(tmp_path):
    from domain.coding.file_ops import FileOps

    _init_git_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("clean\n", encoding="utf-8")
    (tmp_path / "clean.txt").write_text("baseline\n", encoding="utf-8")
    _git_commit_all(tmp_path)
    (tmp_path / "tracked.txt").write_text("dirty checkpoint\n", encoding="utf-8")
    (tmp_path / "scratch.txt").write_text("scratch checkpoint\n", encoding="utf-8")

    ops = FileOps(tmp_path)
    checkpoint = ops.checkpoint_before_mutation("manual", ["."])
    (tmp_path / "tracked.txt").write_text("after\n", encoding="utf-8")
    (tmp_path / "clean.txt").write_text("after clean\n", encoding="utf-8")
    (tmp_path / "scratch.txt").write_text("after scratch\n", encoding="utf-8")
    (tmp_path / "later.txt").write_text("remove me\n", encoding="utf-8")

    restored = ops.restore_snapshot(checkpoint["snapshot_id"])

    assert restored["kind"] == "worktree"
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "dirty checkpoint\n"
    assert (tmp_path / "scratch.txt").read_text(encoding="utf-8") == "scratch checkpoint\n"
    assert (tmp_path / "clean.txt").read_text(encoding="utf-8") == "baseline\n"
    assert not (tmp_path / "later.txt").exists()


def test_mutating_file_blocks_return_reversible_checkpoints(tmp_path):
    from blocks.coding.file_delete import run as file_delete_run
    from blocks.coding.file_write import run as file_write_run

    path = tmp_path / "notes.txt"
    path.write_text("before\n", encoding="utf-8")

    write = file_write_run(
        {"workspace_root": str(tmp_path), "path": "notes.txt", "content": "after\n"},
        {"_tool_server_approved": True},
    )

    assert write["status"] == "ok"
    assert write["data"]["checkpoint"]["metadata"]["operation"] == "file.write"
    assert "-before" in write["data"]["diff"]
    assert "+after" in write["data"]["diff"]

    delete = file_delete_run(
        {"workspace_root": str(tmp_path), "path": "notes.txt"},
        {"_tool_server_approved": True},
    )

    assert delete["status"] == "ok"
    assert delete["data"]["checkpoint"]["metadata"]["operation"] == "file.delete"


def test_not_implemented_fails_closed():
    from blocks._common import not_implemented

    result = not_implemented("defaults.frontend.stop")

    assert result["status"] == "error"
    assert result["error"]["code"] == "NOT_IMPLEMENTED"


def test_tool_executor_file_reader_delegates_and_unknown_tools_fail_closed(tmp_path):
    from domain.tool.executor import ToolExecutor

    (tmp_path / "doc.txt").write_text("real content", encoding="utf-8")
    executor = ToolExecutor()

    read = executor._execute_local(
        "file_reader",
        {"path": "doc.txt", "workspace_root": str(tmp_path)},
        {},
    )
    unknown = executor._execute_local("missing_tool", {"x": 1}, {})

    assert read["is_error"] is False
    assert read["result"] == "real content"
    assert unknown["is_error"] is True
    assert "not implemented" in unknown["result"]


def test_coding_checkpoint_functions_are_dispatchable(tmp_path):
    from domain.function_runtime.dispatcher import run_defaultspack_function

    result = run_defaultspack_function(
        "coding_checkpoint_create",
        {"workspace_root": str(tmp_path), "paths": ["missing.txt"]},
        {"_tool_server_approved": True},
    )
    listed = run_defaultspack_function(
        "coding_checkpoint_list",
        {"workspace_root": str(tmp_path)},
        {},
    )
    (tmp_path / "missing.txt").write_text("created after checkpoint", encoding="utf-8")
    restored = run_defaultspack_function(
        "coding_checkpoint_restore",
        {
            "workspace_root": str(tmp_path),
            "snapshot_id": result["data"]["checkpoint"]["snapshot_id"],
            "paths": ["missing.txt"],
        },
        {"_tool_server_approved": True},
    )

    assert result["status"] == "ok"
    assert result["data"]["checkpoint"]["snapshot_id"]
    assert listed["status"] == "ok"
    assert listed["data"]["checkpoints"]
    assert restored["status"] == "ok"
    assert restored["data"]["removed"] == ["missing.txt"]
    assert not (tmp_path / "missing.txt").exists()
