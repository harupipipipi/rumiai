from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _reset_defaultspack_singletons() -> None:
    from domain.agent.scheduler import Scheduler
    from domain.chat.store import ChatStore

    scheduler = Scheduler._instance
    if scheduler is not None:
        for schedule_id in list(getattr(scheduler, "_timers", {}).keys()):
            scheduler._cancel_timer(schedule_id)
    Scheduler._instance = None
    ChatStore._instance = None


def _future_once_config() -> dict[str, str]:
    return {"run_at": "2099-01-01T00:00:00Z"}


def test_scheduler_passes_task_timeout_to_chat_payload_and_context(tmp_path, monkeypatch):
    from blocks.chat import send as chat_send
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    seen: dict[str, dict] = {}

    def fake_chat_send(input_data, context):
        seen["input_data"] = input_data
        seen["context"] = context
        return {"status": "ok", "data": {"content": "done"}}

    monkeypatch.setattr(chat_send, "run", fake_chat_send)
    schedule = Scheduler().create_schedule(
        "once",
        {
            "message": "scheduled chat",
            "conversation_id": "conv-timeout-propagation",
            "timeout": 12.5,
            "tool_policy": {"tool_allowlist": ["todo"]},
            "thinking_level": "high",
        },
        _future_once_config(),
    )

    try:
        result = Scheduler().trigger_now(schedule["id"])

        assert result["status"] == "completed"
        params = seen["input_data"]["params"]
        assert params["request_timeout"] == 12.5
        assert params["timeout"] == 12.5
        assert params["tool_policy"] == {"tool_allowlist": ["todo"]}
        assert params["thinking_level"] == "high"
        assert seen["context"]["profile_policy"] == {"tool_allowlist": ["todo"]}
        assert seen["context"]["schedule_timeout_seconds"] == 12.5
        assert seen["input_data"]["message"]["metadata"]["source"] == "scheduler"
        assert seen["input_data"]["message"]["metadata"]["schedule_id"] == schedule["id"]
    finally:
        Scheduler().delete_schedule(schedule["id"])
        _reset_defaultspack_singletons()


def test_provider_request_planning_keeps_timeout_params():
    from domain.ai_client.request_planner import plan_model_request
    from domain.chat.ir import RumiChatIR, RumiIRMessage
    from domain.chat.ir_blocks import RumiIRBlock

    planned = plan_model_request(
        RumiChatIR(
            conversation_id="conv-provider-timeout",
            messages=[
                RumiIRMessage(
                    role="user",
                    content=[RumiIRBlock(type="text", text="scheduled provider payload")],
                )
            ],
        ),
        "stub/default",
        {
            "supported_roles": ["system", "user", "assistant", "tool"],
            "supported_content_blocks": ["text"],
            "supports_tool_calling": True,
            "supports_parallel_tool_calls": True,
        },
        [],
        {"request_timeout": 19, "timeout": 19},
        {"run_source": "scheduler"},
    )

    assert planned.params["request_timeout"] == 19
    assert planned.params["timeout"] == 19


def test_scheduler_passes_task_timeout_to_direct_ai_payload(tmp_path, monkeypatch):
    from blocks.ai import complete as ai_complete
    from domain.agent.scheduler import Scheduler

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    seen: dict[str, dict] = {}

    def fake_ai_complete(input_data, context):
        seen["input_data"] = input_data
        seen["context"] = context
        return {"status": "ok", "data": {"content": "done"}}

    monkeypatch.setattr(ai_complete, "run", fake_ai_complete)
    schedule = Scheduler().create_schedule(
        "once",
        {"message": "scheduled ai", "model": "stub/default", "timeout": 7},
        _future_once_config(),
    )

    try:
        result = Scheduler().trigger_now(schedule["id"])

        assert result["status"] == "completed"
        assert seen["input_data"]["params"] == {"request_timeout": 7.0, "timeout": 7.0}
        assert seen["context"] == {}
    finally:
        Scheduler().delete_schedule(schedule["id"])
        _reset_defaultspack_singletons()


def test_scheduler_timeout_cancels_chat_and_records_timeout_history(tmp_path, monkeypatch):
    from blocks.chat import send as chat_send
    from domain.agent.scheduler import Scheduler
    from domain.chat.cancellation import get_chat_cancellation_registry

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    conversation_id = "conv-scheduler-timeout"
    registry = get_chat_cancellation_registry()
    registry.unregister(conversation_id)
    entered = threading.Event()

    def cancellable_chat_send(input_data, context):
        del input_data, context
        entered.set()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if registry.is_cancelled(conversation_id):
                return {
                    "status": "error",
                    "error": {"code": "CANCELLED", "message": "cancelled by schedule timeout"},
                }
            time.sleep(0.005)
        return {"status": "ok", "data": {"content": "late"}}

    monkeypatch.setattr(chat_send, "run", cancellable_chat_send)
    schedule = Scheduler().create_schedule(
        "once",
        {
            "message": "slow scheduled chat",
            "conversation_id": conversation_id,
            "timeout": 0.05,
        },
        _future_once_config(),
    )

    try:
        started = time.monotonic()
        result = Scheduler().trigger_now(schedule["id"])
        elapsed = time.monotonic() - started
        history = Scheduler().get_history(schedule["id"])["entries"]

        assert entered.is_set()
        assert elapsed < 0.5
        assert result["status"] == "timeout"
        assert result["timed_out"] is True
        assert result["timeout_seconds"] == 0.05
        assert result["error"] == "cancelled by schedule timeout"
        assert history[0]["execution_id"] == result["execution_id"]
        assert history[0]["status"] == "timeout"
    finally:
        registry.unregister(conversation_id)
        Scheduler().delete_schedule(schedule["id"])
        _reset_defaultspack_singletons()


def test_scheduler_records_timeout_when_chat_run_does_not_cooperate(tmp_path, monkeypatch):
    from blocks.chat import send as chat_send
    from domain.agent.scheduler import Scheduler
    from domain.chat.cancellation import get_chat_cancellation_registry

    _reset_defaultspack_singletons()
    monkeypatch.chdir(tmp_path)
    conversation_id = "conv-noncooperative-timeout"
    registry = get_chat_cancellation_registry()
    registry.unregister(conversation_id)
    release = threading.Event()
    finished = threading.Event()

    def blocked_chat_send(input_data, context):
        del input_data, context
        try:
            release.wait(1.0)
            return {"status": "ok", "data": {"content": "late"}}
        finally:
            finished.set()

    monkeypatch.setattr(chat_send, "run", blocked_chat_send)
    schedule = Scheduler().create_schedule(
        "once",
        {
            "message": "blocked scheduled chat",
            "conversation_id": conversation_id,
            "timeout": 0.03,
        },
        _future_once_config(),
    )

    try:
        started = time.monotonic()
        result = Scheduler().trigger_now(schedule["id"])
        elapsed = time.monotonic() - started
        history = Scheduler().get_history(schedule["id"])["entries"]

        assert elapsed < 0.3
        assert registry.is_cancelled(conversation_id) is True
        assert result["status"] == "timeout"
        assert result["error"] == "Scheduled conversation timed out after 0.03 seconds"
        assert history[0]["status"] == "timeout"
    finally:
        release.set()
        finished.wait(1.0)
        registry.unregister(conversation_id)
        Scheduler().delete_schedule(schedule["id"])
        _reset_defaultspack_singletons()


def test_chat_send_reports_cancelled_engine_runs(monkeypatch):
    from blocks.chat import send as chat_send
    from domain.chat import stream_engine

    class CancelledEngine:
        def stream(self, input_data, context, *, stream_mode=True):
            del input_data, context, stream_mode
            yield {
                "type": "cancelled",
                "data": {"reason": "schedule_timeout"},
                "reason": "schedule_timeout",
            }

    monkeypatch.setattr(stream_engine, "ChatRunEngine", CancelledEngine)

    result = chat_send.run(
        {"conversation_id": "conv-cancelled", "message": {"content": "stop"}},
        {},
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "CANCELLED"
    assert result["error"]["message"] == "Chat run cancelled: schedule_timeout"
