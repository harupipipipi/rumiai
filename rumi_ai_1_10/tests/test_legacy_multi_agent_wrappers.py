from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_legacy_multi_wrappers_route_to_company_slack_runtime(monkeypatch, tmp_path):
    from blocks.agent import multi_execute, multi_message, multi_status
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None

    def fake_dispatch(envelope, context):
        return {
            "status": "ok",
            "delegate": {"execution_id": "run_" + envelope.target["agent_id"], "status": "running"},
            "result": {"status": "running"},
        }

    monkeypatch.setattr("domain.company.run_dispatcher.dispatch_input", fake_dispatch)

    started = multi_execute.run(
        {
            "task": "Build the thing",
            "agents": [{"name": "Coding Engineer", "role": "coding_engineer", "tools": ["coding_file_read"]}],
        },
        {},
    )
    session_id = started["data"]["session_id"]
    posted = multi_message.run({"session_id": session_id, "message": "@coding_engineer add tests", "target_agent": "Coding Engineer"}, {})
    status = multi_status.run({"session_id": session_id}, {})

    assert started["status"] == "ok"
    assert "compatibility wrapper" in started["data"]["deprecation_warning"]
    assert posted["data"]["status"] == "routed"
    assert status["data"]["runtime"] == "CompanySlackRuntime"
    assert status["data"]["task_total"] >= 1


def test_multi_orchestrator_is_legacy_only_and_wrappers_do_not_import_it():
    import domain.agent.multi as legacy_multi

    execute_source = (DEFAULTSPACK_ROOT / "blocks" / "agent" / "multi_execute.py").read_text(encoding="utf-8")
    message_source = (DEFAULTSPACK_ROOT / "blocks" / "agent" / "multi_message.py").read_text(encoding="utf-8")

    assert legacy_multi.LEGACY_ONLY is True
    assert "MultiAgentOrchestrator" not in execute_source
    assert "MultiAgentOrchestrator" not in message_source
    assert "round_robin" not in execute_source
