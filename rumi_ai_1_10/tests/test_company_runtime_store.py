from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_company_runtime_store_persists_slack_runtime_tables(tmp_path):
    from domain.company.runtime_store import CompanyRuntimeStore

    store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    message = store.add_message(
        "acme",
        channel_id="engineering",
        sender_id="user",
        content="@coding_engineer fix this",
        mentions=["coding_engineer"],
    )
    task = store.create_task(
        "acme",
        title="Fix this",
        description="Do the work",
        target_agent_ids=["coding_engineer"],
        source="mention",
        channel_id="engineering",
        thread_id=message["thread_id"],
        message_id=message["message_id"],
    )
    link = store.record_agent_run(
        "acme",
        agent_id="coding_engineer",
        run_id="run_1",
        task_id=task["task_id"],
        thread_id=message["thread_id"],
        message_id=message["message_id"],
    )
    inbox = store.add_inbox_item(
        "acme",
        agent_id="operations_manager",
        kind="manager_tick",
        content="watch this",
        task_id=task["task_id"],
    )
    summary = store.upsert_summary(
        "acme",
        scope_type="thread",
        scope_id=message["thread_id"],
        summary="Thread summary",
        generated_by="scribe",
    )

    messages, message_total = store.list_messages("acme", channel_id="engineering")
    tasks, task_total = store.list_tasks("acme", target_agent_id="coding_engineer")
    summaries, summary_total = store.list_summaries("acme")

    assert message_total == 1
    assert task_total == 1
    assert summary_total == 3
    assert messages[0]["mentions"] == ["coding_engineer"]
    assert tasks[0]["target_agent_ids"] == ["coding_engineer"]
    assert {item["scope_type"] for item in summaries} == {"thread", "task", "run"}
    assert link["run_id"] == "run_1"
    assert inbox["agent_id"] == "operations_manager"
    assert summary["dirty"] is False
    assert store.stats("acme") == {
        "threads": 1,
        "messages": 1,
        "tasks": 1,
        "runs": 1,
        "inbox": 1,
        "summaries": 3,
    }


def test_task_assignment_index_tracks_create_and_update(tmp_path):
    from domain.company.runtime_store import CompanyRuntimeStore

    store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    task = store.create_task("acme", title="Indexed", target_agent_ids=["coding_engineer"])

    rows = store.conn.execute("SELECT agent_id FROM company_task_assignments WHERE task_id = ?", (task["task_id"],)).fetchall()
    assert [row["agent_id"] for row in rows] == ["coding_engineer"]
    tasks, total = store.list_tasks("acme", target_agent_id="coding_engineer")
    assert total == 1
    assert tasks[0]["task_id"] == task["task_id"]

    store.update_task(task["task_id"], {"target_agent_ids": ["scribe"]}, company_id="acme")
    old_tasks, old_total = store.list_tasks("acme", target_agent_id="coding_engineer")
    new_tasks, new_total = store.list_tasks("acme", target_agent_id="scribe")

    assert old_tasks == []
    assert old_total == 0
    assert new_total == 1
    assert new_tasks[0]["target_agent_ids"] == ["scribe"]


def test_find_active_run_marks_missing_and_terminal_links_inactive(tmp_path, monkeypatch):
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    AgentRunStore._instance = None
    store = CompanyRuntimeStore(tmp_path / "company_runtime.db")
    run_store = AgentRunStore()

    missing = store.record_agent_run("acme", agent_id="coding_engineer", run_id="run_missing", status="running")
    assert store.find_active_run_for_agent("acme", "coding_engineer") is None
    assert store.get_run_link(missing["link_id"])["status"] == "missing"

    terminal = store.record_agent_run("acme", agent_id="coding_engineer", run_id="run_done", status="running")
    run_store.upsert_run(AgentRun(run_id="run_done", session_key="s", task="done", status="completed", agent_id="coding_engineer"))

    assert store.find_active_run_for_agent("acme", "coding_engineer") is None
    assert store.get_run_link(terminal["link_id"])["status"] == "completed"
