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
    runtime_store.record_agent_run("acme", agent_id="coding_engineer", run_id="run_stale", task_id=task["task_id"], status="running")
    runtime_store.record_agent_run("acme", agent_id="reviewer", run_id="run_wait", status="waiting_approval")
    runtime_store.record_agent_run("acme", agent_id="reviewer", run_id="run_failed", status="failed")

    result = CompanySupervisor(runtime_store=runtime_store, run_store=run_store).tick("acme", stale_after_seconds=1)
    action_types = {action["type"] for action in result["actions"]}

    assert task["task_id"] in {item["task_id"] for item in result["open_tasks"]}
    assert {"open_task", "unassigned_mention", "stale_run", "waiting_approval", "failed_run", "dirty_summary"} <= action_types
    assert runtime_store.list_inbox("acme", agent_id="operations_manager", kind="supervisor_tick")


def test_supervisor_tick_filters_runs_to_company_scope(tmp_path):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.supervisor import CompanySupervisor

    runtime_store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    run_store = AgentRunStore(tmp_path / "agent_runtime.db")
    run_store.upsert_run(
        AgentRun(run_id="run_a", session_key="s", task="a", status="running", agent_id="coding_engineer", heartbeat_at="2000-01-01T00:00:00Z")
    )
    run_store.upsert_run(
        AgentRun(run_id="run_b", session_key="s", task="b", status="running", agent_id="coding_engineer", heartbeat_at="2000-01-01T00:00:00Z")
    )
    runtime_store.record_agent_run("company_a", agent_id="coding_engineer", run_id="run_a", status="running")
    runtime_store.record_agent_run("company_b", agent_id="coding_engineer", run_id="run_b", status="running")

    result = CompanySupervisor(runtime_store=runtime_store, run_store=run_store).tick("company_a", stale_after_seconds=1)

    assert [run["run_id"] for run in result["stale_runs"]] == ["run_a"]
    assert all(action.get("run_id") != "run_b" for action in result["actions"])


def test_supervisor_observe_only_and_action_mode(tmp_path):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.supervisor import CompanySupervisor

    runtime_store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    run_store = AgentRunStore(tmp_path / "agent_runtime.db")
    queued_task = runtime_store.create_task("acme", title="Dispatch me", target_agent_ids=["coding_engineer"])
    stale_task = runtime_store.create_task("acme", title="Stale work", target_agent_ids=["coding_engineer"], status="running")
    runtime_store.mark_summary_dirty("acme", "thread", "thread_dirty")
    run_store.upsert_run(
        AgentRun(run_id="run_stale", session_key="s", task="old", status="running", agent_id="coding_engineer", heartbeat_at="2000-01-01T00:00:00Z")
    )
    runtime_store.record_agent_run("acme", agent_id="coding_engineer", run_id="run_stale", task_id=stale_task["task_id"], status="running")
    dispatch_calls = []

    class FakeDispatcher:
        def dispatch_task(self, company_id, task_id, **kwargs):
            dispatch_calls.append((company_id, task_id, kwargs))
            runtime_store.update_task(task_id, {"status": "running"}, company_id=company_id)
            return {"dispatch": {"status": "running"}}

    supervisor = CompanySupervisor(runtime_store=runtime_store, run_store=run_store, run_dispatcher=FakeDispatcher())
    observed = supervisor.tick("acme", stale_after_seconds=1)

    assert observed["performed_actions"] == []
    assert runtime_store.get_task(queued_task["task_id"], company_id="acme")["status"] == "queued"
    assert runtime_store.get_task(stale_task["task_id"], company_id="acme")["status"] == "running"
    assert runtime_store.get_summary("acme", "thread", "thread_dirty")["dirty"] is True

    acted = supervisor.tick("acme", stale_after_seconds=1, auto_dispatch=True, auto_summarize=True, auto_mark_stale=True)
    performed_types = {action["type"] for action in acted["performed_actions"]}

    assert "dispatch_task" in performed_types
    assert "summarize" in performed_types
    assert "mark_stale_run" in performed_types
    assert dispatch_calls[0][1] == queued_task["task_id"]
    assert runtime_store.get_task(queued_task["task_id"], company_id="acme")["status"] == "running"
    assert runtime_store.get_task(stale_task["task_id"], company_id="acme")["status"] == "stale"
    assert run_store.get_run("run_stale")["status"] == "stale"
    assert runtime_store.get_summary("acme", "thread", "thread_dirty")["dirty"] is False
    assert runtime_store.list_inbox("acme", agent_id="operations_manager", kind="stale_run")


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
