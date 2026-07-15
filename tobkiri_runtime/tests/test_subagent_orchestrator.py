from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_tool_selector_subagent_returns_structured_output():
    from domain.agent.subagent_orchestrator import run_subagent

    result = run_subagent(
        "tool_selector",
        {"candidate_tools": [{"tool_id": "search_docs", "summary": "Search docs"}]},
    )

    assert result["role_id"] == "tool_selector"
    assert result["output"]["recommended_tools"][0]["tool_id"] == "search_docs"


def test_no_computer_use_subagent_role():
    from domain.agent.subagent_roles import list_subagent_roles

    roles = list_subagent_roles()
    assert "computer_use" not in roles
    assert "browser_computer" not in roles
