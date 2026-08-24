from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.agent.scheduler import trigger as trigger_block  # noqa: E402


def test_manual_startup_failure_returns_http_error_with_durable_history(
    monkeypatch,
) -> None:
    history = {
        "execution_id": "sexec_failed",
        "schedule_id": "sched_test",
        "trigger": "manual",
        "status": "error",
        "error": "Conversation not found",
        "error_code": "NOT_FOUND",
    }

    class FakeScheduler:
        def trigger_now(self, schedule_id: str) -> dict[str, object]:
            assert schedule_id == "sched_test"
            return history

    monkeypatch.setattr(trigger_block, "Scheduler", FakeScheduler)

    result = trigger_block.run({"schedule_id": "sched_test"}, {})

    assert result["status"] == "error"
    assert result["error"]["code"] == "SCHEDULE_TRIGGER_FAILED"
    assert result["_http_status"] == 409
    assert result["data"]["history_entry"] == history
    assert result["data"]["cause_code"] == "NOT_FOUND"


def test_manual_provider_startup_failure_is_not_wrapped_as_success(
    monkeypatch,
) -> None:
    history = {
        "execution_id": "sexec_failed",
        "schedule_id": "sched_test",
        "trigger": "manual",
        "status": "error",
        "error": "provider unavailable",
        "error_code": "PROVIDER_UNAVAILABLE",
    }

    class FakeScheduler:
        def trigger_now(self, schedule_id: str) -> dict[str, object]:
            return history

    monkeypatch.setattr(trigger_block, "Scheduler", FakeScheduler)

    result = trigger_block.run({"schedule_id": "sched_test"}, {})

    assert result["status"] == "error"
    assert result["_http_status"] == 500
    assert result["data"]["history_entry"] == history


def test_scheduled_or_successful_manual_result_keeps_success_envelope(
    monkeypatch,
) -> None:
    history = {
        "execution_id": "sexec_complete",
        "schedule_id": "sched_test",
        "trigger": "manual",
        "status": "completed",
        "result": "done",
    }

    class FakeScheduler:
        def trigger_now(self, schedule_id: str) -> dict[str, object]:
            return history

    monkeypatch.setattr(trigger_block, "Scheduler", FakeScheduler)

    result = trigger_block.run({"schedule_id": "sched_test"}, {})

    assert result == {"status": "ok", "data": history}
