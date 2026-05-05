from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_blocker_store_blocks_runtime_tick(monkeypatch, tmp_path):
    from domain.agent.agent_definition import AgentDefinition
    from domain.agent.agent_runtime import AgentRuntime
    from domain.agent.agent_store import AgentStore
    from domain.agent.blocker import BlockerStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STORE_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_HISTORY_PATH", str(tmp_path / "runs.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_BLOCKERS_PATH", str(tmp_path / "blockers.json"))
    AgentStore().upsert(AgentDefinition(agent_id="blocked"))
    BlockerStore().add("blocked", "needs login", severity="high")

    result = AgentRuntime().tick("blocked")

    assert result["status"] == "blocked"
    assert result["run"]["result"]["requires_user_action"] is True
