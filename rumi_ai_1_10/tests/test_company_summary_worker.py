from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_scribe_summarizes_thread_task_run_and_company_scopes(tmp_path):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.summary_worker import CompanySummaryWorker

    runtime_store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    run_store = AgentRunStore(tmp_path / "agent_runtime.db")
    message = runtime_store.add_message("acme", sender_id="user", content="@coding_engineer fix this")
    task = runtime_store.create_task(
        "acme",
        title="Fix this",
        target_agent_ids=["coding_engineer"],
        thread_id=message["thread_id"],
        message_id=message["message_id"],
        metadata={"changed_files": ["app.py"], "decisions": ["Patch the bug"]},
    )
    run_store.upsert_run(AgentRun(run_id="run_1", session_key="s", task="work", status="completed", agent_id="coding_engineer"))
    runtime_store.record_agent_run("acme", agent_id="coding_engineer", run_id="run_1", task_id=task["task_id"], thread_id=message["thread_id"])
    worker = CompanySummaryWorker(runtime_store=runtime_store, run_store=run_store)

    thread_summary = worker.summarize_scope("acme", "thread", message["thread_id"])
    task_summary = worker.summarize_scope("acme", "task", task["task_id"])
    run_summary = worker.summarize_scope("acme", "run", "run_1")
    company_summary = worker.summarize_scope("acme", "company", "acme")

    assert "1 message" in thread_summary["summary"]
    assert "Fix this" in task_summary["summary"]
    assert "status=completed" in run_summary["summary"]
    assert "messages=1" in company_summary["summary"]
    assert thread_summary["generated_by"] == "scribe"
    packet = task_summary["metadata"]["packet"]
    assert {
        "decisions",
        "blockers",
        "owners",
        "approvals_needed",
        "changed_files",
        "next_actions",
        "source_message_ids",
        "source_run_ids",
    } <= set(packet)
    assert packet["owners"] == ["coding_engineer"]
    assert packet["changed_files"] == ["app.py"]
    assert packet["source_message_ids"] == [message["message_id"]]
    assert packet["source_run_ids"] == ["run_1"]
    assert runtime_store.get_summary("acme", "thread", message["thread_id"])["dirty"] is False


def test_summary_block_lists_and_refreshes_company_summaries(tmp_path, monkeypatch):
    from blocks.company.summary import run
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None
    store = CompanyRuntimeStore()
    message = store.add_message("acme", sender_id="user", content="Summarize me")

    refreshed = run({"company_id": "acme", "action": "refresh", "scope_type": "thread", "scope_id": message["thread_id"]}, {})
    listed = run({"company_id": "acme", "action": "list"}, {})

    assert refreshed["status"] == "ok"
    assert listed["status"] == "ok"
    assert listed["data"]["total"] == 1
