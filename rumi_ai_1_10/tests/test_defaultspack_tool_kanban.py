from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.kanban import KanbanController  # noqa: E402
from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def test_kanban_controller_persists_workspace_board_and_moves_cards(tmp_path):
    workspace = tmp_path / "conversation" / "workspace"
    controller = KanbanController()

    created = controller.run(
        {"action": "create", "title": "Review PR slice", "priority": "high"},
        {"conversation_workspace_dir": str(workspace)},
    )
    card_id = created["changed"]["id"]
    moved = controller.run(
        {"action": "move", "card_id": card_id, "column": "Doing"},
        {"conversation_workspace_dir": str(workspace)},
    )

    board_path = workspace / "kanban.json"
    stored = json.loads(board_path.read_text(encoding="utf-8"))

    assert board_path.exists()
    assert [column["title"] for column in moved["columns"]] == ["Backlog", "Doing", "Review", "Done"]
    assert moved["cards"][0]["column_id"] == "doing"
    assert stored["cards"][0]["priority"] == "high"


def test_kanban_controller_configures_columns_and_rehomes_removed_column_cards(tmp_path):
    workspace = tmp_path / "workspace"
    controller = KanbanController()

    created = controller.run(
        {"action": "create", "title": "Ship minimal backend", "column": "Review"},
        {"conversation_workspace_dir": str(workspace)},
    )
    configured = controller.run(
        {"action": "configure", "columns": ["Inbox", "Active", "Done"]},
        {"conversation_workspace_dir": str(workspace)},
    )

    assert created["changed"]["column_id"] == "review"
    assert [column["id"] for column in configured["columns"]] == ["inbox", "active", "done"]
    assert configured["cards"][0]["column_id"] == "inbox"


def test_kanban_controller_preserves_board_order_and_done_count_for_custom_terminal_columns(tmp_path):
    workspace = tmp_path / "workspace"
    controller = KanbanController()

    controller.run(
        {
            "action": "configure",
            "columns": [
                {"title": "Inbox"},
                {"title": "Active"},
                {"title": "Completed"},
            ],
        },
        {"conversation_workspace_dir": str(workspace)},
    )
    controller.run({"action": "create", "title": "First", "column": "Inbox"}, {"conversation_workspace_dir": str(workspace)})
    controller.run({"action": "create", "title": "Second", "column": "Active"}, {"conversation_workspace_dir": str(workspace)})
    listed = controller.run(
        {"action": "create", "title": "Third", "column": "Completed"},
        {"conversation_workspace_dir": str(workspace)},
    )

    assert listed["summary"].endswith("(2 open)")
    assert [card["title"] for card in listed["cards"]] == ["First", "Second", "Third"]
    assert [column["done"] for column in listed["columns"]] == [False, False, True]


def test_tool_registry_and_executor_invoke_manifest_backed_kanban(tmp_path):
    ToolRegistry._instance = None
    registry = ToolRegistry()

    tool = registry.get("tool_kanban")
    result = ToolExecutor().execute(
        "tool_kanban",
        {"action": "create", "title": "Exercise ToolExecutor"},
        {
            "conversation_workspace_dir": str(tmp_path),
            "_tool_server_approved": True,
            "principal_id": "defaultspack",
        },
    )

    assert tool is not None
    assert tool["execution"]["handler"] == "domain.tool.kanban:tool_kanban"
    assert "done" in tool["schema"]["parameters"]["properties"]["columns"]["items"]["oneOf"][1]["properties"]
    assert result["is_error"] is False
    assert result["widget"]["type"] == "kanban"
    assert result["widget"]["cards"][0]["title"] == "Exercise ToolExecutor"


def test_tool_kanban_function_runtime_registers_and_invokes(tmp_path):
    from core_runtime.di_container import get_container, reset_container
    from core_runtime.pack_function_runtime import invoke_pack_function
    from ecosystem.defaultspack.domain.function_runtime.bridge import ensure_defaultspack_functions_registered
    from ecosystem.defaultspack.domain.function_runtime.dispatcher import run_defaultspack_function

    reset_container()
    registered = ensure_defaultspack_functions_registered(get_container())
    dispatched = run_defaultspack_function(
        "tool_kanban",
        {"action": "create", "title": "Exercise dispatcher"},
        {"conversation_workspace_dir": str(tmp_path / "dispatcher")},
    )
    output = invoke_pack_function(
        "defaultspack",
        "tool_kanban",
        {"action": "create", "title": "Exercise function runtime"},
        {"conversation_workspace_dir": str(tmp_path)},
    )

    assert registered > 0
    assert dispatched["status"] == "ok"
    assert dispatched["data"]["widget"]["type"] == "kanban"
    assert output["status"] == "ok"
    assert output["data"]["is_error"] is False
    assert output["data"]["widget"]["type"] == "kanban"
    assert output["data"]["widget"]["columns"][0]["title"] == "Backlog"
