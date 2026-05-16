from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_coding_cockpit_functions_are_registered_in_manifest_factory():
    from domain.function_runtime.manifest_factory import FUNCTION_SPECS_BY_ID

    required = {
        "coding_approval_list",
        "coding_approval_approve",
        "coding_approval_deny",
        "coding_github_pr_read",
        "coding_github_issue_read",
        "coding_github_ci_status",
        "tool_mcp_registry",
        "browser_artifacts",
        "coding_agent_session_create",
        "coding_agent_session_status",
        "coding_agent_session_merge_report",
    }

    assert required <= set(FUNCTION_SPECS_BY_ID)
    assert FUNCTION_SPECS_BY_ID["coding_github_pr_read"].risk == "medium"
    assert FUNCTION_SPECS_BY_ID["coding_agent_session_create"].block_module == "blocks.agent.coding_session_create"


def test_coding_agent_session_create_status_and_merge_report_are_visible():
    from blocks.agent.coding_session_create import run as create_session
    from blocks.agent.coding_session_merge_report import run as merge_report
    from blocks.agent.coding_session_status import run as session_status

    created = create_session(
        {
            "task": "Inspect cockpit",
            "agents": [{"name": "worker", "role": "coding worker", "model": "stub/default", "tools": []}],
            "worktree_mode": "metadata_only",
        },
        {},
    )

    assert created["status"] == "ok"
    session_id = created["data"]["session_id"]
    assert created["data"]["session"]["status"] == "created"
    assert created["data"]["session"]["shared_context"]["workspace"]["merge_strategy"] == "manual_conflict_report"

    status = session_status({"session_id": session_id}, {})
    report = merge_report({"session_id": session_id}, {})

    assert status["status"] == "ok"
    assert status["data"]["session_id"] == session_id
    assert report["status"] == "ok"
    assert report["data"]["merge_report"]["merge_strategy"] == "manual_conflict_report"
