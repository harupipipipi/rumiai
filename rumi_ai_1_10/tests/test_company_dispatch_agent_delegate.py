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
    assert result["run_links"][0]["run_id"] == "run_123"
    assert runtime_store.list_run_links(company["id"], task_id=task["task_id"])[0]["agent_id"] == "coding_engineer"
