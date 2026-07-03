from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_agent_studio_state() -> None:
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.chat.store import ChatStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    AgentRunStore._instance = None
    ChatStore._instance = None
    CompanyRuntimeStore._instance = None
    CompanyStore._instance = None


def test_agent_studio_profile_activation_enforces_human_only_and_review_gate(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    service = AgentStudioService()

    result = service.activate_profile_for_conversation(conversation["id"], "builtin.coding")
    updated = result["conversation"]

    assert updated["metadata"]["agent_profile_id"] == "builtin.coding"
    assert updated["metadata"]["agent_studio"]["surface"] == "mode_agent"
    assert updated["metadata"]["agent_studio"]["active_profile_id"] == "builtin.coding"
    assert updated["metadata"]["agent_studio"]["review_gate"]["approved"] is False

    yolo_guard = service.command_guard("yolo", conversation_id=conversation["id"])
    commit_guard = service.command_guard("commit", conversation_id=conversation["id"])

    assert yolo_guard["allowed"] is False
    assert yolo_guard["code"] == "HUMAN_ONLY_COMMAND"
    assert commit_guard["allowed"] is False
    assert commit_guard["code"] == "REVIEW_GATE_BLOCKED"

    service.mark_review_gate_for_conversation(conversation["id"], approved=True, approved_by="test-reviewer")
    approved_commit_guard = service.command_guard("commit", conversation_id=conversation["id"])

    assert approved_commit_guard["allowed"] is True
    assert approved_commit_guard.get("warning") in {None, ""}


def test_agent_studio_team_and_fusion_activation_materialize_workroom_members(tmp_path, monkeypatch):
    from domain.agent_studio.service import AgentStudioService
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_STUDIO_PATH", str(tmp_path / "agent_studio.json"))
    _reset_agent_studio_state()

    store = ChatStore()
    team_conversation = store.create_conversation(model="stub/default")
    fusion_conversation = store.create_conversation(model="stub/default")
    service = AgentStudioService()

    team_result = service.activate_team_for_conversation(team_conversation["id"], "builtin.delivery_team")
    fusion_result = service.activate_fusion_for_conversation(fusion_conversation["id"], "builtin.delivery_fusion")

    team_company = team_result["company"]
    fusion_company = fusion_result["company"]

    assert team_result["conversation"]["metadata"]["agent_studio"]["surface"] == "team_agent"
    assert team_result["conversation"]["metadata"]["team_id"] == "builtin.delivery_team"
    assert team_company["metadata"]["team_id"] == "builtin.delivery_team"
    assert {"builtin_coding", "builtin_research", "builtin_review"}.issubset(team_company["agents"].keys())

    assert fusion_result["conversation"]["metadata"]["agent_studio"]["surface"] == "fusion_agent"
    assert fusion_result["conversation"]["metadata"]["fusion_id"] == "builtin.delivery_fusion"
    assert fusion_company["metadata"]["fusion_id"] == "builtin.delivery_fusion"
    assert {"builtin_coding", "builtin_research", "builtin_review"}.issubset(fusion_company["agents"].keys())
