"""Production gates for the one-way Pack v4 artifact migration."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.migrate_pack_artifacts_v4 import (
    CATALOG,
    EXCLUDED_PACKS,
    PackV4MigrationError,
    _render_record,
    _validate_catalog_payload,
    generate,
    verify_rendered_artifacts,
)
from tobkiri_protocol.errors import SchemaValidationError


def _catalog() -> dict[str, object]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_all_non_default_packs_have_valid_deterministic_v4_artifacts() -> None:
    """All 139 owned Packs must match a second byte-identical generation."""
    result = generate(check=True)
    assert result == {
        "packs": 139,
        "valid": 139,
        "contracts": 158,
        "operations": 197,
    }
    payload = _catalog()
    assert payload["excluded_packs"] == sorted(EXCLUDED_PACKS)
    for record in payload["packs"]:
        files = _render_record(record)
        verify_rendered_artifacts(files)
        pack_root = CATALOG.parents[1] / "ecosystem" / record["pack_id"]
        assert {name: (pack_root / name).read_text(encoding="utf-8") for name in files} == files


def test_normal_generation_has_no_v3_or_legacy_authority_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal generation may consume only the canonical v4 source catalog."""
    original = Path.read_text

    def guarded_read(path: Path, *args: object, **kwargs: object) -> str:
        if path.name in {"rumi.pack.v3.json", "ecosystem.json"}:
            raise AssertionError(f"legacy authority read: {path}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert generate(check=True)["valid"] == 139


@pytest.mark.parametrize("failure", ["duplicate", "missing", "unknown", "malformed"])
def test_catalog_rejects_inventory_and_shape_failures(failure: str) -> None:
    """Unknown, missing, duplicate, and malformed source records fail closed."""
    payload = copy.deepcopy(_catalog())
    if failure == "duplicate":
        payload["packs"][-1] = copy.deepcopy(payload["packs"][0])
    elif failure == "missing":
        payload["packs"].pop()
    elif failure == "unknown":
        payload["packs"][-1]["pack_id"] = "unknown_pack"
    else:
        payload["packs"][0].pop("network")
    with pytest.raises(PackV4MigrationError):
        _validate_catalog_payload(payload)


def test_tampered_and_stale_generated_artifacts_fail_closed() -> None:
    """Content tampering and stale integrity seals cannot pass artifact checks."""
    record = _catalog()["packs"][0]
    files = _render_record(record)

    tampered = dict(files)
    manifest = json.loads(tampered["pack.v4.json"])
    manifest["pack"]["display_name"] += " tampered"
    tampered["pack.v4.json"] = json.dumps(manifest, sort_keys=True) + "\n"
    with pytest.raises(PackV4MigrationError, match="digest mismatch"):
        verify_rendered_artifacts(tampered)

    stale = dict(files)
    index = json.loads(stale["artifact-index.v4.json"])
    index["integrity_seal"]["signed_digest"] = "sha256:" + "0" * 64
    stale["artifact-index.v4.json"] = json.dumps(index, sort_keys=True) + "\n"
    with pytest.raises(PackV4MigrationError, match="integrity seal"):
        verify_rendered_artifacts(stale)

    malformed = dict(files)
    malformed["pack.v4.json"] = "{}\n"
    with pytest.raises(SchemaValidationError):
        verify_rendered_artifacts(malformed)


def test_global_catalog_has_no_duplicate_provider_or_operation() -> None:
    """Provider and operation identities are globally qualified and unique."""
    providers: set[str] = set()
    operations: set[str] = set()
    owners: dict[str, str] = {}
    for record in _catalog()["packs"]:
        files = _render_record(record)
        manifest = json.loads(files["pack.v4.json"])
        contracts = json.loads(files["contracts.v4.json"])["contracts"]
        for contract in contracts:
            assert (
                owners.setdefault(contract["contract_id"], contract["owner"]) == contract["owner"]
            )
        for provider in manifest["provider_catalog"]:
            assert provider["provider_id"] not in providers
            providers.add(provider["provider_id"])
        for operation in manifest["operation_catalog"]:
            assert operation["operation_id"] not in operations
            operations.add(operation["operation_id"])
    assert len(providers) == 158
    assert len(operations) == 197
