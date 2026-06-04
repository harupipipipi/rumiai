from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.kanban import KanbanController  # noqa: E402
from domain.tool.kanban_agent_session import KanbanAgentSessionController  # noqa: E402
from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def _reset_sessions():
    from blocks.agent import _state

    _state._multi_sessions.clear()


def test_kanban_card_starts_tracks_and_applies_agent_session(tmp_path):
    _reset_sessions()
    context = {"conversation_workspace_dir": str(tmp_path / "workspace")}
    card = KanbanController().run(
        {"action": "create", "title": "Implement task run", "notes": "Keep it backend-only."},
        context,
    )["changed"]
    controller = KanbanAgentSessionController()

    started = controller.run({"action": "start", "card_id": card["id"], "max_turns": 1}, context)
    session_id = started["session_link"]["session_id"]

    assert session_id.startswith("multi_")
    assert started["card"]["column_id"] == "doing"
    assert started["card"]["metadata"]["agent_session"]["task"].startswith("Implement task run")

    status = controller.run({"action": "status", "card_id": card["id"]}, context)
    report = controller.run({"action": "merge_report", "card_id": card["id"]}, context)
    applied = controller.run({"action": "apply", "card_id": card["id"]}, context)

    assert status["session_link"]["status"] == "created"
    assert report["card"]["column_id"] == "review"
    assert report["session_link"]["ready_for_review"] is True
    assert report["session_link"]["merge_report"]["merge_strategy"] == "manual_conflict_report"
    assert applied["card"]["column_id"] == "done"
    assert applied["session_link"]["terminal_state"] == "applied"


def test_kanban_agent_session_tool_and_dispatcher_are_registered(tmp_path):
    _reset_sessions()
    ToolRegistry._instance = None
    context = {"conversation_workspace_dir": str(tmp_path / "workspace")}
    card = KanbanController().run({"action": "create", "title": "Registry task"}, context)["changed"]
    registry = ToolRegistry()

    tool = registry.get("tool_kanban_agent_session")
    executed = ToolExecutor().execute(
        "tool_kanban_agent_session",
        {"action": "start", "card_id": card["id"]},
        {**context, "_tool_server_approved": True, "principal_id": "defaultspack"},
    )

    from ecosystem.defaultspack.domain.function_runtime.dispatcher import run_defaultspack_function

    dispatched_card = KanbanController().run(
        {"action": "create", "title": "Dispatcher task"},
        {"conversation_workspace_dir": str(tmp_path / "dispatcher")},
    )["changed"]
    dispatched = run_defaultspack_function(
        "tool_kanban_agent_session",
        {"action": "start", "card_id": dispatched_card["id"]},
        {"conversation_workspace_dir": str(tmp_path / "dispatcher")},
    )

    assert tool is not None
    assert tool["execution"]["handler"] == "domain.tool.kanban_agent_session:tool_kanban_agent_session"
    assert executed["is_error"] is False
    assert executed["widget"]["type"] == "kanban_agent_session"
    assert dispatched["status"] == "ok"
    assert dispatched["data"]["widget"]["session_link"]["session_id"].startswith("multi_")
