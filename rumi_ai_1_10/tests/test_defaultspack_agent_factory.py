from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _agent_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STORE_PATH", str(tmp_path / "agents.json"))


def test_agent_store_crud_and_templates(monkeypatch, tmp_path):
    from domain.agent.agent_definition import AgentDefinition
    from domain.agent.agent_store import AgentStore
    from domain.agent.agent_templates import AgentTemplates
    from domain.agent.operations_company import ROLE_DEFINITIONS

    _agent_env(monkeypatch, tmp_path)
    store = AgentStore()
    agent = store.create(
        AgentDefinition(
            agent_id="agent-1",
            display_name="Writer",
            profile_id="defaultspack.local_agent",
            tool_policy={"allowlist": ["todo"]},
        )
    )
    assert agent["agent_id"] == "agent-1"
    assert store.get("agent-1")["display_name"] == "Writer"

    updated = store.update("agent-1", {"display_name": "Editor"})
    assert updated["display_name"] == "Editor"
    assert len(store.list()) == 1
    assert store.delete("agent-1") is True
    assert store.get("agent-1") is None

    templated = AgentTemplates.from_role_definition(ROLE_DEFINITIONS[0]).to_dict()
    assert templated["agent_id"] == "client_manager"
    assert "rumi_api" in templated["tool_policy"]["allowlist"]
