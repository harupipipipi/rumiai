from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.kanban import KanbanController  # noqa: E402
from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def test_kanban_tracks_dependencies_blockers_and_subtasks(tmp_path):
    context = {"conversation_workspace_dir": str(tmp_path / "workspace")}
    controller = KanbanController()
    foundation = controller.run({"action": "create", "title": "Foundation"}, context)["changed"]
    feature = controller.run(
        {
            "action": "create",
            "title": "Feature",
            "depends_on": [foundation["id"]],
            "blocked_by": [foundation["id"]],
            "blocker_reason": "Waiting for foundation",
            "subtasks": ["Implement API", {"title": "Write tests", "done": True}],
        },
        context,
    )
    feature_id = feature["changed"]["id"]

    added = controller.run({"action": "subtask_add", "card_id": feature_id, "title": "Update docs"}, context)
    subtask_id = next(item["id"] for item in added["changed"]["subtasks"] if item["title"] == "Update docs")
    completed = controller.run({"action": "subtask_complete", "card_id": feature_id, "subtask_id": subtask_id}, context)
    unblocked = controller.run({"action": "unblock", "card_id": feature_id}, context)

    assert feature["dependency_counts"]["cards_blocked"] == 1
    assert feature["dependency_counts"]["total_dependencies"] == 1
    assert feature["blocked_cards"][0]["blocker_reason"] == "Waiting for foundation"
    assert completed["dependency_counts"]["completed_subtasks"] == 2
    assert completed["dependency_counts"]["open_subtasks"] == 1
    assert unblocked["dependency_counts"]["cards_blocked"] == 0
    assert unblocked["changed"]["depends_on"] == [foundation["id"]]


def test_tool_kanban_relations_manifest_loads_and_executes(tmp_path):
    ToolRegistry._instance = None
    registry = ToolRegistry()
    context = {"conversation_workspace_dir": str(tmp_path), "_tool_server_approved": True, "principal_id": "defaultspack"}
    root = ToolExecutor().execute("tool_kanban", {"action": "create", "title": "Root"}, context)["widget"]["changed"]
    result = ToolExecutor().execute(
        "tool_kanban",
        {"action": "create", "title": "Child", "depends_on": [root["id"]]},
        context,
    )

    tool = registry.get("tool_kanban")

    assert tool is not None
    assert "subtask_add" in tool["schema"]["parameters"]["properties"]["action"]["enum"]
    assert result["is_error"] is False
    assert result["widget"]["dependency_counts"]["total_dependencies"] == 1
