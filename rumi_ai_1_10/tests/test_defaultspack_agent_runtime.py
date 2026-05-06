from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _runtime_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STORE_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUN_HISTORY_PATH", str(tmp_path / "runs.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_BLOCKERS_PATH", str(tmp_path / "blockers.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_API_KEYS_PATH", str(tmp_path / "api_keys.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))


def test_agent_runtime_tick_records_run_and_uses_conversation(monkeypatch, tmp_path):
    from domain.agent.agent_definition import AgentDefinition
    from domain.agent.agent_runtime import AgentRuntime
    from domain.agent.agent_store import AgentStore
    from domain.chat.store import ChatStore

    _runtime_env(monkeypatch, tmp_path)
    ChatStore._instance = None
    AgentStore().upsert(
        AgentDefinition(
            agent_id="runner",
            display_name="Runner",
            model_policy={"default_model": "stub/default", "allowed_models": ["stub/default"]},
            runtime_policy={"non_stop": True},
            tool_policy={"allowlist": ["todo"]},
        )
    )
    conversation = ChatStore().create_conversation(model="stub/default", agent_id="runner")

    result = AgentRuntime().tick("runner", message="hello", conversation_id=conversation["id"])

    assert result["status"] == "completed"
    assert result["state"]["run_count"] == 1
    stored = ChatStore().get_conversation(conversation["id"])
    assert stored["messages"][0]["metadata"]["source"] == "agent_runtime"
    assert stored["messages"][0]["metadata"]["runtime_source"] == "agent_runtime"
    assert AgentRuntime().runs("runner")["total"] >= 1


def test_operations_heartbeat_routes_through_agent_runtime(monkeypatch, tmp_path):
    from domain.agent.operations_company import OperationsCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _runtime_env(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", str(tmp_path / "ops" / "state.json"))
    ChatStore._instance = None
    Scheduler._instance = None

    status = OperationsCompanyRuntime().bootstrap(start_nonstop=True, heartbeat_minutes=30, model="stub/default")
    assert len(status["agents"]) == 7
    schedule = status["schedules"][0]
    assert schedule["task"]["metadata"]["runtime_handler"] == "agent_runtime.tick"

    history = Scheduler().trigger_now(schedule["id"])
    assert history["status"] == "completed"
    conversation = ChatStore().get_conversation(status["conversation_id"])
    assert conversation["agent_id"] == "client_manager"
    assert conversation["messages"][0]["metadata"]["runtime_source"] == "agent_runtime"


def test_agent_webhook_route_triggers_enabled_agent(monkeypatch, tmp_path):
    from blocks.agent.agents.webhook import run as webhook_run
    from domain.agent.agent_definition import AgentDefinition
    from domain.agent.agent_store import AgentStore

    _runtime_env(monkeypatch, tmp_path)
    AgentStore().upsert(
        AgentDefinition(
            agent_id="hooked",
            display_name="Hooked",
            schedule_policy={"type": "webhook", "enabled": True, "run_mode": "webhook"},
            webhook_policy={"enabled": True, "secret": "ok"},
        )
    )

    result = webhook_run(
        {
            "agent_id": "hooked",
            "action": "ping",
            "secret": "ok",
            "payload": {"message": "webhook hello"},
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["accepted"] is True
    assert result["data"]["result"]["run"]["trigger"] == "webhook"
