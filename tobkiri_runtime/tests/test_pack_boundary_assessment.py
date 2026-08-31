from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.quality.check_pack_boundary_assessment import (
    ASSESSMENT_PATH,
    discover_pack_manifests,
    find_runtime_references,
    validate_assessment,
)

pytestmark = pytest.mark.contract
REPO_ROOT = Path(__file__).resolve().parents[2]


def _payload() -> dict[str, object]:
    return json.loads(ASSESSMENT_PATH.read_text(encoding="utf-8"))


def test_assessment_is_non_runtime_and_matches_discovered_manifests() -> None:
    payload = _payload()

    assert payload["runtime_authority"] is False
    assert payload["activation_input"] is False
    assert validate_assessment(payload, REPO_ROOT) == []
    assert len(payload["records"]) == len(discover_pack_manifests(REPO_ROOT))


@pytest.mark.parametrize("field", ["runtime_authority", "activation_input"])
def test_assessment_rejects_runtime_authority(field: str) -> None:
    payload = _payload()
    payload[field] = True

    assert any(field in error for error in validate_assessment(payload, REPO_ROOT))


def test_assessment_detects_manifest_drift() -> None:
    payload = _payload()
    manifests = discover_pack_manifests(REPO_ROOT)

    errors = validate_assessment(payload, REPO_ROOT, manifests=manifests[:-1])

    assert any("stale manifest rows" in error for error in errors)


def test_accepted_rows_cannot_retain_unknown_ownership() -> None:
    payload = copy.deepcopy(_payload())
    row = payload["records"][0]
    row["review_status"] = "accepted"

    errors = validate_assessment(payload, REPO_ROOT)

    assert any(
        "accepted row has unresolved lifecycle_owner" in error for error in errors
    )


def test_removal_phase_requires_aliases_and_removal_disposition() -> None:
    payload = copy.deepcopy(_payload())
    row = payload["records"][0]
    row["removal_phase"] = "phase-2"

    errors = validate_assessment(payload, REPO_ROOT)

    assert any("removal_phase requires deprecated_ids" in error for error in errors)
    assert any(
        "removal_phase requires a removal disposition" in error for error in errors
    )


def test_production_runtime_does_not_consume_assessment() -> None:
    assert find_runtime_references(REPO_ROOT) == []
