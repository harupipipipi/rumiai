"""Workflow Pack admission through the official v4 Profile ceremony."""

from __future__ import annotations

from pathlib import Path

from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
from core_runtime.pack_control_v4 import (
    CONTROL_PRESENTATION_CONTRACT,
    PACK_CONTROL_CONTRACT,
    capture_pack_control_session,
)

PACK_ID = "tobkiri_workflow_pack"
SESSION_ID = "workflow-v4-integration"


def _invoke(session, contract: str, operation: str, payload: dict | None = None):
    return session.invoke(
        contract,
        operation,
        {**(payload or {}), "_session_id": SESSION_ID},
    )


def test_optional_workflow_pack_enters_closure_only_after_full_ceremony(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Install, approval, enable, and Profile ceremony select exact v4 bindings."""

    monkeypatch.setenv("TOBKIRI_USER_DATA", str(tmp_path / "user-data"))
    capture_default_profile(confirmation=prepare_default_profile_confirmation())
    session = capture_pack_control_session()

    catalog = _invoke(session, PACK_CONTROL_CONTRACT, "catalog.read")
    workflow = next(item for item in catalog["packs"] if item["pack_id"] == PACK_ID)
    assert workflow == {
        **workflow,
        "required": False,
        "installed": False,
        "approved": False,
        "enabled": False,
    }
    _invoke(session, PACK_CONTROL_CONTRACT, "pack.install", {"pack_id": PACK_ID})
    candidate = _invoke(session, PACK_CONTROL_CONTRACT, "approval.candidate", {"pack_id": PACK_ID})
    _invoke(
        session,
        PACK_CONTROL_CONTRACT,
        "approval.approve",
        {"pack_id": PACK_ID, "candidate_id": candidate["candidate_id"]},
    )
    enabled = _invoke(session, PACK_CONTROL_CONTRACT, "pack.enable", {"pack_id": PACK_ID})
    assert enabled["enabled"] is True

    profile = _invoke(session, CONTROL_PRESENTATION_CONTRACT, "profile.read")
    desired = [
        item["pack_id"]
        for item in profile["data"]["profile_document"]["packs"]
        if item.get("role") != "application"
    ]
    assert PACK_ID in desired
    resolved = _invoke(
        session,
        CONTROL_PRESENTATION_CONTRACT,
        "profile.change.resolve",
        {
            "profile_id": "defaults",
            "expected_profile_revision": profile["profile_revision"],
            "expected_plan_digest": profile["plan_digest"],
            "desired_pack_ids": desired,
        },
    )
    review = resolved["review"]
    assert PACK_ID in {item["pack_id"] for item in review["profile"]["packs"]}
    assert PACK_ID in {item["identity"] for item in review["profile_lock"]["effective_set"]}
    workflow_bindings = [
        item for item in review["resolved_plan"]["bindings"] if item["pack_id"] == PACK_ID
    ]
    assert workflow_bindings
    assert {item["contract_id"] for item in workflow_bindings} == {"tobkiri.workflow.v4"}
    assert {item["function_principal"]["function_id"] for item in workflow_bindings} == {
        "tobkiri.workflow.provider"
    }

    reviewed = _invoke(
        session,
        CONTROL_PRESENTATION_CONTRACT,
        "profile.change.review",
        {
            "candidate_id": resolved["candidate_id"],
            "candidate_digest": resolved["candidate_digest"],
        },
    )
    approved = _invoke(
        session,
        CONTROL_PRESENTATION_CONTRACT,
        "profile.change.approve",
        {
            "candidate_id": reviewed["candidate_id"],
            "candidate_digest": reviewed["candidate_digest"],
        },
    )
    activated = _invoke(
        session,
        CONTROL_PRESENTATION_CONTRACT,
        "profile.change.activate",
        {
            "approval_id": approved["approval_id"],
            "approval_digest": approved["approval_digest"],
        },
    )
    assert activated["state"] == "active"
    assert activated["plan_digest"] == review["resolved_plan"]["plan_digest"]
    status = _invoke(session, PACK_CONTROL_CONTRACT, "pack.status", {"pack_id": PACK_ID})
    assert status["installed"] is True
    assert status["approved"] is True
    assert status["enabled"] is True
