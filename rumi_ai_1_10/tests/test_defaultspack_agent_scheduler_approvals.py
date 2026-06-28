from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_scheduler_singleton():
    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler._instance
    if scheduler is not None:
        for schedule_id in list(getattr(scheduler, "_timers", {}).keys()):
            scheduler._cancel_timer(schedule_id)
    Scheduler._instance = None


def _setup_approval_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_APPROVAL_DB_PATH", str(tmp_path / "safety" / "approval.sqlite3"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_APPROVAL_SECRET_PATH", str(tmp_path / "safety" / "approval.secret"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    return approval


def _approval_required_response(
    approval,
    *,
    conversation_id: str,
    tool_name: str = "browser_use",
    operation: str = "browser.open_url",
    risk_level: str = "high",
    arguments: dict | None = None,
) -> dict:
    if arguments is None:
        arguments = {
            "url": "http://127.0.0.1:8766/chat",
            "profile_id": "default",
            "persistent": True,
            "target_app": "",
        }
    request = approval.create_approval_request(
        operation,
        risk_level,
        arguments,
        details={
            "tool_name": tool_name,
            "action": operation,
            "function_id": operation,
            "pack_id": "defaultspack",
            "conversation_id": conversation_id,
            "arguments": arguments,
        },
    )
    pending = {
        "tool_name": tool_name,
        "tool_call_id": f"call_{tool_name}",
        "action": operation,
        "operation": operation,
        "payload": arguments,
        "approval_required": True,
        "approval_request_id": request["request_id"],
        "request_id": request["request_id"],
        "expires_at": request["expires_at"],
    }
    return {
        "status": "ok",
        "data": {
            "id": "assistant-approval",
            "role": "assistant",
            "content": [{"type": "text", "text": "approval needed"}],
            "finish_reason": "approval_required",
            "metadata": {"pending_approval": pending},
        },
    }


def test_schedule_auto_approval_limit_accepts_unlimited_policy():
    from domain.agent.scheduler import _schedule_auto_approval_limit

    assert _schedule_auto_approval_limit({"tool_policy": {}}) == 3
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": 0}}) == 0
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": "unlimited"}}) == 64
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": None}}) == 64
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": 999}}) == 64


def test_scheduler_auto_approves_mimo_scheduled_browser_request(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) == 1:
            return _approval_required_response(approval, conversation_id="conv-mimo")
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "opened and inspected"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {
            "message": "Run browser QA.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["browser_use"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_initial_tool_choice": "required",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["browser_use"],
                "schedule_auto_approve_max_followups": 2,
            },
            "metadata": {
                "profile_id": "defaultspack.mimo_coding_company",
                "company_id": "mimo-coding-company",
            },
        },
        {"run_at": "2099-01-01T00:00:00Z"},
    )

    history = scheduler.trigger_now(schedule["id"])

    assert history["status"] == "completed"
    assert history["result"] == "opened and inspected"
    assert len(calls) == 2
    assert calls[0]["payload"]["params"]["tool_choice"] == "required"
    assert "tool_choice" not in calls[1]["payload"]["params"]
    followup = calls[1]["payload"]["message"]["metadata"]["approval_followup"]
    assert followup["tool_name"] == "browser_use"
    assert followup["request_id"].startswith("apr_")
    assert followup["approval_token"]
    assert history["auto_approvals"] == [
        {
            "request_id": followup["request_id"],
            "tool_name": "browser_use",
            "operation": "browser.open_url",
            "status": "approved",
        }
    ]
    assert "approval_token" not in history["auto_approvals"][0]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_auto_approves_mimo_scheduled_todo_request(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) == 1:
            return _approval_required_response(
                approval,
                conversation_id="conv-mimo",
                tool_name="todo",
                operation="tool.todo",
                risk_level="medium",
                arguments={"action": "list"},
            )
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "todo list checked and task continued"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {
            "message": "Run MiMo QA loop.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "qa_loop",
            "tools": ["todo"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["todo"],
                "schedule_auto_approve_max_followups": 2,
            },
            "metadata": {
                "profile_id": "defaultspack.mimo_coding_company",
                "company_id": "mimo-coding-company",
            },
        },
        {"run_at": "2099-01-01T00:00:00Z"},
    )

    history = scheduler.trigger_now(schedule["id"])

    assert history["status"] == "completed"
    assert history["result"] == "todo list checked and task continued"
    assert len(calls) == 2
    followup = calls[1]["payload"]["message"]["metadata"]["approval_followup"]
    assert followup["tool_name"] == "todo"
    assert followup["operation"] == "tool.todo"
    assert followup["approval_token"]
    assert history["auto_approvals"] == [
        {
            "request_id": followup["request_id"],
            "tool_name": "todo",
            "operation": "tool.todo",
            "status": "approved",
        }
    ]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_leaves_non_mimo_approval_waiting(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        return _approval_required_response(approval, conversation_id="conv-other")

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {
            "message": "Run browser QA.",
            "model": "stub/default",
            "conversation_id": "conv-other",
            "profile_id": "defaultspack.local_agent",
            "agent_id": "browser_qa",
            "tools": ["browser_use"],
            "tool_policy": {
                "profile_id": "defaultspack.local_agent",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["browser_use"],
            },
            "metadata": {
                "profile_id": "defaultspack.local_agent",
                "company_id": "other-company",
            },
        },
        {"run_at": "2099-01-01T00:00:00Z"},
    )

    history = scheduler.trigger_now(schedule["id"])

    assert history["status"] == "approval_required"
    assert history["finish_reason"] == "approval_required"
    assert "approval_required" in history["result"]
    assert len(calls) == 1
    assert "auto_approvals" not in history

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_schedule_history_replaces_lone_surrogates_before_persisting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from domain.agent.schedule_store import append_history, load_history, save_schedule

    save_schedule(
        {
            "id": "sched-surrogate",
            "type": "once",
            "task": {"message": "bad \udc88 schedule"},
            "config": {"run_at": "2099-01-01T00:00:00Z"},
            "status": "active",
        }
    )
    append_history(
        "sched-surrogate",
        {
            "execution_id": "sexec-surrogate",
            "status": "error",
            "error": "bad \udc88 history",
        },
    )

    entries, total = load_history("sched-surrogate")

    assert total == 1
    assert entries[0]["error"] == "bad ? history"
    assert "bad ? schedule" in (tmp_path / "user_data" / "shared" / "schedules" / "sched-surrogate.json").read_text(
        encoding="utf-8"
    )


def test_schedule_store_can_use_explicit_schedules_dir_when_cwd_differs(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / "rumi_ai_1_10"
    schedules_dir = runtime_root / "user_data" / "shared" / "schedules"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(schedules_dir))

    from domain.agent.schedule_store import load_history, save_schedule, append_history

    save_schedule(
        {
            "id": "sched-explicit",
            "type": "once",
            "task": {"message": "use explicit runtime schedule dir"},
            "config": {"run_at": "2099-01-01T00:00:00Z"},
            "status": "active",
        }
    )
    append_history(
        "sched-explicit",
        {
            "execution_id": "sexec-explicit",
            "status": "completed",
            "result": "ok",
        },
    )

    entries, total = load_history("sched-explicit")

    assert total == 1
    assert entries[0]["result"] == "ok"
    assert (schedules_dir / "sched-explicit.json").is_file()
    assert not (repo_root / "user_data" / "shared" / "schedules" / "sched-explicit.json").exists()


def test_scheduler_serializes_chat_runs_for_same_conversation(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    active = 0
    max_active = 0
    call_count = 0
    lock = threading.Lock()
    first_call_started = threading.Event()
    release_first_call = threading.Event()

    def fake_send_chat(payload, context):
        nonlocal active, max_active, call_count
        with lock:
            active += 1
            max_active = max(max_active, active)
            call_count += 1
            index = call_count
            if index == 1:
                first_call_started.set()
        if index == 1:
            assert release_first_call.wait(timeout=2)
        time.sleep(0.05)
        content = payload["message"]["content"]
        with lock:
            active -= 1
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": content + " done"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler()
    first = scheduler.create_schedule(
        "once",
        {"message": "first", "conversation_id": "conv-shared"},
        {"run_at": "2099-01-01T00:00:00Z"},
    )
    second = scheduler.create_schedule(
        "once",
        {"message": "second", "conversation_id": "conv-shared"},
        {"run_at": "2099-01-01T00:00:00Z"},
    )

    results = {}

    def run_schedule(key, schedule_id):
        results[key] = scheduler.trigger_now(schedule_id)

    t1 = threading.Thread(target=run_schedule, args=("first", first["id"]))
    t2 = threading.Thread(target=run_schedule, args=("second", second["id"]))
    t1.start()
    assert first_call_started.wait(timeout=2)
    t2.start()
    time.sleep(0.1)

    assert call_count == 1
    assert max_active == 1

    release_first_call.set()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert results["first"]["status"] == "completed"
    assert results["second"]["status"] == "completed"
    assert max_active == 1

    scheduler.delete_schedule(first["id"])
    scheduler.delete_schedule(second["id"])
    _reset_scheduler_singleton()
