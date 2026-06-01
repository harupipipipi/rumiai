from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_mention_to_active_run_routes_as_runtime_instruction(monkeypatch, tmp_path):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.service import CompanyService
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None

    captured = {}

    def fake_instruction(envelope, context):
        captured["action_id"] = envelope.delivery["action_id"]
        captured["target"] = dict(envelope.target)
        captured["input"] = envelope.input
        return {"status": "ok", "instruction_id": "inst_1", "execution_id": envelope.target["execution_id"]}

    monkeypatch.setattr("domain.company.message_router.dispatch_input", fake_instruction)
    company = CompanyService().bootstrap_default_company()
    AgentRunStore().upsert_run(
        AgentRun(
            run_id="run_active",
            session_key="agent:coding_engineer:main",
            task="work",
            status="running",
            agent_id="coding_engineer",
            execution_json={
                "execution_id": "run_active",
                "task": "work",
                "status": "running",
                "context": {"agent_id": "coding_engineer"},
                "messages": [],
            },
        )
    )
    CompanyRuntimeStore().record_agent_run(company["id"], agent_id="coding_engineer", run_id="run_active", status="running")

    result = CompanyService().mention(company["id"], {"content": "@coding_engineer change course", "sender_id": "user"})

    assert result["task"] is None
    assert result["routes"][0]["route"] == "run.instruction"
    assert captured["action_id"] == "run.instruction"
    assert captured["target"]["execution_id"] == "run_active"
    assert captured["input"] == "@coding_engineer change course"
    inbox = CompanyRuntimeStore().list_inbox(company["id"], agent_id="coding_engineer", kind="mention")
    assert inbox[0]["status"] == "delivered"


def test_mention_instruction_failure_marks_inbox_failed_and_notifies_manager(monkeypatch, tmp_path):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.service import CompanyService
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None

    def failing_instruction(envelope, context):
        return {"status": "error", "error": "queue unavailable", "execution_id": envelope.target["execution_id"]}

    monkeypatch.setattr("domain.company.message_router.dispatch_input", failing_instruction)
    company = CompanyService().bootstrap_default_company()
    AgentRunStore().upsert_run(
        AgentRun(
            run_id="run_active",
            session_key="agent:coding_engineer:main",
            task="work",
            status="running",
            agent_id="coding_engineer",
            execution_json={"execution_id": "run_active", "status": "running", "context": {"agent_id": "coding_engineer"}},
        )
    )
    CompanyRuntimeStore().record_agent_run(company["id"], agent_id="coding_engineer", run_id="run_active", status="running")

    result = CompanyService().mention(company["id"], {"content": "@coding_engineer change course", "sender_id": "user"})
    mention_inbox = CompanyRuntimeStore().list_inbox(company["id"], agent_id="coding_engineer", kind="mention")
    manager_inbox = CompanyRuntimeStore().list_inbox(company["id"], agent_id="operations_manager", kind="instruction_failure")

    assert result["routes"][0]["route"] == "run.instruction"
    assert result["routes"][0]["status"] == "error"
    assert mention_inbox[0]["status"] == "failed"
    assert manager_inbox[0]["priority"] == "high"
