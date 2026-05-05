from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_stop_conditions_prevent_runtime_tick(monkeypatch, tmp_path):
    from domain.agent.agent_definition import AgentDefinition
    from domain.agent.agent_runtime import AgentRuntime
    from domain.agent.agent_store import AgentStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STORE_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_HISTORY_PATH", str(tmp_path / "runs.json"))
    AgentStore().upsert(AgentDefinition(agent_id="stopper", stop_conditions={"max_failures": 0}))

    result = AgentRuntime().tick("stopper", message="should not run")

    assert result["status"] == "failed"
    assert result["run"]["blocked_reason"] == "max_failures"
