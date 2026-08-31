from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.quality.check_pack_boundary_assessment import (
    ASSESSMENT_PATH,
    BOUNDARY_CRITERIA,
    DOCUMENT_ROLE,
    SCHEMA_VERSION,
    discover_pack_locations,
    find_runtime_references,
    render_assessment,
    validate_assessment,
)

pytestmark = pytest.mark.contract
REPO_ROOT = Path(__file__).resolve().parents[2]


def _payload() -> dict[str, object]:
    return json.loads(ASSESSMENT_PATH.read_text(encoding="utf-8"))


def _write_manifest(path: Path, contents: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _accepted_row(payload: dict[str, object]) -> dict[str, object]:
    row = payload["records"][0]
    assert isinstance(row, dict)
    row.update(
        {
            "review_status": "accepted",
            "lifecycle_owner": "runtime-team",
            "state_owner": "runtime-team",
            "external_effects": [],
            "trust_domain": "first-party",
            "execution_mode": "in-process",
            "canonical_owner": "core-runtime",
            "disposition": "keep",
            "boundary_criteria": ["independent_lifecycle"],
            "assessment_justification": "A reviewed lifecycle requires this boundary.",
        }
    )
    evidence = row["evidence"]
    assert isinstance(evidence, list)
    support_path = REPO_ROOT / "tobkiri_runtime/docs/adr/0001-pack-boundary-criteria.md"
    evidence.append(
        {
            "path": support_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": hashlib.sha256(support_path.read_bytes()).hexdigest(),
        }
    )
    return row


def test_assessment_is_non_runtime_and_matches_discovered_manifests() -> None:
    payload = _payload()

    assert payload["runtime_authority"] is False
    assert payload["activation_input"] is False
    assert validate_assessment(payload, REPO_ROOT) == []
    assert len(payload["records"]) == len(discover_pack_locations(REPO_ROOT))
    assert {row["review_status"] for row in payload["records"]} == {"unreviewed"}


def test_discovery_matches_direct_nested_legacy_and_core_runtime_shapes(
    tmp_path: Path,
) -> None:
    root = tmp_path
    _write_manifest(root / "tobkiri_runtime/ecosystem/direct/ecosystem.json")
    _write_manifest(root / "tobkiri_runtime/ecosystem/direct/backend/ecosystem.json")
    _write_manifest(root / "tobkiri_runtime/ecosystem/nested/zeta/ecosystem.json")
    _write_manifest(root / "tobkiri_runtime/ecosystem/nested/alpha/ecosystem.json")
    _write_manifest(
        root / "tobkiri_runtime/ecosystem/packs/legacy/backend/ecosystem.json"
    )
    _write_manifest(root / "tobkiri_runtime/ecosystem/dupe/ecosystem.json")
    _write_manifest(
        root / "tobkiri_runtime/ecosystem/packs/dupe/backend/ecosystem.json"
    )
    _write_manifest(
        root / "tobkiri_runtime/core_runtime/core_pack/core_direct/ecosystem.json"
    )
    _write_manifest(
        root
        / "tobkiri_runtime/core_runtime/core_pack/core_nested/backend/ecosystem.json"
    )

    locations = {
        location.pack_id: location for location in discover_pack_locations(root)
    }

    assert locations["direct"].ecosystem_json_path.name == "ecosystem.json"
    assert locations["direct"].pack_subdir.name == "direct"
    assert locations["nested"].pack_subdir.name == "alpha"
    assert locations["legacy"].is_legacy is True
    assert locations["legacy"].pack_subdir.name == "backend"
    assert locations["dupe"].is_legacy is False
    assert locations["dupe"].ecosystem_json_path.parent.name == "dupe"
    assert locations["core_direct"].is_core is True
    assert locations["core_nested"].is_core is True
    assert locations["core_nested"].pack_subdir.name == "backend"


def test_regeneration_resets_reviewed_rows_when_manifest_evidence_changes(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "tobkiri_runtime/ecosystem/demo/ecosystem.json"
    _write_manifest(manifest, '{"pack_id": "demo"}\n')
    reviewed = render_assessment(tmp_path)
    row = _accepted_row(reviewed)
    support = tmp_path / "tobkiri_runtime/review/demo.md"
    _write_manifest(support, "review evidence\n")
    row["evidence"][1] = {
        "path": support.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(support.read_bytes()).hexdigest(),
    }

    assert (
        render_assessment(tmp_path, reviewed)["records"][0]["review_status"]
        == "accepted"
    )

    _write_manifest(manifest, '{"pack_id": "demo", "changed": true}\n')
    regenerated = render_assessment(tmp_path, reviewed)

    assert regenerated["records"][0]["review_status"] == "unreviewed"
    assert regenerated["records"][0]["assessment_justification"] == ""


@pytest.mark.parametrize("field", ["runtime_authority", "activation_input"])
def test_assessment_rejects_runtime_authority(field: str) -> None:
    payload = _payload()
    payload[field] = True

    assert any(field in error for error in validate_assessment(payload, REPO_ROOT))


def test_accepted_rows_require_adr_criteria_and_justification() -> None:
    payload = copy.deepcopy(_payload())
    row = _accepted_row(payload)
    row["boundary_criteria"] = []
    row["assessment_justification"] = ""

    errors = validate_assessment(payload, REPO_ROOT)

    assert any("accepted row requires boundary_criteria" in error for error in errors)
    assert any(
        "accepted row requires assessment_justification" in error for error in errors
    )


def test_accepted_rows_reject_unknown_criteria() -> None:
    payload = copy.deepcopy(_payload())
    row = _accepted_row(payload)
    row["boundary_criteria"] = ["not-an-adr-criterion"]

    errors = validate_assessment(payload, REPO_ROOT)

    assert BOUNDARY_CRITERIA
    assert any("unsupported boundary_criteria" in error for error in errors)


def test_accepted_rows_require_supporting_evidence_beyond_manifest() -> None:
    payload = copy.deepcopy(_payload())
    row = _accepted_row(payload)
    row["evidence"] = row["evidence"][:1]

    errors = validate_assessment(payload, REPO_ROOT)

    assert any("requires evidence beyond its manifest" in error for error in errors)


def test_evidence_digest_detects_tampering() -> None:
    payload = copy.deepcopy(_payload())
    row = payload["records"][0]
    assert isinstance(row, dict)
    evidence = row["evidence"]
    assert isinstance(evidence, list)
    assert isinstance(evidence[0], dict)
    evidence[0]["sha256"] = "0" * 64

    errors = validate_assessment(payload, REPO_ROOT)

    assert any("sha256 does not match current file" in error for error in errors)


def test_removal_phase_requires_aliases_and_removal_disposition() -> None:
    payload = copy.deepcopy(_payload())
    row = payload["records"][0]
    assert isinstance(row, dict)
    row["removal_phase"] = "phase-2"

    errors = validate_assessment(payload, REPO_ROOT)

    assert any("removal_phase requires deprecated_ids" in error for error in errors)
    assert any(
        "removal_phase requires a removal disposition" in error for error in errors
    )


@pytest.mark.parametrize(
    "path, token",
    [
        (
            "tobkiri_runtime/core_runtime/consumer.py",
            "pack-boundary-assessment.v1.json",
        ),
        ("tobkiri_launcher/src-tauri/tauri.conf.json", SCHEMA_VERSION),
        (".github/workflows/consumer.yml", DOCUMENT_ROLE),
    ],
)
def test_static_non_consumption_guard_detects_production_mutations(
    tmp_path: Path, path: str, token: str
) -> None:
    candidate = tmp_path / path
    _write_manifest(candidate, token)
    _write_manifest(tmp_path / "tobkiri_runtime/docs/ignored.py", token)

    references = find_runtime_references(tmp_path)

    assert references == [f"{path} ({token})"]


def test_production_runtime_does_not_consume_assessment() -> None:
    assert find_runtime_references(REPO_ROOT) == []
