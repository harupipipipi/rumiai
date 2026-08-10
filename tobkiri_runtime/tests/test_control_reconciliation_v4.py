"""Durability and fail-closed tests for v4 control reconciliation."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from core_runtime.control_reconciliation_v4 import (
    ControlReconciliationError,
    ControlReconciliationStore,
)
from tobkiri_protocol.canonical import canonical_digest


def _begin(
    store: ControlReconciliationStore,
    request_id: str,
    *,
    session_id: str = "session-a",
    request_digest: str | None = None,
):
    return store.begin_operation(
        request_id=request_id,
        session_id=session_id,
        operation_id="profile.change.approve",
        contract_id="tobkiri.host.control-presentation.v4",
        request_digest=request_digest or canonical_digest({"request_id": request_id}),
    )


def test_operation_journal_reconciles_terminal_results_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "control" / "reconciliation-v4.sqlite3"
    first = ControlReconciliationStore(path, instance_id="process-a")
    request_id = "11111111-1111-4111-8111-111111111111"
    pending, created = _begin(first, request_id)
    assert created is True
    assert pending["state"] == "pending"

    result = {
        "state": "approved",
        "approval_id": "approval.profile-change.test",
        "approval_digest": "sha256:" + "1" * 64,
    }
    succeeded = first.finish_operation(
        request_id,
        session_id="session-a",
        state="succeeded",
        result=result,
        record_refs=[
            {
                "record_id": "approval.profile-change.test",
                "record_digest": "sha256:" + "1" * 64,
            }
        ],
    )
    restarted = ControlReconciliationStore(path, instance_id="process-b")
    status = restarted.operation_status(request_id, session_id="session-a")
    replay, created = _begin(restarted, request_id)

    assert created is False
    assert replay == status == succeeded
    assert status["state"] == "succeeded"
    assert status["result"] == result
    assert status["result_digest"] == canonical_digest(result)
    assert status["record_refs"][0]["record_id"] == result["approval_id"]


def test_operation_journal_marks_only_abandoned_pending_work_indeterminate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reconciliation-v4.sqlite3"
    original = ControlReconciliationStore(path, instance_id="process-a")
    pending_id = "22222222-2222-4222-8222-222222222222"
    failed_id = "33333333-3333-4333-8333-333333333333"
    _begin(original, pending_id)
    _begin(original, failed_id)
    original.finish_operation(
        failed_id,
        session_id="session-a",
        state="failed",
        result={"state": "error", "code": "UNAPPROVED"},
        safe_error_code="UNAPPROVED",
    )

    restarted = ControlReconciliationStore(path, instance_id="process-b")
    assert restarted.recover_abandoned_operations() == 1
    pending = restarted.operation_status(pending_id, session_id="session-a")
    failed = restarted.operation_status(failed_id, session_id="session-a")

    assert pending["state"] == "indeterminate"
    assert pending["safe_error_code"] == "PROCESS_RESTART"
    assert failed["state"] == "failed"
    assert failed["safe_error_code"] == "UNAPPROVED"
    assert (
        ControlReconciliationStore(path).operation_status(pending_id, session_id="session-a")
        == pending
    )


def test_operation_status_rejects_unknown_cross_session_and_tampered_replay(
    tmp_path: Path,
) -> None:
    store = ControlReconciliationStore(tmp_path / "reconciliation-v4.sqlite3")
    request_id = "44444444-4444-4444-8444-444444444444"
    digest = canonical_digest({"payload": "exact"})
    _begin(store, request_id, request_digest=digest)

    with pytest.raises(ControlReconciliationError, match="unknown"):
        store.operation_status(
            "55555555-5555-4555-8555-555555555555",
            session_id="session-a",
        )
    with pytest.raises(ControlReconciliationError, match="another session"):
        store.operation_status(request_id, session_id="session-b")
    with pytest.raises(ControlReconciliationError, match="binding changed"):
        _begin(
            store,
            request_id,
            request_digest=canonical_digest({"payload": "tampered"}),
        )

    store.finish_operation(
        request_id,
        session_id="session-a",
        state="succeeded",
        result={"state": "approved"},
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE control_operations SET result_json=? WHERE request_id=?",
            ('{"state":"forged"}', request_id),
        )
    with pytest.raises(ControlReconciliationError, match="digest changed"):
        store.operation_status(request_id, session_id="session-a")
