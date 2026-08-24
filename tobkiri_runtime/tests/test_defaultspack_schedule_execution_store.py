"""Focused tests for the pack-local durable scheduled execution ledger."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.agent.schedule_execution_store import (  # noqa: E402
    ACTIVE_SCHEDULE_EXECUTION_STATES,
    CANCELLED,
    COMPLETED,
    FAILED,
    RUNNING,
    TIMED_OUT,
    WAITING_APPROVAL,
    ScheduleExecutionAlreadyActive,
    ScheduleExecutionIdempotencyConflict,
    ScheduleExecutionStore,
    ScheduleExecutionTransitionError,
)


def _store(path: Path) -> ScheduleExecutionStore:
    """Create a store with deterministic timestamps for transition checks."""

    return ScheduleExecutionStore(path, clock=lambda: "2026-08-23T00:00:00Z")


def _reserve(store: ScheduleExecutionStore, **overrides: object) -> dict[str, object]:
    """Reserve the common test request with optional field overrides."""

    request: dict[str, object] = {
        "schedule_id": "schedule-1",
        "idempotency_key": "request-1",
        "expected_revision": 3,
        "input_fingerprint": "input-fingerprint-1",
    }
    request.update(overrides)
    return store.reserve(**request)


def test_transitions_are_deterministic_and_settlement_is_atomic(tmp_path: Path) -> None:
    """Legal transitions work while illegal transitions leave the row unchanged."""

    store = _store(tmp_path / "schedule-executions.sqlite3")
    queued = _reserve(store)
    assert queued["status"] == "queued"
    assert store.list_active()[0]["execution_id"] == queued["execution_id"]

    running = store.transition(
        str(queued["execution_id"]), RUNNING, now="2026-08-23T00:01:00Z"
    )
    assert running["status"] == RUNNING
    assert running["started_at"] == "2026-08-23T00:01:00Z"

    store.transition(
        str(queued["execution_id"]),
        WAITING_APPROVAL,
        now="2026-08-23T00:02:00Z",
    )
    with pytest.raises(ScheduleExecutionTransitionError):
        store.transition(str(queued["execution_id"]), COMPLETED)
    assert store.get(str(queued["execution_id"]))["status"] == WAITING_APPROVAL

    resumed = store.resume_after_approval(
        schedule_id="schedule-1",
        idempotency_key="request-1",
        now="2026-08-23T00:03:00Z",
    )
    assert resumed["execution_id"] == queued["execution_id"]
    assert resumed["status"] == RUNNING

    settled = store.settle(
        str(queued["execution_id"]),
        COMPLETED,
        result={"answer": 42},
        now="2026-08-23T00:04:00Z",
    )
    assert settled["status"] == COMPLETED
    assert settled["result"] == {"answer": 42}
    assert settled["error"] is None
    assert settled["completed_at"] == "2026-08-23T00:04:00Z"
    assert store.list_active() == []


def test_exact_duplicate_replays_and_identity_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    """Retries replay one row and cannot silently change its request identity."""

    store = _store(tmp_path / "schedule-executions.sqlite3")
    first = _reserve(store)
    duplicate = _reserve(store)
    assert duplicate == first

    with pytest.raises(ScheduleExecutionIdempotencyConflict):
        _reserve(store, input_fingerprint="different-input")
    with pytest.raises(ScheduleExecutionIdempotencyConflict):
        _reserve(store, expected_revision=4)


def test_concurrent_reservations_allow_one_active_execution_per_schedule(
    tmp_path: Path,
) -> None:
    """SQLite's active partial index protects the invariant under contention."""

    store = _store(tmp_path / "schedule-executions.sqlite3")

    def reserve(index: int) -> str:
        try:
            result = _reserve(
                store,
                idempotency_key=f"request-{index}",
                input_fingerprint=f"fingerprint-{index}",
            )
        except ScheduleExecutionAlreadyActive:
            return "conflict"
        return str(result["execution_id"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(reserve, range(16)))

    created = [outcome for outcome in outcomes if outcome != "conflict"]
    assert len(created) == 1
    active = store.list_active(schedule_id="schedule-1")
    assert len(active) == 1
    assert active[0]["status"] in ACTIVE_SCHEDULE_EXECUTION_STATES


@pytest.mark.parametrize("terminal_status", [COMPLETED, FAILED, CANCELLED, TIMED_OUT])
def test_active_projection_is_zero_or_one_after_every_transition(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    """Crash-boundary state transitions never expose two active executions."""
    store = _store(tmp_path / terminal_status / "schedule-executions.sqlite3")
    queued = _reserve(store)
    assert len(store.list_active(schedule_id="schedule-1")) == 1
    store.transition(str(queued["execution_id"]), RUNNING)
    assert len(store.list_active(schedule_id="schedule-1")) == 1
    store.transition(str(queued["execution_id"]), WAITING_APPROVAL)
    assert len(store.list_active(schedule_id="schedule-1")) == 1
    store.resume_after_approval(str(queued["execution_id"]))
    assert len(store.list_active(schedule_id="schedule-1")) == 1
    store.settle(
        str(queued["execution_id"]),
        terminal_status,
        result={"terminal": terminal_status},
        error=None if terminal_status == COMPLETED else terminal_status,
    )
    assert store.list_active(schedule_id="schedule-1") == []


def test_approval_resume_and_terminal_state_survive_restart(tmp_path: Path) -> None:
    """A new store instance can resume and settle a persisted execution."""

    database = tmp_path / "nested" / "schedule-executions.sqlite3"
    first_store = _store(database)
    queued = _reserve(first_store)
    first_store.transition(str(queued["execution_id"]), RUNNING)
    first_store.transition(str(queued["execution_id"]), WAITING_APPROVAL)

    restarted = _store(database)
    resumed = restarted.resume_after_approval(str(queued["execution_id"]))
    assert resumed["execution_id"] == queued["execution_id"]
    completed = restarted.complete(
        str(queued["execution_id"]), {"ok": True}, now="2026-08-23T00:05:00Z"
    )
    assert completed["status"] == COMPLETED

    restarted_again = _store(database)
    persisted = restarted_again.require(str(queued["execution_id"]))
    assert persisted["result"] == {"ok": True}
    assert persisted["completed_at"] == "2026-08-23T00:05:00Z"
    assert restarted_again.project_active({"id": "schedule-1"}) == {
        "id": "schedule-1"
    }


def test_input_and_path_validation_fails_closed(tmp_path: Path) -> None:
    """Identifiers, revisions, fingerprints, payloads, and paths are checked."""

    with pytest.raises(ValueError, match="directory"):
        ScheduleExecutionStore(tmp_path)
    store = _store(tmp_path / "schedule-executions.sqlite3")
    with pytest.raises(ValueError, match="schedule_id"):
        store.reserve("../outside", "request-1", 0, "fingerprint")
    with pytest.raises(ValueError, match="expected_revision"):
        store.reserve("schedule-1", "request-1", -1, "fingerprint")
    with pytest.raises(ValueError, match="input_fingerprint"):
        store.reserve("schedule-1", "request-1", 0, "not a fingerprint")
    with pytest.raises(ValueError, match="JSON serializable"):
        store.reserve(
            "schedule-1",
            "request-1",
            0,
            input_data={"not-json": object()},
        )
