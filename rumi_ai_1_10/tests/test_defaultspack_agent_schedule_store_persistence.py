from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_schedule_history_atomic_write_retries_transient_replace_failure(tmp_path, monkeypatch):
    import domain.agent.schedule_store as schedule_store

    schedules_dir = tmp_path / "schedules"
    history_path = str(schedules_dir / "sched-lock_history.json")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(schedules_dir))
    monkeypatch.setattr(schedule_store.time, "sleep", lambda _seconds: None)
    original_replace = schedule_store.os.replace
    attempts = []

    def flaky_replace(src, dst):
        if dst == history_path and len(attempts) < 2:
            attempts.append(src)
            raise PermissionError("Access is denied")
        return original_replace(src, dst)

    monkeypatch.setattr(schedule_store.os, "replace", flaky_replace)

    schedule_store.append_history(
        "sched-lock",
        {
            "execution_id": "exec-1",
            "started_at": "2026-06-30T01:10:54Z",
            "status": "completed",
        },
    )

    entries, total = schedule_store.load_history("sched-lock")
    assert len(attempts) == 2
    assert total == 1
    assert entries[0]["execution_id"] == "exec-1"
    assert list(schedules_dir.glob(".sched-lock_history.json.*.tmp")) == []


def test_schedule_atomic_write_cleans_tmp_and_preserves_existing_json_on_failure(tmp_path, monkeypatch):
    import domain.agent.schedule_store as schedule_store

    schedules_dir = tmp_path / "schedules"
    schedule_path = str(schedules_dir / "sched-fail.json")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(schedules_dir))
    schedule_store.save_schedule({"id": "sched-fail", "name": "old"})
    original_replace = schedule_store.os.replace

    def fail_replace(src, dst):
        if dst == schedule_path:
            raise OSError("replace failed")
        return original_replace(src, dst)

    monkeypatch.setattr(schedule_store.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        schedule_store.save_schedule({"id": "sched-fail", "name": "new"})

    assert json.loads(Path(schedule_path).read_text(encoding="utf-8")) == {
        "id": "sched-fail",
        "name": "old",
    }
    assert list(schedules_dir.glob(".sched-fail.json.*.tmp")) == []
