from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.agent.scheduler import trigger as trigger_block  # noqa: E402
from domain.agent.schedule_store import load_history, load_schedule  # noqa: E402
from domain.agent.scheduler import Scheduler  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_scheduler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate the singleton, schedule files, and durable execution ledger."""
    schedules_dir = tmp_path / "schedules"
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(schedules_dir)
    )
    instance = getattr(Scheduler, "_instance", None)
    if instance is not None:
        instance.shutdown()
    Scheduler._instance = None
    yield
    instance = getattr(Scheduler, "_instance", None)
    if instance is not None:
        instance.shutdown()
    Scheduler._instance = None


def test_startup_failure_settles_durable_run_before_returning_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-model chat failure cannot leave an active schedule projection."""
    model_called = False

    def fail_before_model(payload, context):
        nonlocal model_called
        assert payload["conversation_id"] == "missing-conversation"
        return {
            "status": "error",
            "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
        }

    def unexpected_model_call(payload, context):
        nonlocal model_called
        model_called = True
        raise AssertionError("model invocation must not be reached")

    monkeypatch.setattr("blocks.chat.send.run", fail_before_model)
    monkeypatch.setattr("blocks.ai.complete.run", unexpected_model_call)
    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {
            "message": "heartbeat",
            "model": "stub/default",
            "conversation_id": "missing-conversation",
        },
        {"value": 30, "unit": "minutes"},
    )

    result = trigger_block.run({"schedule_id": schedule["id"]}, {})

    assert result["status"] == "error"
    assert result["_http_status"] == 409
    assert not model_called
    history = result["data"]["history_entry"]
    execution = scheduler._durable_execution_store().require(
        history["execution_id"]
    )
    assert execution["status"] == "failed"
    assert scheduler._durable_execution_store().active_for_schedule(
        schedule["id"]
    ) is None
    persisted = load_schedule(schedule["id"])
    assert "running_execution" not in persisted
    assert persisted["last_execution_status"] == "error"
    assert persisted["last_execution_error"] == "Conversation not found"


def test_approval_wait_is_active_and_duplicate_manual_trigger_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval wait preserves one run instead of creating double authority."""

    def wait_for_approval(payload, context):
        return {
            "status": "ok",
            "data": {
                "id": "assistant-approval",
                "content": [{"type": "text", "text": "approval needed"}],
                "finish_reason": "approval_required",
                "metadata": {
                    "pending_approval": {"request_id": "approval-1"},
                },
            },
        }

    monkeypatch.setattr("blocks.chat.send.run", wait_for_approval)
    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {
            "message": "needs approval",
            "conversation_id": "conversation-approval",
        },
        {"value": 30, "unit": "minutes"},
    )

    first = trigger_block.run({"schedule_id": schedule["id"]}, {})
    assert first["status"] == "ok"
    execution_id = first["data"]["execution_id"]
    assert first["data"]["status"] == "approval_required"
    active = scheduler._durable_execution_store().active_for_schedule(schedule["id"])
    assert active["execution_id"] == execution_id
    assert active["status"] == "waiting_approval"
    persisted = load_schedule(schedule["id"])
    assert persisted["running_execution"]["execution_id"] == execution_id
    assert persisted["running_execution"]["status"] == "waiting_approval"

    duplicate = trigger_block.run({"schedule_id": schedule["id"]}, {})
    assert duplicate["status"] == "error"
    assert duplicate["_http_status"] == 409
    assert duplicate["data"]["cause_code"] == "ALREADY_RUNNING"
    assert (
        duplicate["data"]["history_entry"]["running_execution"]["execution_id"]
        == execution_id
    )
    assert len(
        scheduler._durable_execution_store().list_active(
            schedule_id=schedule["id"]
        )
    ) == 1


def test_completed_run_is_terminal_and_clears_active_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful settlement updates ledger, history metadata, and projection."""

    def complete(payload, context):
        return {"status": "ok", "data": {"content": "done"}}

    monkeypatch.setattr("blocks.ai.complete.run", complete)
    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {"message": "summarize", "model": "stub/default"},
        {"value": 30, "unit": "minutes"},
    )

    result = trigger_block.run({"schedule_id": schedule["id"]}, {})

    assert result["status"] == "ok"
    history = result["data"]
    assert history["status"] == "completed"
    execution = scheduler._durable_execution_store().require(
        history["execution_id"]
    )
    assert execution["status"] == "completed"
    assert execution["result"] == "done"
    assert execution["completed_at"]
    assert scheduler._durable_execution_store().active_for_schedule(
        schedule["id"]
    ) is None
    persisted = load_schedule(schedule["id"])
    assert "running_execution" not in persisted
    assert persisted["execution_count"] == 1
    assert persisted["last_execution_status"] == "completed"


def test_restart_fails_queued_start_once_and_allows_retry() -> None:
    """A crash after reservation leaves one failed record, not a stuck marker."""
    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {"message": "heartbeat", "model": "stub/default"},
        {"value": 30, "unit": "minutes"},
    )
    execution_id = "sexec_crash_before_start"
    scheduler._reserve_durable_execution(
        schedule_id=schedule["id"],
        execution_id=execution_id,
        sched=schedule,
        trigger="manual",
        timeout_seconds=300,
    )
    scheduler.shutdown()
    Scheduler._instance = None

    restarted = Scheduler()
    restarted.ensure_loaded()

    record = restarted._durable_execution_store().require(execution_id)
    assert record["status"] == "failed"
    assert record["error"] == "scheduler restarted before model invocation"
    assert restarted._durable_execution_store().active_for_schedule(
        schedule["id"]
    ) is None
    entries, total = load_history(schedule["id"])
    assert total == 1
    assert entries[0]["execution_id"] == execution_id
    assert entries[0]["recovered_queued_execution"] is True

    restarted.shutdown()
    Scheduler._instance = None
    restarted_again = Scheduler()
    restarted_again.ensure_loaded()
    _, total_after_second_restart = load_history(schedule["id"])
    assert total_after_second_restart == 1


def test_restart_replays_terminal_ledger_before_clearing_projection() -> None:
    """A crash after SQLite settlement cannot leave a terminal run projected active."""
    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {"message": "heartbeat", "model": "stub/default"},
        {"value": 30, "unit": "minutes"},
    )
    execution_id = "sexec_crash_after_settlement"
    scheduler._reserve_durable_execution(
        schedule_id=schedule["id"],
        execution_id=execution_id,
        sched=schedule,
        trigger="manual",
        timeout_seconds=300,
    )
    scheduler._mark_schedule_running(
        schedule["id"], execution_id, "2026-08-24T00:00:00Z", "manual", 300
    )
    scheduler._durable_execution_store().complete(execution_id, result="done")
    scheduler.shutdown()
    Scheduler._instance = None

    restarted = Scheduler()
    restarted.ensure_loaded()

    persisted = load_schedule(schedule["id"])
    assert "running_execution" not in persisted
    assert persisted["execution_count"] == 1
    assert persisted["last_execution_status"] == "completed"
    entries, total = load_history(schedule["id"])
    assert total == 1
    assert entries[0]["execution_id"] == execution_id
    assert entries[0]["recovered_terminal_execution"] is True

    restarted.shutdown()
    Scheduler._instance = None
    restarted_again = Scheduler()
    restarted_again.ensure_loaded()
    _, second_total = load_history(schedule["id"])
    assert second_total == 1
    assert load_schedule(schedule["id"])["execution_count"] == 1


def test_task_update_before_model_boundary_cancels_captured_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker may not invoke a task after its reserved revision is superseded."""
    model_called = False
    scheduler = Scheduler()
    schedule = scheduler.create_schedule(
        "interval",
        {"message": "old privileged input", "model": "stub/default"},
        {"value": 30, "unit": "minutes"},
    )
    original_mark_running = scheduler._mark_schedule_running

    def mark_then_update(*args, **kwargs):
        original_mark_running(*args, **kwargs)
        scheduler.update_schedule(
            schedule["id"], {"task": {"message": "replacement input"}}
        )

    def unexpected_model_call(payload, context):
        nonlocal model_called
        model_called = True
        raise AssertionError("superseded input must not reach model.invoke")

    monkeypatch.setattr(scheduler, "_mark_schedule_running", mark_then_update)
    monkeypatch.setattr("blocks.ai.complete.run", unexpected_model_call)

    result = trigger_block.run({"schedule_id": schedule["id"]}, {})

    assert result["status"] == "error"
    assert result["_http_status"] == 409
    assert result["data"]["cause_code"] == "SCHEDULE_EXECUTION_SUPERSEDED"
    assert not model_called
    history = result["data"]["history_entry"]
    record = scheduler._durable_execution_store().require(history["execution_id"])
    assert record["status"] == "cancelled"
    assert record["error"] == "execution_input_changed"
    assert scheduler._durable_execution_store().active_for_schedule(
        schedule["id"]
    ) is None


def test_scheduler_honors_explicit_execution_database_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scheduler uses the same explicit pack-local ledger override as the store."""
    explicit_path = tmp_path / "ledger" / "executions.sqlite3"
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_SCHEDULE_EXECUTION_DB_PATH", str(explicit_path)
    )

    scheduler = Scheduler()
    scheduler.ensure_loaded()

    assert scheduler._durable_execution_store().db_path == explicit_path.absolute()
    assert explicit_path.is_file()
