from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_tool_selection_excludes_computer_tools_from_new_auto_selector():
    from domain.chat.tool_selection_orchestrator import ToolSelectionOrchestrator

    tools = [
        {"tool_id": "search_docs", "summary": "Search project docs", "tags": ["search"]},
        {"tool_id": "computer_use", "summary": "Computer control", "tags": ["computer"]},
    ]
    result = ToolSelectionOrchestrator().select("search docs", tools, selected_model_capabilities={"supports_tool_calling": True})
    selected = [item["tool_id"] for item in result["recommended_tools"]]
    assert "search_docs" in selected
    assert "computer_use" not in selected
