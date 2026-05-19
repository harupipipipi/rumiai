from __future__ import annotations

import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.scheduler.create import run as create_job  # noqa: E402
from blocks.scheduler.tick import run as tick_scheduler  # noqa: E402
from domain.scheduler.job_store import SchedulerJobStore  # noqa: E402
from domain.scheduler.schedule_parser import parse_next_run  # noqa: E402


def test_scheduler_creates_job(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SCHEDULER_DIR", str(tmp_path / "scheduler"))

    result = create_job({"name": "check", "kind": "interval", "schedule": "every 30m", "prompt": "hello"}, {})

    assert result["status"] == "ok"
    assert result["data"]["job_id"].startswith("job_")
    assert SchedulerJobStore().get(result["data"]["job_id"])["schedule"] == "every 30m"


def test_scheduler_blocks_no_agent_script_when_shell_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SCHEDULER_DIR", str(tmp_path / "scheduler"))

    created = create_job(
        {
            "name": "script",
            "kind": "one_shot",
            "schedule": "now",
            "no_agent": True,
            "script": ["printf", "scheduler-ok"],
        },
        {},
    )

    assert created["status"] == "error"
    assert created["error"]["code"] == "PERMISSION_DENIED"


def test_scheduler_no_agent_watchdog_tick_with_explicit_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SCHEDULER_DIR", str(tmp_path / "scheduler"))
    config_path = tmp_path / "runtime_config.json"
    config_path.write_text(
        json.dumps(
            {
                "tool_policy": {"allow_shell": True},
                "scheduler": {
                    "allow_no_agent_scripts": True,
                    "no_agent_command_allowlist": [sys.executable],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_RUNTIME_CONFIG_PATH", str(config_path))

    created = create_job(
        {
            "name": "script",
            "kind": "one_shot",
            "schedule": "now",
            "no_agent": True,
            "script": [sys.executable, "-c", "import sys; sys.stdout.write('scheduler-ok')"],
            "timeout_seconds": 5,
        },
        {},
    )
    assert created["status"] == "ok"
    result = tick_scheduler({}, {})

    assert result["status"] == "ok"
    assert result["data"]["count"] == 1
    assert result["data"]["ran"][0]["result"]["stdout"] == "scheduler-ok"
    assert SchedulerJobStore().get(created["data"]["job_id"])["timeout_seconds"] == 5


def test_scheduler_disabled_blocks_create_and_tick(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SCHEDULER_DIR", str(tmp_path / "scheduler"))
    config_path = tmp_path / "runtime_config.json"
    config_path.write_text(json.dumps({"scheduler": {"enabled": False}}), encoding="utf-8")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_RUNTIME_CONFIG_PATH", str(config_path))

    created = create_job({"name": "blocked", "schedule": "now", "prompt": "hello"}, {})
    ticked = tick_scheduler({}, {})

    assert created["status"] == "error"
    assert created["error"]["code"] == "PERMISSION_DENIED"
    assert ticked["status"] == "error"
    assert ticked["error"]["code"] == "PERMISSION_DENIED"


def test_schedule_parser_understands_interval():
    assert parse_next_run("every 1h") > parse_next_run("now")


def test_schedule_parser_understands_one_shot_delay():
    now = datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc)

    assert parse_next_run("in 30m", now=now) == now + timedelta(minutes=30)


def test_schedule_parser_understands_weekly_wall_clock():
    now = datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc)  # Tuesday

    assert parse_next_run("every Monday 09:00", now=now) == datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)


def test_scheduler_tick_sends_due_job_to_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SCHEDULER_DIR", str(tmp_path / "scheduler"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    calls: list[dict] = []

    def fake_send_chat(payload, context):
        calls.append({"payload": payload, "context": context})
        return {"status": "ok", "data": {"id": "assistant-1"}}

    monkeypatch.setattr("blocks.chat.send.run", fake_send_chat)
    created = create_job({"name": "remind", "kind": "one_shot", "schedule": "now", "prompt": "ping", "session_target": "fresh"}, {})

    result = tick_scheduler({}, {})

    assert result["status"] == "ok"
    assert result["data"]["count"] == 1
    assert calls[0]["payload"]["message"]["content"] == "ping"
    assert calls[0]["payload"]["message"]["metadata"]["source"] == "scheduler"
    assert result["data"]["ran"][0]["result"]["conversation_id"]
    assert SchedulerJobStore().get(created["data"]["job_id"])["enabled"] is False
