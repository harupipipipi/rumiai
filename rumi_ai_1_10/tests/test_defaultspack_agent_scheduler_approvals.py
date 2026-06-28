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
    pending_tool_name: str | None = None,
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
    pending_tool_name = pending_tool_name or tool_name
    pending = {
        "tool_name": pending_tool_name,
        "tool_call_id": f"call_{pending_tool_name}",
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
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": "unlimited"}}) is None
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": None}}) is None
    assert _schedule_auto_approval_limit({"tool_policy": {"schedule_auto_approve_max_followups": 999}}) == 64


def test_scheduler_ensure_loaded_rearms_missing_active_timer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    from domain.agent import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()

    schedule = scheduler.create_schedule(
        "interval",
        {"message": "keep testing", "conversation_id": "conv-mimo"},
        {"value": 30, "unit": "minutes"},
    )

    assert len(FakeTimer.created) == 1
    assert FakeTimer.created[0].started is True

    with scheduler._lock:
        missing = scheduler._timers.pop(schedule["id"])
    missing.cancel()

    scheduler.ensure_loaded()

    assert len(FakeTimer.created) == 2
    assert FakeTimer.created[1].started is True
    with scheduler._lock:
        assert scheduler._timers[schedule["id"]] is FakeTimer.created[1]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_ensure_loaded_rearms_dead_active_timer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    from domain.agent import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()

    schedule = scheduler.create_schedule(
        "interval",
        {"message": "keep testing", "conversation_id": "conv-mimo"},
        {"value": 30, "unit": "minutes"},
    )
    dead_timer = FakeTimer.created[0]
    dead_timer.cancel()

    scheduler.ensure_loaded()

    assert len(FakeTimer.created) == 2
    assert FakeTimer.created[1].started is True
    with scheduler._lock:
        assert scheduler._timers[schedule["id"]] is FakeTimer.created[1]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_ensure_loaded_does_not_duplicate_live_active_timer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    from domain.agent import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()

    schedule = scheduler.create_schedule(
        "interval",
        {"message": "keep testing", "conversation_id": "conv-mimo"},
        {"value": 30, "unit": "minutes"},
    )

    scheduler.ensure_loaded()
    scheduler.ensure_loaded()

    assert len(FakeTimer.created) == 1
    with scheduler._lock:
        assert scheduler._timers[schedule["id"]] is FakeTimer.created[0]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_reloads_and_rearms_when_schedule_dir_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import save_schedule

    def schedule_payload(schedule_id, message):
        return {
            "id": schedule_id,
            "name": message,
            "description": "",
            "type": "interval",
            "task": {"message": message, "conversation_id": "conv-mimo"},
            "config": {"value": 30, "unit": "minutes"},
            "status": "active",
            "execution_count": 0,
            "last_executed_at": None,
            "next_execution_at": "2099-01-01T00:00:00Z",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)

    first_dir = tmp_path / "first" / "schedules"
    second_dir = tmp_path / "second" / "schedules"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(first_dir))
    save_schedule(schedule_payload("sched-first", "first directory schedule"))

    scheduler = scheduler_module.Scheduler()
    scheduler.ensure_loaded()

    assert len(FakeTimer.created) == 1
    first_timer = FakeTimer.created[0]
    assert first_timer.args == ["sched-first"]
    assert first_timer.started is True

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(second_dir))
    save_schedule(schedule_payload("sched-second", "second directory schedule"))

    scheduler.ensure_loaded()

    assert first_timer.cancelled is True
    assert len(FakeTimer.created) == 2
    assert FakeTimer.created[1].args == ["sched-second"]
    assert FakeTimer.created[1].started is True
    with scheduler._lock:
        assert set(scheduler._schedules) == {"sched-second"}
        assert set(scheduler._timers) == {"sched-second"}

    scheduler.delete_schedule("sched-second")
    _reset_scheduler_singleton()


def test_scheduler_recovers_persisted_stale_manual_running_execution_and_can_trigger(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        del context
        calls.append(payload)
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "manual retry done"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule, save_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    schedule_id = "sched-stale-manual"
    stale_execution_id = "sexec-stale-manual"
    next_execution_at = "2099-01-01T00:00:00Z"
    save_schedule(
        {
            "id": schedule_id,
            "name": "Stale manual QA",
            "description": "",
            "type": "interval",
            "task": {"message": "keep testing", "conversation_id": "conv-mimo", "timeout": 600},
            "config": {"value": 30, "unit": "minutes"},
            "status": "active",
            "execution_count": 0,
            "last_executed_at": None,
            "next_execution_at": next_execution_at,
            "created_at": "2026-06-28T15:00:00Z",
            "updated_at": "2026-06-28T15:53:36Z",
            "running_execution": {
                "execution_id": stale_execution_id,
                "schedule_id": schedule_id,
                "started_at": "2000-01-01T00:00:00Z",
                "trigger": "manual",
            },
            "running_started_at": "2000-01-01T00:00:00Z",
        }
    )

    scheduler = scheduler_module.Scheduler()
    try:
        recovered = scheduler.get_schedule(schedule_id)

        assert "running_execution" not in recovered
        assert "running_started_at" not in recovered
        assert recovered["execution_count"] == 1
        assert recovered["last_executed_at"]
        assert recovered["next_execution_at"] == next_execution_at
        saved = load_schedule(schedule_id)
        assert "running_execution" not in saved
        assert saved["execution_count"] == 1

        entries, total = load_history(schedule_id)
        assert total == 1
        assert entries[0]["execution_id"] == stale_execution_id
        assert entries[0]["trigger"] == "manual"
        assert entries[0]["status"] == "error"
        assert entries[0]["timeout_seconds"] == 600
        assert entries[0]["recovered_stale_running_execution"] is True
        assert "timed out after 600 seconds" in entries[0]["error"]

        retry = scheduler.trigger_now(schedule_id)

        assert retry["status"] == "completed"
        assert retry["result"] == "manual retry done"
        assert len(calls) == 1
        saved_after_retry = load_schedule(schedule_id)
        assert "running_execution" not in saved_after_retry
        assert saved_after_retry["execution_count"] == 2
        entries, total = load_history(schedule_id)
        assert total == 2
        assert entries[0]["status"] == "completed"
        assert entries[1]["execution_id"] == stale_execution_id
    finally:
        scheduler.delete_schedule(schedule_id)
        _reset_scheduler_singleton()


def test_trigger_now_skips_when_schedule_has_active_running_execution(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        del context
        calls.append(payload)
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "should not run"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule, save_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    schedule_id = "sched-active-manual"
    active_execution_id = "sexec-active-manual"
    started_at = scheduler_module.timestamp()
    next_execution_at = "2099-01-01T00:00:00Z"
    save_schedule(
        {
            "id": schedule_id,
            "name": "Active manual QA",
            "description": "",
            "type": "interval",
            "task": {"message": "keep testing", "conversation_id": "conv-mimo", "timeout": 600},
            "config": {"value": 30, "unit": "minutes"},
            "status": "active",
            "execution_count": 0,
            "last_executed_at": None,
            "next_execution_at": next_execution_at,
            "created_at": "2026-06-28T15:00:00Z",
            "updated_at": "2026-06-28T15:53:36Z",
            "running_execution": {
                "execution_id": active_execution_id,
                "schedule_id": schedule_id,
                "started_at": started_at,
                "trigger": "manual",
                "timeout_seconds": 600,
            },
            "running_started_at": started_at,
        }
    )

    scheduler = scheduler_module.Scheduler()
    try:
        history = scheduler.trigger_now(schedule_id)

        assert history["status"] == "skipped"
        assert history["skipped_reason"] == "already_running"
        assert history["trigger"] == "manual"
        assert active_execution_id in history["error"]
        assert history["running_execution"]["execution_id"] == active_execution_id
        assert calls == []

        saved = load_schedule(schedule_id)
        assert saved["running_execution"]["execution_id"] == active_execution_id
        assert saved["running_execution"]["started_at"] == started_at
        assert saved["running_execution"]["trigger"] == "manual"
        assert saved["running_started_at"] == started_at
        assert saved["execution_count"] == 0
        assert saved["next_execution_at"] == next_execution_at
        entries, total = load_history(schedule_id)
        assert entries == []
        assert total == 0
    finally:
        scheduler.delete_schedule(schedule_id)
        _reset_scheduler_singleton()


def test_manual_trigger_fails_fast_when_conversation_is_busy_without_running_marker(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        del context
        calls.append(payload)
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "should not start"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {"message": "manual check", "conversation_id": "conv-busy", "timeout": 30},
        {"run_at": "2099-01-01T00:00:00Z"},
    )
    conversation_lock = scheduler._conversation_execution_lock("conv-busy")
    assert conversation_lock is not None
    assert conversation_lock.acquire(blocking=False)
    try:
        started = time.monotonic()
        history = scheduler.trigger_now(schedule["id"])
        elapsed = time.monotonic() - started
    finally:
        conversation_lock.release()

    try:
        assert elapsed < 1
        assert calls == []
        assert history["status"] == "error"
        assert history["error_code"] == "CONVERSATION_RUNNING"
        assert history["skipped_reason"] == "conversation_running"
        assert "conv-busy" in history["error"]

        saved = load_schedule(schedule["id"])
        assert "running_execution" not in saved
        assert "running_started_at" not in saved
        assert saved["execution_count"] == 1
        assert saved["last_executed_at"] == history["completed_at"]

        entries, total = load_history(schedule["id"])
        assert total == 1
        assert entries[0]["execution_id"] == history["execution_id"]
        assert entries[0]["status"] == "error"
        assert entries[0]["error_code"] == "CONVERSATION_RUNNING"
        assert entries[0]["skipped_reason"] == "conversation_running"
    finally:
        scheduler.delete_schedule(schedule["id"])
        _reset_scheduler_singleton()


def test_timer_skips_active_running_execution_without_overwriting_or_chat_send(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        del context
        calls.append(payload)
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "should not run"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule, save_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    schedule_id = "sched-active-timer"
    active_execution_id = "sexec-active-timer"
    started_at = scheduler_module.timestamp()
    overdue_next = "2000-01-01T00:00:00Z"
    save_schedule(
        {
            "id": schedule_id,
            "name": "Active timer QA",
            "description": "",
            "type": "interval",
            "task": {"message": "keep testing", "conversation_id": "conv-mimo", "timeout": 600},
            "config": {"value": 30, "unit": "minutes"},
            "status": "active",
            "execution_count": 0,
            "last_executed_at": None,
            "next_execution_at": overdue_next,
            "created_at": "2026-06-28T15:00:00Z",
            "updated_at": "2026-06-28T15:53:36Z",
            "running_execution": {
                "execution_id": active_execution_id,
                "schedule_id": schedule_id,
                "started_at": started_at,
                "trigger": "manual",
                "timeout_seconds": 600,
            },
            "running_started_at": started_at,
        }
    )

    scheduler = scheduler_module.Scheduler()
    try:
        scheduler.ensure_loaded()
        initial_timer_count = len(FakeTimer.created)

        scheduler._on_timer_fire(schedule_id)

        assert calls == []
        saved = load_schedule(schedule_id)
        assert saved["running_execution"]["execution_id"] == active_execution_id
        assert saved["running_execution"]["started_at"] == started_at
        assert saved["running_execution"]["trigger"] == "manual"
        assert saved["running_started_at"] == started_at
        assert saved["execution_count"] == 0
        assert saved["last_executed_at"] is None
        assert saved["next_execution_at"] != overdue_next
        assert saved["next_execution_at"]
        assert len(FakeTimer.created) == initial_timer_count + 1
        assert FakeTimer.created[-1].args == [schedule_id]
        assert FakeTimer.created[-1].started is True

        entries, total = load_history(schedule_id)
        assert total == 1
        assert entries[0]["status"] == "skipped"
        assert entries[0]["skipped_reason"] == "already_running"
        assert entries[0]["trigger"] == "scheduled"
        assert entries[0]["running_execution"]["execution_id"] == active_execution_id
        assert active_execution_id in entries[0]["error"]
    finally:
        scheduler.delete_schedule(schedule_id)
        _reset_scheduler_singleton()


def test_once_timer_skip_for_active_running_execution_stays_active_and_retries(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        del context
        calls.append(payload)
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "should not run"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule, save_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    schedule_id = "sched-once-active-timer"
    active_execution_id = "sexec-once-active-timer"
    started_at = scheduler_module.timestamp()
    overdue_next = "2000-01-01T00:00:00Z"
    save_schedule(
        {
            "id": schedule_id,
            "name": "Active once timer QA",
            "description": "",
            "type": "once",
            "task": {"message": "keep testing", "conversation_id": "conv-mimo", "timeout": 600},
            "config": {"run_at": overdue_next},
            "status": "active",
            "execution_count": 0,
            "last_executed_at": None,
            "next_execution_at": overdue_next,
            "created_at": "2026-06-28T15:00:00Z",
            "updated_at": "2026-06-28T15:53:36Z",
            "running_execution": {
                "execution_id": active_execution_id,
                "schedule_id": schedule_id,
                "started_at": started_at,
                "trigger": "manual",
                "timeout_seconds": 600,
            },
            "running_started_at": started_at,
        }
    )

    scheduler = scheduler_module.Scheduler()
    try:
        scheduler.ensure_loaded()
        initial_timer_count = len(FakeTimer.created)

        scheduler._on_timer_fire(schedule_id)

        assert calls == []
        saved = load_schedule(schedule_id)
        assert saved["status"] == "active"
        assert saved["running_execution"]["execution_id"] == active_execution_id
        assert saved["running_execution"]["started_at"] == started_at
        assert saved["running_execution"]["trigger"] == "manual"
        assert saved["running_started_at"] == started_at
        assert saved["execution_count"] == 0
        assert saved["last_executed_at"] is None
        assert saved["next_execution_at"] != overdue_next
        assert saved["next_execution_at"]
        assert len(FakeTimer.created) == initial_timer_count + 1
        assert FakeTimer.created[-1].args == [schedule_id]
        assert FakeTimer.created[-1].started is True

        entries, total = load_history(schedule_id)
        assert total == 1
        assert entries[0]["status"] == "skipped"
        assert entries[0]["skipped_reason"] == "already_running"
        assert entries[0]["trigger"] == "scheduled"
        assert entries[0]["running_execution"]["execution_id"] == active_execution_id
        assert active_execution_id in entries[0]["error"]
    finally:
        scheduler.delete_schedule(schedule_id)
        _reset_scheduler_singleton()


def test_scheduler_marks_interval_running_until_task_completes(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        created = []

        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False
            FakeTimer.created.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    started = threading.Event()
    release = threading.Event()

    def fake_send_chat(payload, context):
        started.set()
        assert release.wait(5)
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "interval done"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)
    from domain.agent import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()

    schedule = scheduler.create_schedule(
        "interval",
        {"message": "keep testing", "conversation_id": "conv-mimo"},
        {"value": 30, "unit": "minutes"},
    )

    worker = threading.Thread(target=scheduler._on_timer_fire, args=(schedule["id"],))
    worker.start()
    assert started.wait(5)

    running = scheduler.get_schedule(schedule["id"])
    assert running["running_execution"]["execution_id"].startswith("sexec_")
    assert running["running_execution"]["schedule_id"] == schedule["id"]
    assert running["running_execution"]["trigger"] == "scheduled"
    assert running["running_started_at"] == running["running_execution"]["started_at"]

    release.set()
    worker.join(5)
    assert not worker.is_alive()

    completed = scheduler.get_schedule(schedule["id"])
    assert "running_execution" not in completed
    assert "running_started_at" not in completed
    assert completed["execution_count"] == 1
    assert completed["last_executed_at"]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduled_execution_persists_completion_and_next_time_together(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    def fake_send_chat(payload, context):
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "interval done"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)
    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule, save_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {"message": "keep testing", "conversation_id": "conv-mimo"},
        {"value": 30, "unit": "minutes"},
    )
    with scheduler._lock:
        scheduler._schedules[schedule["id"]]["next_execution_at"] = "2000-01-01T00:00:00Z"
        save_schedule(scheduler._schedules[schedule["id"]])

    scheduler._execute_task(schedule["id"], manual=False)

    saved = load_schedule(schedule["id"])
    history, total = load_history(schedule["id"])
    assert total == 1
    assert history[0]["status"] == "completed"
    assert "running_execution" not in saved
    assert "running_started_at" not in saved
    assert saved["execution_count"] == 1
    assert saved["last_executed_at"] == history[0]["completed_at"]
    assert saved["next_execution_at"] != "2000-01-01T00:00:00Z"
    assert saved["next_execution_at"]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_times_out_conversation_run_and_allows_next_interval(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    calls: list[dict] = []
    calls_lock = threading.Lock()
    first_call_started = threading.Event()
    first_call_release = threading.Event()
    first_call_finished = threading.Event()

    def fake_send_chat(payload, context):
        del context
        with calls_lock:
            calls.append(payload)
            index = len(calls)
        if index == 1:
            first_call_started.set()
            try:
                first_call_release.wait(timeout=5)
            finally:
                first_call_finished.set()
            return {
                "status": "ok",
                "data": {
                    "id": "assistant-late",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "late first run"}],
                    "finish_reason": "stop",
                    "metadata": {},
                },
            }
        return {
            "status": "ok",
            "data": {
                "id": "assistant-next",
                "role": "assistant",
                "content": [{"type": "text", "text": "next interval done"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule, save_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()
    schedule = None
    try:
        schedule = scheduler.create_schedule(
            "interval",
            {"message": "keep testing", "conversation_id": "conv-mimo", "timeout": 0.2},
            {"value": 30, "unit": "minutes"},
        )
        stale_next = "2000-01-01T00:00:00Z"
        with scheduler._lock:
            scheduler._schedules[schedule["id"]]["next_execution_at"] = stale_next
            save_schedule(scheduler._schedules[schedule["id"]])

        first_history = scheduler._execute_task(schedule["id"], manual=False)

        assert first_call_started.wait(timeout=1)
        assert first_history["status"] == "error"
        assert "timed out after 0.2 seconds" in first_history["error"]
        assert first_history["timeout_seconds"] == 0.2
        saved_after_timeout = load_schedule(schedule["id"])
        assert "running_execution" not in saved_after_timeout
        assert "running_started_at" not in saved_after_timeout
        assert saved_after_timeout["execution_count"] == 1
        assert saved_after_timeout["last_executed_at"] == first_history["completed_at"]
        assert saved_after_timeout["next_execution_at"] != stale_next
        assert not first_call_finished.is_set()

        second_history = scheduler._execute_task(schedule["id"], manual=False)

        assert second_history["status"] == "completed"
        assert second_history["result"] == "next interval done"
        with calls_lock:
            assert len(calls) == 2
        saved_after_second = load_schedule(schedule["id"])
        assert "running_execution" not in saved_after_second
        assert saved_after_second["execution_count"] == 2

        entries, total = load_history(schedule["id"])
        assert total == 2
        assert entries[0]["status"] == "completed"
        assert entries[1]["status"] == "error"
        assert entries[1]["timeout_seconds"] == 0.2
    finally:
        first_call_release.set()
        first_call_finished.wait(timeout=1)
        if schedule is not None:
            scheduler.delete_schedule(schedule["id"])
        _reset_scheduler_singleton()


def test_scheduler_times_out_ai_complete_run_and_clears_running(tmp_path, monkeypatch):
    _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    class FakeTimer:
        def __init__(self, delay, callback, args=None):
            self.delay = delay
            self.callback = callback
            self.args = args or []
            self.started = False
            self.cancelled = False

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    complete_started = threading.Event()
    complete_release = threading.Event()
    complete_finished = threading.Event()

    def fake_complete(payload, context):
        del payload, context
        complete_started.set()
        try:
            complete_release.wait(timeout=5)
        finally:
            complete_finished.set()
        return {"status": "ok", "data": {"content": "late complete"}}

    monkeypatch.setattr("blocks.ai.complete.run", fake_complete)

    from domain.agent import scheduler as scheduler_module
    from domain.agent.schedule_store import load_history, load_schedule

    monkeypatch.setattr(scheduler_module.threading, "Timer", FakeTimer)
    scheduler = scheduler_module.Scheduler()
    schedule = None
    try:
        schedule = scheduler.create_schedule(
            "interval",
            {"message": "summarize", "model": "stub/default", "timeout": 0.2},
            {"value": 30, "unit": "minutes"},
        )

        history = scheduler._execute_task(schedule["id"], manual=False)

        assert complete_started.wait(timeout=1)
        assert history["status"] == "error"
        assert "timed out after 0.2 seconds" in history["error"]
        assert history["timeout_seconds"] == 0.2
        saved = load_schedule(schedule["id"])
        assert "running_execution" not in saved
        assert "running_started_at" not in saved
        assert saved["execution_count"] == 1
        entries, total = load_history(schedule["id"])
        assert total == 1
        assert entries[0]["status"] == "error"
        assert entries[0]["timeout_seconds"] == 0.2
    finally:
        complete_release.set()
        complete_finished.wait(timeout=1)
        if schedule is not None:
            scheduler.delete_schedule(schedule["id"])
        _reset_scheduler_singleton()


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
    assert followup["arguments"] == {
        "url": "http://127.0.0.1:8766/chat",
        "profile_id": "default",
        "persistent": True,
        "target_app": "",
    }
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


def test_scheduler_auto_approved_browser_computer_followup_includes_inline_arguments(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []
    screenshot_args = {"action": "computer.screenshot", "payload": {"detail": "high"}}

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) == 1:
            return _approval_required_response(
                approval,
                conversation_id="conv-mimo",
                tool_name="browser_computer",
                operation="computer.screenshot",
                risk_level="high",
                arguments=screenshot_args,
            )
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "screenshot captured"}],
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
            "message": "Capture a browser computer screenshot.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["browser_computer"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["browser_computer"],
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
    assert len(calls) == 2
    followup = calls[1]["payload"]["message"]["metadata"]["approval_followup"]
    assert followup["tool_name"] == "browser_computer"
    assert followup["operation"] == "computer.screenshot"
    assert followup["arguments"] == screenshot_args
    assert "approval_token" not in followup["arguments"]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_resumes_mimo_request_already_approved_by_manager(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []
    approval_args = {"path": "notes.txt", "content": "approved by manager"}
    external_approval: dict[str, str] = {}

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) == 1:
            response = _approval_required_response(
                approval,
                conversation_id="conv-mimo",
                tool_name="coding_file_write",
                operation="tool.coding_file_write",
                risk_level="medium",
                arguments=approval_args,
            )
            request_id = response["data"]["metadata"]["pending_approval"]["request_id"]
            decision = approval.approve(request_id)
            assert decision["approved"] is True
            external_approval.update({"request_id": request_id, "token": decision["token"]})
            assert approval.get_approval_request(request_id)["status"] == "approved"
            return response
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "approved write completed"}],
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
            "message": "Write the scheduled note.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "self_improvement",
            "tools": ["coding_file_write"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["coding_file_write"],
                "schedule_auto_approve_max_followups": "unlimited",
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
    assert history["result"] == "approved write completed"
    assert len(calls) == 2
    followup = calls[1]["payload"]["message"]["metadata"]["approval_followup"]
    assert followup["request_id"] == external_approval["request_id"]
    assert followup["approval_token"]
    assert followup["approval_token"] != external_approval["token"]
    assert history["auto_approvals"] == [
        {
            "request_id": external_approval["request_id"],
            "tool_name": "coding_file_write",
            "operation": "tool.coding_file_write",
            "status": "approved",
        }
    ]

    verification = approval.verify_execution_token(
        followup["approval_token"],
        "tool.coding_file_write",
        approval.hash_arguments(approval_args),
        consume=True,
        pack_id="defaultspack",
        conversation_id="conv-mimo",
    )
    assert verification.valid is True
    assert approval.get_approval_request(external_approval["request_id"])["status"] == "consumed"

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


def test_scheduler_auto_approves_display_name_tool_requests(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) == 1:
            return _approval_required_response(
                approval,
                conversation_id="conv-mimo",
                tool_name="Desktop List",
                pending_tool_name="desktop_list",
                operation="tool.Desktop List",
                risk_level="medium",
                arguments={},
            )
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "desktop list checked"}],
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
            "message": "List managed desktops.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["desktop_list"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["desktop_list"],
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
    assert history["result"] == "desktop list checked"
    assert len(calls) == 2
    assert calls[0]["context"]["owner_pack"] == "defaultspack"
    assert calls[1]["context"]["owner_pack"] == "defaultspack"
    assert history["auto_approvals"] == [
        {
            "request_id": calls[1]["payload"]["message"]["metadata"]["approval_followup"]["request_id"],
            "tool_name": "desktop_list",
            "operation": "tool.Desktop List",
            "status": "approved",
        }
    ]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_unlimited_auto_approves_repeated_rumi_api_get_desktop_frame_requests(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    approval_count = 66
    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) <= approval_count:
            seat_id = f"seat-{len(calls)}"
            return _approval_required_response(
                approval,
                conversation_id="conv-mimo",
                tool_name="rumi_api",
                operation="tool.rumi_api",
                risk_level="high",
                arguments={
                    "action": "request",
                    "method": "GET",
                    "path": f"/api/desktops/{seat_id}/frame",
                },
            )
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "desktop frames inspected"}],
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
            "message": "Keep inspecting the desktop frames.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["rumi_api"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["GET /api/desktops/{id}/frame"],
                "schedule_auto_approve_max_followups": "unlimited",
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
    assert history["result"] == "desktop frames inspected"
    assert len(calls) == approval_count + 1
    assert len(history["auto_approvals"]) == approval_count
    assert history["auto_approvals"][0]["tool_name"] == "rumi_api"
    assert history["auto_approvals"][0]["operation"] == "GET /api/desktops/{id}/frame"
    assert history["auto_approvals"][-1]["operation"] == "GET /api/desktops/{id}/frame"
    assert "approval_token" not in history["auto_approvals"][0]
    followup = calls[1]["payload"]["message"]["metadata"]["approval_followup"]
    assert followup["tool_name"] == "rumi_api"
    assert followup["operation"] == "tool.rumi_api"
    assert followup["approval_token"]

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_does_not_auto_approve_post_frame_when_get_frame_is_allowlisted(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        return _approval_required_response(
            approval,
            conversation_id="conv-mimo",
            tool_name="rumi_api",
            operation="tool.rumi_api",
            risk_level="high",
            arguments={
                "action": "request",
                "method": "POST",
                "path": "/api/desktops/seat-1/frame",
            },
        )

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {
            "message": "Inspect a desktop frame.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["rumi_api"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["GET /api/desktops/{id}/frame"],
                "schedule_auto_approve_max_followups": "unlimited",
            },
            "metadata": {
                "profile_id": "defaultspack.mimo_coding_company",
                "company_id": "mimo-coding-company",
            },
        },
        {"run_at": "2099-01-01T00:00:00Z"},
    )

    history = scheduler.trigger_now(schedule["id"])

    assert history["status"] == "approval_required"
    assert len(calls) == 1
    assert "auto_approvals" not in history

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_does_not_auto_approve_rumi_api_post_frame_from_desktop_frame_alias(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        return _approval_required_response(
            approval,
            conversation_id="conv-mimo",
            tool_name="rumi_api",
            operation="tool.rumi_api",
            risk_level="high",
            arguments={
                "action": "request",
                "method": "POST",
                "path": "/api/desktops/seat-1/frame",
            },
        )

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from domain.agent.scheduler import Scheduler

    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {
            "message": "Inspect a desktop frame.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["rumi_api"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["desktop_frame"],
                "schedule_auto_approve_max_followups": "unlimited",
            },
            "metadata": {
                "profile_id": "defaultspack.mimo_coding_company",
                "company_id": "mimo-coding-company",
            },
        },
        {"run_at": "2099-01-01T00:00:00Z"},
    )

    history = scheduler.trigger_now(schedule["id"])

    assert history["status"] == "approval_required"
    assert len(calls) == 1
    assert "auto_approvals" not in history

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_scheduler_auto_approves_route_listing_without_broad_rumi_api_allowlist(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    _reset_scheduler_singleton()

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        if len(calls) == 1:
            return _approval_required_response(
                approval,
                conversation_id="conv-mimo",
                tool_name="rumi_api",
                operation="tool.rumi_api",
                risk_level="medium",
                arguments={"action": "list_routes"},
            )
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "routes checked"}],
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
            "message": "List routes.",
            "model": "stub/default",
            "conversation_id": "conv-mimo",
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["rumi_api"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["rumi_api:list_routes"],
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
    assert history["result"] == "routes checked"
    assert len(calls) == 2
    assert history["auto_approvals"][0]["tool_name"] == "rumi_api"
    assert history["auto_approvals"][0]["operation"] == "tool.rumi_api"

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_mimo_status_recovers_externally_approved_scheduled_approval(tmp_path, monkeypatch):
    approval = _setup_approval_store(tmp_path, monkeypatch)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(tmp_path / "schedules"))
    _reset_scheduler_singleton()

    from domain.chat.store import ChatStore

    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(
        model="stub/default",
        conversation_kind="mimo_coding_company",
        metadata={
            "profile_id": "defaultspack.mimo_coding_company",
            "company_id": "mimo-coding-company",
        },
    )
    conversation_id = conversation["id"]

    from domain.agent.scheduler import Scheduler
    from domain.agent.schedule_store import load_history

    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "once",
        {
            "message": "Run browser QA.",
            "model": "stub/default",
            "conversation_id": conversation_id,
            "profile_id": "defaultspack.mimo_coding_company",
            "agent_id": "browser_qa",
            "tools": ["browser_use"],
            "tool_policy": {
                "profile_id": "defaultspack.mimo_coding_company",
                "schedule_initial_tool_choice": "required",
                "schedule_auto_approve_tool_requests": True,
                "schedule_auto_approve_tool_allowlist": ["browser_use"],
                "schedule_auto_approve_max_followups": "unlimited",
            },
            "metadata": {
                "profile_id": "defaultspack.mimo_coding_company",
                "company_id": "mimo-coding-company",
                "conversation_id": conversation_id,
            },
        },
        {"run_at": "2099-01-01T00:00:00Z"},
    )
    approval_response = _approval_required_response(
        approval,
        conversation_id=conversation_id,
        tool_name="browser_use",
        operation="tool.browser_use",
    )
    pending = approval_response["data"]["metadata"]["pending_approval"]
    request_id = pending["request_id"]
    scheduler_message = store.add_message(
        conversation_id,
        {
            "role": "user",
            "content": "Run browser QA.",
            "metadata": {
                "source": "scheduler",
                "schedule_id": schedule["id"],
                "schedule_execution_id": "sexec-original",
                "trigger": "scheduled",
                "profile_id": "defaultspack.mimo_coding_company",
                "company_id": "mimo-coding-company",
            },
        },
    )
    approval_message = store.add_message(conversation_id, approval_response["data"])
    assert scheduler_message is not None
    assert approval_message is not None
    store.add_message(
        conversation_id,
        {
            "role": "user",
            "content": "A later stored branch message should not be treated as current.",
            "metadata": {"source": "manual"},
        },
    )
    store.update_conversation(conversation_id, {"current_node_id": approval_message["id"]})

    external_decision = approval.approve(request_id)
    assert external_decision["approved"] is True

    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        return {
            "status": "ok",
            "data": {
                "id": "assistant-final",
                "role": "assistant",
                "content": [{"type": "text", "text": "continued after approval"}],
                "finish_reason": "stop",
                "metadata": {},
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)

    from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import MimoCodingCompanyRuntime

    try:
        runtime = MimoCodingCompanyRuntime()
        schedules = runtime._schedules_for_state({"schedule_ids": {"qa_loop": schedule["id"]}})

        assert [item["id"] for item in schedules] == [schedule["id"]]
        assert len(calls) == 1
        payload = calls[0]["payload"]
        metadata = payload["message"]["metadata"]
        assert metadata["source"] == "scheduler_approval_followup"
        assert metadata["schedule_id"] == schedule["id"]
        assert metadata["schedule_execution_id"] == "sexec-original"
        assert metadata["approval_followup"]["request_id"] == request_id
        assert metadata["approval_followup"]["approval_token"]
        assert "tool_choice" not in payload["params"]
        assert calls[0]["context"]["owner_pack"] == "defaultspack"

        entries, total = load_history(schedule["id"])
        assert total == 1
        history = entries[0]
        assert history["status"] == "completed"
        assert history["result"] == "continued after approval"
        assert history["recovered_scheduled_approval"] is True
        assert history["recovered_execution_id"] == "sexec-original"
        assert history["auto_approvals"] == [
            {
                "request_id": request_id,
                "tool_name": "browser_use",
                "operation": "tool.browser_use",
                "status": "approved",
            }
        ]
        assert "approval_token" not in history["auto_approvals"][0]
    finally:
        scheduler.delete_schedule(schedule["id"])
        _reset_scheduler_singleton()
        ChatStore._instance = None


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
    assert "owner_pack" not in calls[0]["context"]
    assert "auto_approvals" not in history

    scheduler.delete_schedule(schedule["id"])
    _reset_scheduler_singleton()


def test_schedule_history_replaces_lone_surrogates_before_persisting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", raising=False)

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
        results[key] = scheduler._execute_task(schedule_id, manual=False)

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
