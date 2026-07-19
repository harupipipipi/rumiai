from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR",
        str(tmp_path / "schedules"),
    )
    from domain.agent.scheduler import Scheduler

    Scheduler._instance = None
    instance = Scheduler()
    yield instance
    for schedule_id in list(instance._timers):
        instance._cancel_timer(schedule_id)
    Scheduler._instance = None


def _create(scheduler, mutation_id: str):
    return scheduler.create_schedule(
        "once",
        {
            "message": "Run calendar task",
            "metadata": {
                "source": "calendar",
                "calendar_item_id": "calendar-1",
            },
        },
        {"run_at": "2099-01-01T09:00:00Z"},
        name="Calendar: task",
        mutation_id=mutation_id,
    )


def test_create_retry_returns_the_committed_schedule(scheduler):
    first = _create(scheduler, "calendar-create-1")
    retry = _create(scheduler, "calendar-create-1")

    assert retry["id"] == first["id"]
    assert retry["revision"] == 1
    assert len(scheduler.list_schedules()) == 1


def test_update_requires_revision_and_settles_each_mutation_once(scheduler):
    schedule = _create(scheduler, "calendar-create-1")
    updated = scheduler.update_schedule(
        schedule["id"],
        {
            "name": "Calendar: updated",
            "expected_revision": 1,
            "mutation_id": "calendar-update-1",
        },
    )

    assert updated["revision"] == 2
    assert updated["name"] == "Calendar: updated"
    retry = scheduler.update_schedule(
        schedule["id"],
        {
            "name": "ignored retry payload",
            "expected_revision": 1,
            "mutation_id": "calendar-update-1",
        },
    )
    assert retry["revision"] == 2
    assert retry["name"] == "Calendar: updated"

    with pytest.raises(ValueError, match="revision conflict"):
        scheduler.update_schedule(
            schedule["id"],
            {
                "name": "stale overwrite",
                "expected_revision": 1,
                "mutation_id": "calendar-update-stale",
            },
        )


def test_delete_rejects_a_stale_revision(scheduler):
    schedule = _create(scheduler, "calendar-create-1")
    scheduler.update_schedule(
        schedule["id"],
        {
            "name": "Calendar: updated",
            "expected_revision": 1,
            "mutation_id": "calendar-update-1",
        },
    )

    with pytest.raises(ValueError, match="revision conflict"):
        scheduler.delete_schedule(schedule["id"], expected_revision=1)

    assert scheduler.delete_schedule(schedule["id"], expected_revision=2) is True


def test_concurrent_devices_cannot_both_commit_the_same_revision(scheduler):
    schedule = _create(scheduler, "calendar-create-1")
    barrier = threading.Barrier(3)
    outcomes = []

    def update(name, mutation_id):
        barrier.wait()
        try:
            result = scheduler.update_schedule(
                schedule["id"],
                {"name": name, "expected_revision": 1, "mutation_id": mutation_id},
            )
            outcomes.append(("ok", result["revision"]))
        except ValueError as exc:
            outcomes.append(("conflict", str(exc)))

    threads = [
        threading.Thread(target=update, args=("Device A", "device-a")),
        threading.Thread(target=update, args=("Device B", "device-b")),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sorted(result[0] for result in outcomes) == ["conflict", "ok"]
    assert scheduler.get_schedule(schedule["id"])["revision"] == 2
