from __future__ import annotations

import sys
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


def test_scheduler_no_agent_watchdog_tick(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SCHEDULER_DIR", str(tmp_path / "scheduler"))

    create_job(
        {
            "name": "script",
            "kind": "one_shot",
            "schedule": "now",
            "no_agent": True,
            "script": "printf scheduler-ok",
        },
        {},
    )
    result = tick_scheduler({}, {})

    assert result["status"] == "ok"
    assert result["data"]["count"] == 1
    assert result["data"]["ran"][0]["result"]["stdout"] == "scheduler-ok"


def test_schedule_parser_understands_interval():
    assert parse_next_run("every 1h") > parse_next_run("now")
