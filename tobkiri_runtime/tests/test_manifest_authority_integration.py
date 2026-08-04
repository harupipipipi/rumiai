"""Repository gates for classified Pack authority and production loading."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import backend_core.ecosystem.registry as registry_module
import core_runtime.manifest_authority as authority_module
from backend_core.ecosystem.registry import Registry
from backend_core.ecosystem.spec.schema.validator import validate_ecosystem
from core_runtime.function_registry import FunctionRegistry
from core_runtime.capability_binding_registration import (
    register_pack_binding_handlers,
)
from core_runtime.global_contracts.manifest import load_manifest
from core_runtime.manifest_authority import (
    ManifestAuthorityError,
    load_manifest_authority_catalog,
    validate_repository_manifest_authority,
)
from core_runtime.manifest_projection import (
    ManifestProjectionError,
    generate_legacy_ecosystem_projection,
    project_legacy_ecosystem,
    source_manifest_identity,
)
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.pack_artifact_integrity import verify_declared_artifacts
from core_runtime.resolved_profile import ResolutionInput, resolve_profile

ROOT = Path(__file__).resolve().parents[1]
ECOSYSTEM = ROOT / "ecosystem"


class _Container:
    def __init__(self, registry: FunctionRegistry) -> None:
        self.registry = registry

    def get_or_none(self, name: str):
        return self.registry if name == "function_registry" else None


class _Approved:
    def is_pack_approved_and_verified(self, pack_id: str):
        return (True, None)


def test_every_repository_pack_has_one_explicit_authority() -> None:
    catalog = load_manifest_authority_catalog()

    validate_repository_manifest_authority(ECOSYSTEM)
    assert len(catalog) == 141
    assert list(catalog.values()).count("v3-authoritative") == 95
    assert list(catalog.values()).count("legacy-authoritative") == 46
    assert list(catalog.values()).count("modern-only") == 0


def test_all_authoritative_manifests_and_projections_are_valid() -> None:
    catalog = load_manifest_authority_catalog()

    for pack_id, authority in sorted(catalog.items()):
        pack_root = ECOSYSTEM / pack_id
        ecosystem_path = pack_root / "ecosystem.json"
        ecosystem = json.loads(ecosystem_path.read_text(encoding="utf-8"))
        assert validate_ecosystem(ecosystem, raise_on_error=False) == [], pack_id
        integrity_ok, integrity_diagnostics = verify_declared_artifacts(
            pack_root,
            ecosystem,
        )
        assert integrity_ok, (pack_id, integrity_diagnostics)
        v3_path = pack_root / "rumi.pack.v3.json"
        if authority == "v3-authoritative":
            loaded = load_manifest(v3_path)
            assert loaded.ok, (pack_id, loaded.diagnostics)
            canonical = json.loads(v3_path.read_text(encoding="utf-8"))
            compatibility = canonical["extensions"]["rumi.legacy_projection"]["manifest"]
            assert project_legacy_ecosystem(canonical) == ecosystem
            generate_legacy_ecosystem_projection(
                v3_path,
                ecosystem_path,
                check=True,
            )
            assert ecosystem["metadata"]["read_only_projection"] is True
            assert ecosystem["metadata"]["generated_from"][
                "source_content_hash"
            ] == source_manifest_identity(canonical)
            for key, value in compatibility.get("metadata", {}).items():
                assert ecosystem["metadata"][key] == value
        else:
            assert not v3_path.exists()


def test_projection_and_artifact_tamper_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pack_id = "rumi_conversation_store_pack"
    source_root = ECOSYSTEM / pack_id
    copied_ecosystem = tmp_path / "ecosystem"
    copied_root = copied_ecosystem / pack_id
    shutil.copytree(source_root, copied_root)
    v3_path = copied_root / "rumi.pack.v3.json"
    ecosystem_path = copied_root / "ecosystem.json"

    ecosystem_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ManifestProjectionError, match="drift"):
        generate_legacy_ecosystem_projection(v3_path, ecosystem_path, check=True)

    shutil.copy2(source_root / "ecosystem.json", ecosystem_path)
    ecosystem = json.loads(ecosystem_path.read_text(encoding="utf-8"))
    artifact_index = copied_root / "artifact-manifest.json"
    artifact_index.write_text('{"artifacts": []}\n', encoding="utf-8")
    monkeypatch.setattr(
        "core_runtime.pack_artifact_integrity.ECOSYSTEM_DIR",
        copied_ecosystem,
    )
    integrity_ok, diagnostics = verify_declared_artifacts(
        copied_root,
        ecosystem,
    )
    assert integrity_ok is False
    assert "artifact manifest hash does not match provenance" in diagnostics


def test_classified_registry_rejects_a_malformed_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ecosystem_dir = tmp_path / "ecosystem"
    pack_root = ecosystem_dir / "broken_pack"
    pack_root.mkdir(parents=True)
    (pack_root / "ecosystem.json").write_text("{", encoding="utf-8")
    catalog_path = tmp_path / "manifest_authority.v1.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": 1,
                "packs": {"broken_pack": "legacy-authoritative"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(authority_module, "CATALOG_PATH", catalog_path)
    monkeypatch.setattr(registry_module, "_ECOSYSTEM_DIR", str(ecosystem_dir))
    load_manifest_authority_catalog.cache_clear()
    try:
        with pytest.raises(ManifestAuthorityError, match="failed to load"):
            Registry(str(ecosystem_dir)).load_all_packs()
    finally:
        load_manifest_authority_catalog.cache_clear()


def test_registry_loads_all_classified_packs_and_host_mediators() -> None:
    function_registry = FunctionRegistry()
    with patch(
        "core_runtime.di_container.get_container",
        return_value=_Container(function_registry),
    ):
        packs = Registry().load_all_packs()

    assert len(packs) == 141
    assert "rumi_model_evals_pack" in packs
    assert function_registry.get("rumi_host_capabilities_pack:host_permission_status") is not None
    assert (
        function_registry.get("rumi_host_capabilities_pack:host_permission_open_settings")
        is not None
    )


def test_invalid_v3_manifest_is_not_available_or_effective(tmp_path: Path) -> None:
    pack_root = tmp_path / "ecosystem" / "invalid_pack"
    pack_root.mkdir(parents=True)
    ecosystem = {
        "pack_id": "invalid_pack",
        "pack_identity": "local:invalid_pack",
        "version": "1.0.0",
        "vocabulary": {"types": ["service"]},
        "dependencies": {},
    }
    (pack_root / "ecosystem.json").write_text(json.dumps(ecosystem), encoding="utf-8")
    example = json.loads(
        (ROOT / "examples" / "pack_v3" / "minimal_service.json").read_text(encoding="utf-8")
    )
    example["unknown_authority"] = True
    (pack_root / "rumi.pack.v3.json").write_text(json.dumps(example), encoding="utf-8")
    resolution_input = ResolutionInput(
        profile_id="invalid-v3",
        profile_revision="1",
        platform="test",
        policy_revision="1",
        lockfile_revision=None,
        requested_pack_ids=("invalid_pack",),
        authorized_pack_ids=("invalid_pack",),
        healthy_pack_ids=("invalid_pack",),
    )

    plan = resolve_profile(
        resolution_input,
        ecosystem_dir=tmp_path / "ecosystem",
    )

    assert plan.available_pack_ids == ()
    assert plan.effective_pack_set == ()
    assert any(item.code == "invalid_manifest" for item in plan.diagnostics)


def test_model_evals_binding_is_explicitly_unavailable_without_host_gate(
    monkeypatch,
) -> None:
    monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)

    result = register_pack_binding_handlers(
        interface_registry=InterfaceRegistry(),
        approval_manager=_Approved(),
        effective_pack_ids=("rumi_model_evals_pack",),
    )

    assert result.registered == []
    assert result.skipped == ["rumi_model_evals_pack"]
    assert any(item["code"] == "v3_python_host_execution_required" for item in result.diagnostics)
