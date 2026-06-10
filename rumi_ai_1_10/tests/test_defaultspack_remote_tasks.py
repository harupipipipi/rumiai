from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture()
def remote_gateway_env(monkeypatch, tmp_path):
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.company.store import CompanyStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_RUNTIME_DB_PATH", str(tmp_path / "company_runtime.db"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_COMPANY_STORE_PATH", str(tmp_path / "companies.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None
    yield
    CompanyStore._instance = None
    CompanyRuntimeStore._instance = None
    AgentRunStore._instance = None


class FakeDispatcher:
    def __init__(self, runtime_store, run_store, *, status="running", approval=False):
        self.runtime_store = runtime_store
        self.run_store = run_store
        self.status = status
        self.approval = approval
        self.calls = []

    def dispatch_task(self, company_id, task_id, **kwargs):
        from domain.agent_runtime.models import AgentRun

        self.calls.append((company_id, task_id, kwargs))
        task = self.runtime_store.get_task(task_id, company_id=company_id)
        run_links = []
        results = []
        for index, agent_id in enumerate(task.get("target_agent_ids") or ["operations_manager"], start=1):
            run_id = f"run_remote_{index}"
            self.run_store.upsert_run(
                AgentRun(
                    run_id=run_id,
                    session_key="remote",
                    task=str(task.get("description") or task.get("title") or ""),
                    status=self.status,
                    agent_id=agent_id,
                    heartbeat_at="2000-01-01T00:00:00Z" if self.status == "stale" else None,
                )
            )
            if self.approval:
                self.run_store.record_tool_call(
                    run_id,
                    f"call_{index}",
                    "coding_file_write",
                    {"path": "x"},
                    status="pending",
                    approval_id=f"approval_{index}",
                )
                self.run_store.record_approval(f"approval_{index}", run_id, f"call_{index}")
            run_links.append(
                self.runtime_store.record_agent_run(
                    company_id,
                    agent_id=agent_id,
                    run_id=run_id,
                    task_id=task_id,
                    thread_id=task.get("thread_id"),
                    message_id=task.get("message_id"),
                    status=self.status,
                )
            )
            results.append({"status": "ok", "delegate": {"execution_id": run_id, "status": self.status}})
        updated = self.runtime_store.update_task(
            task_id,
            {
                "status": self.status,
                "metadata": {
                    "last_dispatch": {
                        "policy": {"direct_tool_execution": False, "mode": "agent_delegate"},
                    }
                },
            },
            company_id=company_id,
        )
        return {
            "task": updated,
            "dispatch": {"id": "dispatch_1", "status": self.status},
            "run_links": run_links,
            "results": results,
        }


def _gateway(*, status="running", approval=False):
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.company.runtime_store import CompanyRuntimeStore
    from domain.remote.task_gateway import RemoteTaskGateway

    runtime_store = CompanyRuntimeStore()
    run_store = AgentRunStore()
    fake = FakeDispatcher(runtime_store, run_store, status=status, approval=approval)
    return RemoteTaskGateway(runtime_store=runtime_store, run_store=run_store, run_dispatcher=fake), fake, runtime_store, run_store


def test_create_remote_task_bootstraps_default_company(remote_gateway_env):
    gateway, _fake, runtime_store, _run_store = _gateway()

    result = gateway.create_task({"input": "Investigate failing tests", "dispatch": False}, {})

    assert result["company_id"] == "operations-company"
    assert result["state"] == "queued"
    task = runtime_store.get_task(result["task_id"], company_id="operations-company")
    assert task["source"] == "remote"
    assert task["target_agent_ids"] == ["operations_manager"]


def test_create_remote_task_dispatches_to_operations_manager_by_default(remote_gateway_env):
    gateway, fake, _runtime_store, _run_store = _gateway()

    result = gateway.create_task({"input": "Run the remote task"}, {})

    assert fake.calls
    assert result["state"] == "running"
    assert result["run_links"][0]["agent_id"] == "operations_manager"
    assert result["task"]["metadata"]["last_dispatch"]["policy"]["direct_tool_execution"] is False


def test_create_remote_task_accepts_explicit_target_agent(remote_gateway_env):
    gateway, _fake, _runtime_store, _run_store = _gateway()

    result = gateway.create_task({"input": "Patch a bug", "target_agent_ids": ["coding_engineer"]}, {})

    assert result["run_links"][0]["agent_id"] == "coding_engineer"
    assert result["task"]["target_agent_ids"] == ["coding_engineer"]


def test_create_remote_task_rejects_unknown_target_agent(remote_gateway_env):
    from domain.remote.task_gateway import RemoteTaskGatewayError

    gateway, _fake, _runtime_store, _run_store = _gateway()

    with pytest.raises(RemoteTaskGatewayError) as exc:
        gateway.create_task({"input": "hello", "target_agent_ids": ["not_an_agent"]}, {})

    assert exc.value.code == "UNKNOWN_TARGET_AGENT"


def test_get_remote_task_returns_task_run_links_and_waiting_approvals(remote_gateway_env):
    gateway, _fake, _runtime_store, _run_store = _gateway(status="waiting_approval", approval=True)
    created = gateway.create_task({"input": "Needs approval"}, {})

    result = gateway.get_task(created["task_id"], {}, {})

    assert result["state"] == "waiting_approval"
    assert result["run_links"][0]["status"] == "waiting_approval"
    assert result["agent_runs"][0]["status"] == "waiting_approval"
    assert result["waiting_approvals"][0]["approval_id"] == "approval_1"


def test_remote_task_events_are_stable_and_cursor_based(remote_gateway_env):
    gateway, _fake, _runtime_store, _run_store = _gateway()
    created = gateway.create_task({"input": "Queue only", "dispatch": False}, {})

    first = gateway.list_events(created["task_id"], {"limit": 10}, {})
    second = gateway.list_events(created["task_id"], {"limit": 10}, {})
    after = gateway.list_events(created["task_id"], {"after": first["next_cursor"]}, {})

    assert [event["cursor"] for event in first["events"]] == [event["cursor"] for event in second["events"]]
    assert first["events"][0]["type"] == "task.created"
    assert after["events"] == []
    assert after["next_cursor"] == first["next_cursor"]


def test_cancel_remote_task_marks_task_runs_links_and_inbox(remote_gateway_env):
    gateway, _fake, runtime_store, run_store = _gateway()
    created = gateway.create_task({"input": "Long running task"}, {})

    result = gateway.cancel_task(created["task_id"], {"reason": "no longer needed"}, {})

    assert result["state"] == "cancelled"
    assert runtime_store.get_task(created["task_id"], company_id="operations-company")["status"] == "cancelled"
    assert runtime_store.list_run_links("operations-company", task_id=created["task_id"])[0]["status"] == "cancelled"
    assert run_store.get_run("run_remote_1")["status"] == "cancelled"
    assert runtime_store.list_inbox("operations-company", agent_id="operations_manager", kind="remote_task_cancelled")


def test_host_status_reports_company_and_supervisor_counts(remote_gateway_env):
    from domain.agent_runtime.models import AgentRun

    gateway, _fake, runtime_store, run_store = _gateway()
    queued = gateway.create_task({"input": "Queued work", "dispatch": False}, {})
    run_store.upsert_run(AgentRun(run_id="run_active", session_key="s", task="active", status="running", agent_id="operations_manager"))
    run_store.upsert_run(AgentRun(run_id="run_wait", session_key="s", task="wait", status="waiting_approval", agent_id="operations_manager"))
    run_store.record_tool_call("run_wait", "call_wait", "coding_file_write", {"path": "x"}, status="pending", approval_id="approval_wait")
    run_store.record_approval("approval_wait", "run_wait", "call_wait")
    run_store.upsert_run(
        AgentRun(
            run_id="run_stale",
            session_key="s",
            task="stale",
            status="running",
            agent_id="operations_manager",
            heartbeat_at="2000-01-01T00:00:00Z",
        )
    )
    for run_id, status in (("run_active", "running"), ("run_wait", "waiting_approval"), ("run_stale", "running")):
        runtime_store.record_agent_run(
            "operations-company",
            agent_id="operations_manager",
            run_id=run_id,
            task_id=queued["task_id"],
            status=status,
        )

    result = gateway.host_status({"stale_after_seconds": 1}, {})

    assert result["company"]["bootstrapped"] is True
    assert result["runtime"]["open_tasks"] >= 1
    assert result["runtime"]["active_runs"] >= 3
    assert result["runtime"]["waiting_approvals"] == 1
    assert result["runtime"]["stale_runs"] == 1
