from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_defaultspack_singletons():
    from domain.agent.org_manager import OrgManager
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore
    from domain.tool.registry import ToolRegistry

    scheduler = Scheduler._instance
    if scheduler is not None:
        for schedule_id in list(getattr(scheduler, "_timers", {}).keys()):
            scheduler._cancel_timer(schedule_id)
    Scheduler._instance = None
    OrgManager._instance = None
    ChatStore._instance = None
    ToolRegistry._instance = None


def test_operations_company_profile_coexists_with_default_profile():
    from domain.capability.catalog import CapabilityCatalog

    manifest = CapabilityCatalog(DEFAULTSPACK_ROOT).manifest()
    profile_ids = {profile["profile_id"] for profile in manifest["profiles"]}

    assert "defaultspack.local_agent" in profile_ids
    assert "defaultspack.operations_company" in profile_ids
    assert manifest["counts"]["profiles"] >= 2


def test_operations_company_bootstrap_creates_org_conversation_and_heartbeat(tmp_path, monkeypatch):
    from domain.agent.operations_company import OperationsCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", str(tmp_path / "ops" / "state.json"))

    status = OperationsCompanyRuntime().bootstrap(start_nonstop=True, heartbeat_minutes=30, model="stub/default")

    assert status["bootstrapped"] is True
    assert status["org"]["member_count"] == 7
    assert status["conversation_id"]
    conversation = ChatStore().get_conversation(status["conversation_id"])
    assert conversation["conversation_kind"] == "operations_company"
    assert conversation["agent_id"] == "client_manager"
    assert conversation["metadata"]["profile_id"] == "defaultspack.operations_company"

    heartbeat = status["schedules"][0]
    assert heartbeat["task"]["profile_id"] == "defaultspack.operations_company"
    assert heartbeat["task"]["agent_id"] == "operations_monitor"
    assert heartbeat["task"]["conversation_id"] == status["conversation_id"]
    assert "rumi_api" in heartbeat["task"]["tool_policy"]["tool_allowlist"]

    Scheduler().delete_schedule(heartbeat["id"])
    _reset_defaultspack_singletons()


def test_operations_conversation_resolves_pack_system_prompt():
    from blocks.chat.send import _conversation_system_prompt
    from domain.prompt.manager import get_manager

    prompt = _conversation_system_prompt({"system_prompt_id": "operations_company"}, get_manager())

    assert "Rumi Operations Company" in prompt
    assert "Client Manager" in prompt


def test_operations_heartbeat_trigger_persists_into_single_client_conversation(tmp_path, monkeypatch):
    from domain.agent.operations_company import OperationsCompanyRuntime
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", str(tmp_path / "ops" / "state.json"))

    status = OperationsCompanyRuntime().bootstrap(start_nonstop=True, heartbeat_minutes=30, model="stub/default")
    conversation_id = status["conversation_id"]
    schedule_id = status["schedules"][0]["id"]

    result = Scheduler().trigger_now(schedule_id)

    assert result["status"] == "completed"
    conversation = ChatStore().get_conversation(conversation_id)
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant"]
    assert conversation["messages"][0]["metadata"]["source"] == "scheduler"
    assert conversation["messages"][0]["metadata"]["profile_id"] == "defaultspack.operations_company"

    persisted = json.loads((tmp_path / "chat" / "conversations.json").read_text(encoding="utf-8"))
    assert persisted["conversations"][conversation_id]["messages"][0]["metadata"]["schedule_id"] == schedule_id

    Scheduler().delete_schedule(schedule_id)
    _reset_defaultspack_singletons()


def test_rumi_api_tool_lists_routes_and_requires_mutation_approval():
    from domain.tool.rumi_api import run

    listed = run({"action": "list_routes"}, {})
    mutation = run(
        {
            "action": "request",
            "method": "POST",
            "path": "/api/agent/company/bootstrap",
            "body": {"start_nonstop": True},
            "allow_mutation": True,
        },
        {"profile_policy": {"yolo_mode": False}},
    )

    assert listed["status"] == "ok"
    assert any(route["path"] == "/api/agent/company/status" for route in listed["data"]["routes"])
    assert mutation["status"] == "ok"
    assert mutation["data"]["approval_required"] is True
