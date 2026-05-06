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


def test_agent_store_maps_webhook_and_nonstop_frontend_settings(monkeypatch, tmp_path):
    from domain.agent.agent_store import AgentStore

    _agent_env(monkeypatch, tmp_path)
    store = AgentStore()
    agent = store.create_agent(
        {
            "name": "Webhook Agent",
            "profile_id": "defaultspack.local_agent",
            "role": "React to webhook actions",
            "tools": ["wait", "todo"],
            "schedule": {"enabled": True, "mode": "webhook", "interval_minutes": 5},
            "lifecycle": {"run_mode": "webhook", "max_cost_usd": 3},
            "webhook": {
                "enabled": True,
                "url_mode": "custom",
                "custom_webhook_url": "https://hooks.example.com/rumi",
                "secret": "secret",
            },
        }
    )

    assert agent["display_name"] == "Webhook Agent"
    assert agent["runtime_policy"]["activation_mode"] == "webhook"
    assert agent["runtime_policy"]["can_run_24_7"] is True
    assert agent["schedule_policy"]["type"] == "webhook"
    assert agent["webhook_policy"]["custom_webhook_url"] == "https://hooks.example.com/rumi"
    assert agent["tool_policy"]["allowlist"] == ["wait", "todo"]


def test_wait_tool_supports_hour_durations_without_sleeping():
    from domain.tool.executor import ToolExecutor

    result = ToolExecutor().execute("wait", {"duration": "2h", "dry_run": True}, {})

    assert result["is_error"] is False
    assert '"seconds": 7200.0' in result["result"] or "7200" in result["result"]


def test_wait_tool_invoke_is_allowed_by_safe_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_TOOL_PERMISSION_POLICY_PATH", str(tmp_path / "permission.json"))
    from blocks.tool.invoke import run

    result = run({"tool_name": "wait", "arguments": {"duration": "1m", "dry_run": True}}, {})

    assert result["status"] == "ok"
    assert result["data"]["permission"]["allowed"] is True
