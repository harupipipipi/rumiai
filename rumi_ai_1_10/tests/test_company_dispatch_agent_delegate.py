from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_dispatch_task_uses_agent_delegate_and_records_run_link(monkeypatch, tmp_path):
    from domain.company.run_dispatcher import CompanyRunDispatcher
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.service import CompanyService
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None

    company = CompanyService().bootstrap_default_company()
    runtime_store = CompanyRuntimeStore()
    task = runtime_store.create_task(
        company["id"],
        title="Fix bug",
        description="Patch the failing code",
        target_agent_ids=["coding_engineer"],
    )
    seen = {}

    def fake_dispatch(envelope, context):
        seen["action_id"] = envelope.delivery["action_id"]
        seen["task"] = envelope.params["task"]
        seen["tools"] = envelope.tools
        seen["profile_policy"] = context["profile_policy"]
        return {"status": "ok", "delegate": {"execution_id": "run_123", "status": "running"}, "result": {"status": "running"}}

    result = CompanyRunDispatcher(runtime_store=runtime_store, dispatcher=fake_dispatch).dispatch_task(
        company["id"],
        task["task_id"],
        requested_by="operations_manager",
        policy={"write_actions_require_approval": True},
    )

    assert seen["action_id"] == "agent.delegate"
    assert "Fix bug" in seen["task"]
    assert "coding_file_read" in seen["tools"]
    assert seen["profile_policy"]["direct_tool_execution"] is False
    assert result["task"]["status"] == "running"
    assert result["run_links"][0]["run_id"] == "run_123"
    assert runtime_store.list_run_links(company["id"], task_id=task["task_id"])[0]["agent_id"] == "coding_engineer"


def test_task_status_from_running_and_completed_delegate_results():
    from domain.company.run_dispatcher import _task_status_from_results

    assert (
        _task_status_from_results(
            [{"status": "ok", "delegate": {"execution_id": "run_1", "status": "running"}, "result": {"status": "running"}}]
        )
        == "running"
    )
    assert (
        _task_status_from_results(
            [{"status": "ok", "delegate": {"execution_id": "run_2", "status": "completed"}, "result": {"status": "completed"}}]
        )
        == "completed"
    )


def test_task_prompt_frames_employee_delegation_from_president_chat():
    from domain.company.run_dispatcher import _task_prompt

    prompt = _task_prompt(
        {"id": "chat-team", "name": "Executive Team"},
        {
            "title": "Research the latest local-first agent patterns",
            "description": "Use the provided sources and report uncertainty.",
            "metadata": {
                "conversation_id": "chat-main-1",
                "source_message": "Deepresearch local-first agent patterns.",
            },
        },
        {"agent_id": "research_specialist", "display_name": "Research Specialist"},
    )

    assert "president in the main Rumi chat" in prompt
    assert "does not perform specialist work directly" in prompt
    assert "Parent chat id: chat-main-1" in prompt
    assert "Original president request" in prompt
    assert "Company Workspace UI" not in prompt


def test_dispatch_prunes_tools_for_non_tool_calling_agent_model(monkeypatch, tmp_path):
    from domain.company.run_dispatcher import CompanyRunDispatcher
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.service import CompanyService
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None

    company = CompanyService().bootstrap_default_company()
    CompanyStore().upsert_agent(
        company["id"],
        {
            "agent_id": "minimax_worker",
            "display_name": "MiniMax Worker",
            "model": "opencode-zen/minimax-m3-free",
            "allowed_tools": ["coding_file_read", "coding_git_diff"],
        },
    )
    runtime_store = CompanyRuntimeStore()
    task = runtime_store.create_task(
        company["id"],
        title="Summarize the task",
        target_agent_ids=["minimax_worker"],
    )
    seen = {}

    def fake_dispatch(envelope, context):
        seen["model"] = envelope.params["model"]
        seen["tools"] = envelope.tools
        return {"status": "ok", "delegate": {"execution_id": "run_456", "status": "completed"}, "result": {"status": "completed"}}

    result = CompanyRunDispatcher(runtime_store=runtime_store, dispatcher=fake_dispatch).dispatch_task(
        company["id"],
        task["task_id"],
    )

    assert seen["model"] == "opencode-zen/minimax-m3-free"
    assert seen["tools"] == []
    assert result["task"]["status"] == "completed"


def test_dispatch_persists_unconfigured_agent_model_error(monkeypatch, tmp_path):
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.run_dispatcher import CompanyRunDispatcher
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.service import CompanyService
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    AgentRunStore._instance = None
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None

    company = CompanyService().bootstrap_default_company()
    CompanyStore().upsert_agent(
        company["id"],
        {
            "agent_id": "stub_worker",
            "display_name": "Stub Worker",
            "model": "stub/default",
            "allowed_tools": [],
        },
    )
    runtime_store = CompanyRuntimeStore()
    task = runtime_store.create_task(
        company["id"],
        title="Show fallback model state",
        target_agent_ids=["stub_worker"],
    )

    result = CompanyRunDispatcher(runtime_store=runtime_store).dispatch_task(company["id"], task["task_id"])

    assert result["task"]["status"] == "blocked"
    assert result["run_links"][0]["status"] == "error"
    run = AgentRunStore().get_run(result["run_links"][0]["run_id"])
    assert run["status"] == "error"
    assert "provider is not configured" in run["error"]
