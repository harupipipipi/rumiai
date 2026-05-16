from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


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

    assert result["status"] == "ok"
    assert result["data"]["checkpoint"]["snapshot_id"]
    assert listed["status"] == "ok"
    assert listed["data"]["checkpoints"]
