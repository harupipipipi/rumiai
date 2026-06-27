from __future__ import annotations

import sys
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


def _approval_required_response(approval, *, conversation_id: str, tool_name: str = "browser_use") -> dict:
    arguments = {
        "url": "http://127.0.0.1:8766/chat",
        "profile_id": "default",
        "persistent": True,
        "target_app": "",
    }
    request = approval.create_approval_request(
        "browser.open_url",
        "high",
        arguments,
        details={
            "tool_name": tool_name,
            "action": "browser.open_url",
            "function_id": "browser.open_url",
            "pack_id": "defaultspack",
            "conversation_id": conversation_id,
            "arguments": arguments,
        },
    )
    pending = {
        "tool_name": tool_name,
        "tool_call_id": "call_browser_open",
        "action": "browser.open_url",
        "operation": "browser.open_url",
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
