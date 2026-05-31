from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_supervisor_tick_surfaces_open_stale_blocked_and_summary_work(tmp_path):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.supervisor import CompanySupervisor

    runtime_store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    run_store = AgentRunStore(tmp_path / "agent_runtime.db")
    task = runtime_store.create_task("acme", title="Open task", target_agent_ids=["coding_engineer"])
    runtime_store.add_inbox_item("acme", agent_id="operations_manager", kind="unassigned_mention", content="@unknown", priority="high")
    runtime_store.mark_summary_dirty("acme", "thread", "thread_1")
    run_store.upsert_run(
        AgentRun(
            run_id="run_stale",
            session_key="s",
            task="old",
            status="running",
            agent_id="coding_engineer",
            heartbeat_at="2000-01-01T00:00:00Z",
        )
    )
    run_store.upsert_run(AgentRun(run_id="run_wait", session_key="s", task="approval", status="waiting_approval", agent_id="reviewer"))
    run_store.upsert_run(AgentRun(run_id="run_failed", session_key="s", task="failed", status="failed", agent_id="reviewer", error="boom"))

    result = CompanySupervisor(runtime_store=runtime_store, run_store=run_store).tick("acme", stale_after_seconds=1)
    action_types = {action["type"] for action in result["actions"]}

    assert task["task_id"] in {item["task_id"] for item in result["open_tasks"]}
    assert {"open_task", "unassigned_mention", "stale_run", "waiting_approval", "failed_run", "dirty_summary"} <= action_types
    assert runtime_store.list_inbox("acme", agent_id="operations_manager", kind="supervisor_tick")


def test_supervisor_tick_block_uses_company_slack_runtime_store(tmp_path, monkeypatch):
    from blocks.company.supervisor_tick import run
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None
    runtime_store = CompanyRuntimeStore()
    task = runtime_store.create_task("acme", title="Open task", target_agent_ids=["coding_engineer"])

    result = run({"company_id": "acme"}, {})

    assert result["status"] == "ok"
    assert task["task_id"] in {item["task_id"] for item in result["data"]["open_tasks"]}
