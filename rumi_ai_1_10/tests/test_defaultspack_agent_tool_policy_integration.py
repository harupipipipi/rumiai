from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_agent_runtime_resolves_tool_policy_with_deny_precedence(monkeypatch, tmp_path):
    from domain.agent.agent_definition import AgentDefinition
    from domain.agent.agent_runtime import AgentRuntime
    from domain.agent.agent_store import AgentStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STORE_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_HISTORY_PATH", str(tmp_path / "runs.json"))
    AgentStore().upsert(
        AgentDefinition(
            agent_id="policy-agent",
            tool_policy={"allowlist": ["todo", "coding_file_write"], "denylist": ["coding_file_write"]},
        )
    )

    result = AgentRuntime().tick("policy-agent", tool_policy={"allowed_tools": ["browser_use"]})

    assert result["status"] == "completed"
    assert "coding_file_write" not in result["run"]["policy"]["tool_allowlist"]
    assert "coding_file_write" in result["run"]["policy"]["tool_denylist"]
