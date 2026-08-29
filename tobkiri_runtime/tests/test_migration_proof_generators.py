"""Focused tests for independent migration source and proof generators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_executable_source_registry_v1 import (
    ECOSYSTEM,
    ExecutableSourceRegistryError,
    build_registry,
)
from scripts.quality.run_independent_migration_proof import (
    build_proof,
)


def test_source_registry_is_complete_without_v4_catalog_inputs() -> None:
    """Legacy manifests and explicit source records cover all v4 operations."""
    payload = build_registry()
    records = payload["packs"]

    assert payload["source"]["kind"] == "legacy-shaped"
    assert len(records) == 162
    assert sum(len(record["operations"]) for record in records.values()) == 221
    assert all(
        not path.endswith(("pack.v4.json", "contracts.v4.json", "executables.v4.json"))
        for path in payload["source"]["input_paths"]
    )
    for function_id, record in records.items():
        assert record["function_id"] == function_id
        implementation = ECOSYSTEM / record["pack_id"] / record["implementation_path"]
        assert implementation.is_file()


def test_source_registry_rejects_unsafe_explicit_implementation_path(
    tmp_path: Path,
) -> None:
    """An explicit legacy source cannot hash bytes outside its Pack."""
    fixture_path = tmp_path / "legacy-executable-sources.json"
    fixture = json.loads(
        Path("tests/fixtures/legacy_executable_sources.v1.json").read_text(
            encoding="utf-8"
        )
    )
    fixture["packs"]["defaultspack"]["entries"][0]["implementation_path"] = "../escape.py"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ExecutableSourceRegistryError, match="escapes"):
        build_registry(ECOSYSTEM, fixture_path=fixture_path)


def test_independent_proof_preserves_named_identity_and_transactional_receipt() -> None:
    """The proof runner keeps three named users separate through restart."""
    proof = build_proof(observed_head_sha="a" * 40)
    source = proof["source"]
    identity = source["identity_proof"]
    transaction = source["transaction"]

    assert len(proof["packs"]) == 143
    assert identity["all_ids_distinct"] is True
    assert identity["defaults_collapsed"] is False
    assert identity["profile_ids"] == ["profile-aoi", "profile-bora", "profile-cleo"]
    assert transaction["lossless"] is True
    assert transaction["restart_verified"] is True
    assert transaction["replay_rejected_without_mutation"] is True
    assert all(entry["status"] == "release-verified" for entry in proof["packs"].values())
