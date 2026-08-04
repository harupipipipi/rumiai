"""Independent regression contracts for the manifest/loader root fix.

These tests intentionally describe the repository state expected after the
manifest authority migration.  They are kept in a dedicated file so the
production fix can be applied independently of the existing Wave 0 tests.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from backend_core.ecosystem.registry import Registry
from backend_core.ecosystem.spec.schema.validator import (
    SchemaValidationError,
    validate_ecosystem,
)
from core_runtime.capability_binding_registration import (
    register_pack_binding_handlers,
)
from core_runtime.global_contracts.manifest import load_manifest
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.manifest_projection import (
    generate_legacy_ecosystem_projection,
    source_manifest_identity,
)
from core_runtime.paths import discover_pack_locations
from core_runtime.resolved_profile import ResolutionInput, resolve_profile
from core_runtime.function_registry import FunctionRegistry


ROOT = Path(__file__).resolve().parents[1]
ECOSYSTEM = ROOT / "ecosystem"
EXAMPLE_V3 = ROOT / "examples" / "pack_v3" / "minimal_service.json"
MODEL_EVALS_PACK = "rumi_model_evals_pack"
HOST_PACK = "rumi_host_capabilities_pack"


def _authority_module():
    """Import the authority module while keeping the baseline failure useful."""
    try:
        return importlib.import_module("core_runtime.manifest_authority")
    except ModuleNotFoundError as exc:
        pytest.fail(
            "manifest authority catalog/loader is not present at the baseline: "
            f"{exc}"
        )


def _write_legacy_pack(root: Path, pack_id: str) -> Path:
    """Write the smallest schema-valid legacy Pack fixture."""
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "ecosystem.json").write_text(
        json.dumps(
            {
                "pack_id": pack_id,
                "pack_identity": f"local:{pack_id}",
                "version": "1.0.0",
                "vocabulary": {"types": ["service"]},
            }
        ),
        encoding="utf-8",
    )
    return pack_dir


class _RegistryContainer:
    """DI adapter used to observe the single legacy FunctionRegistry path."""

    def __init__(self, function_registry: FunctionRegistry) -> None:
        self.function_registry = function_registry

    def get_or_none(self, name: str):
        """Return the test FunctionRegistry and no unrelated services."""
        if name == "function_registry":
            return self.function_registry
        return None


def _load_legacy_registry() -> tuple[dict[str, object], FunctionRegistry]:
    """Load the repository through the legacy Registry and capture functions."""
    function_registry = FunctionRegistry()
    container = _RegistryContainer(function_registry)
    with patch("core_runtime.di_container.get_container", return_value=container):
        with contextlib.redirect_stdout(io.StringIO()):
            packs = Registry(str(ECOSYSTEM)).load_all_packs()
    return packs, function_registry


def test_repository_authority_catalog_is_exact_and_has_no_loader_gaps() -> None:
    """Every discovered Pack has one explicit authority and a matching loader."""
    authority = _authority_module()
    authority.load_manifest_authority_catalog.cache_clear()
    authority.validate_repository_manifest_authority(ECOSYSTEM)
    catalog = authority.load_manifest_authority_catalog()
    locations = discover_pack_locations(str(ECOSYSTEM))

    assert len(locations) == 141
    assert len(catalog) == 141
    assert set(catalog) == {location.pack_id for location in locations}
    assert set(catalog.values()) == {
        "legacy-authoritative",
        "v3-authoritative",
    }

    for location in locations:
        manifest_path = location.pack_subdir / "ecosystem.json"
        v3_path = location.pack_subdir / "rumi.pack.v3.json"
        pack_authority = catalog[location.pack_id]
        assert manifest_path.is_file()
        if pack_authority == "v3-authoritative":
            assert v3_path.is_file(), location.pack_id
            legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata = legacy.get("metadata", {})
            assert metadata.get("manifest_authority") == "v3-authoritative"
            assert metadata.get("generated") is True
            assert metadata.get("read_only_projection") is True


def test_all_repository_legacy_manifests_validate_without_silent_exclusion() -> None:
    """The authoritative legacy scan must accept all 141 repository manifests."""
    paths = sorted(ECOSYSTEM.glob("*/ecosystem.json"))
    errors: list[str] = []
    for path in paths:
        try:
            validate_ecosystem(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc:
            errors.append(f"{path.parent.name}: {exc}")

    assert len(paths) == 141
    assert not errors, "legacy manifest diagnostics: " + " | ".join(errors[:8])


def test_all_repository_v3_manifests_validate_with_actionable_diagnostics() -> None:
    """Every checked-in v3 manifest must be accepted by the canonical loader."""
    paths = sorted(ECOSYSTEM.glob("*/rumi.pack.v3.json"))
    errors: list[str] = []
    for path in paths:
        result = load_manifest(path)
        if not result.ok:
            errors.append(f"{path.parent.name}: {'; '.join(result.diagnostics)}")

    assert len(paths) == 95
    assert not errors, "v3 manifest diagnostics: " + " | ".join(errors[:8])


def test_legacy_registry_loads_every_pack_and_registers_host_mediators() -> None:
    """Registry loading must retain all Packs and both host mediator Functions."""
    packs, function_registry = _load_legacy_registry()
    locations = discover_pack_locations(str(ECOSYSTEM))

    assert len(packs) == 141
    assert set(packs) == {location.pack_id for location in locations}
    for function_id, permission_id in (
        ("host_permission_status", "host.permission.status"),
        ("host_permission_open_settings", "host.permission.open_settings"),
    ):
        entry = function_registry.get(f"{HOST_PACK}:{function_id}")
        assert entry is not None, function_id
        assert entry.calling_convention == "subprocess"
        assert entry.host_execution is False
        assert permission_id in entry.requires


def test_legacy_registry_hard_fails_invalid_pack_with_concrete_diagnostic(
    tmp_path: Path,
) -> None:
    """An invalid legacy Pack must not be printed-and-skipped."""
    ecosystem_dir = tmp_path / "ecosystem"
    _write_legacy_pack(ecosystem_dir, "valid_pack")
    invalid_dir = _write_legacy_pack(ecosystem_dir, "invalid_pack")
    invalid_manifest = json.loads(
        (invalid_dir / "ecosystem.json").read_text(encoding="utf-8")
    )
    invalid_manifest["vocabulary"]["types"] = []
    (invalid_dir / "ecosystem.json").write_text(
        json.dumps(invalid_manifest),
        encoding="utf-8",
    )

    with pytest.raises(Exception) as raised:
        with contextlib.redirect_stdout(io.StringIO()):
            Registry(str(ecosystem_dir)).load_all_packs()

    diagnostic = str(raised.value)
    assert "invalid_pack" in diagnostic
    assert "vocabulary" in diagnostic.lower()


def test_v3_projection_is_legacy_schema_valid_source_bound_and_deterministic(
    tmp_path: Path,
) -> None:
    """Canonical v3 data owns a deterministic, integrity-bound legacy projection."""
    canonical = tmp_path / "rumi.pack.v3.json"
    output = tmp_path / "ecosystem.json"
    manifest = json.loads(EXAMPLE_V3.read_text(encoding="utf-8"))
    canonical.write_text(EXAMPLE_V3.read_text(encoding="utf-8"), encoding="utf-8")

    source_identity = generate_legacy_ecosystem_projection(canonical, output)
    first_bytes = output.read_bytes()
    generate_legacy_ecosystem_projection(canonical, output, check=True)
    second_bytes = output.read_bytes()
    projection = json.loads(second_bytes)

    validate_ecosystem(projection)
    assert first_bytes == second_bytes
    assert source_identity == source_manifest_identity(manifest)
    assert projection["metadata"]["manifest_authority"] == "v3-authoritative"
    assert projection["metadata"]["generated"] is True
    assert projection["metadata"]["read_only_projection"] is True
    assert (
        projection["metadata"]["generated_from"]["source_content_hash"]
        == source_identity
    )


def test_repository_v3_projections_are_current_and_source_integrity_bound() -> None:
    """No v3-authoritative Pack may have a missing, stale, or hand-edited projection."""
    authority = _authority_module()
    catalog = authority.load_manifest_authority_catalog()
    errors: list[str] = []
    for pack_id, pack_authority in sorted(catalog.items()):
        if pack_authority != "v3-authoritative":
            continue
        pack_dir = ECOSYSTEM / pack_id
        canonical = pack_dir / "rumi.pack.v3.json"
        projection = pack_dir / "ecosystem.json"
        try:
            source_identity = generate_legacy_ecosystem_projection(
                canonical,
                projection,
                check=True,
            )
            rendered = json.loads(projection.read_text(encoding="utf-8"))
            if (
                rendered["metadata"]["generated_from"]["source_content_hash"]
                != source_identity
            ):
                errors.append(f"{pack_id}: source hash mismatch")
        except Exception as exc:
            errors.append(f"{pack_id}: {exc}")

    assert not errors, "projection diagnostics: " + " | ".join(errors[:8])


def test_invalid_v3_manifest_is_not_available_or_effective(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A v3 error must never remain in the resolved effective Pack set."""
    import core_runtime.resolved_profile as profile_module

    monkeypatch.setattr(
        profile_module,
        "verify_declared_artifacts",
        lambda *_args, **_kwargs: (True, ()),
    )
    pack_id = "invalid_v3_profile_pack"
    ecosystem_dir = tmp_path / "ecosystem"
    pack_dir = _write_legacy_pack(ecosystem_dir, pack_id)
    (pack_dir / "rumi.pack.v3.json").write_text(
        json.dumps(
            {
                "pack_api_version": "rumi.pack.v3",
                "unknown_schema_key": True,
            }
        ),
        encoding="utf-8",
    )

    plan = resolve_profile(
        ResolutionInput(
            profile_id="invalid-v3-regression",
            profile_revision="r1",
            platform="test",
            policy_revision="p1",
            lockfile_revision=None,
            requested_pack_ids=(pack_id,),
            authorized_pack_ids=(pack_id,),
            healthy_pack_ids=(pack_id,),
        ),
        ecosystem_dir=ecosystem_dir,
    )

    assert pack_id not in plan.available_pack_ids
    assert pack_id not in plan.effective_pack_set
    assert any(
        item.code == "invalid_manifest"
        and item.severity == "error"
        and item.subject == pack_id
        for item in plan.diagnostics
    )


class _Approved:
    """Approval fixture for manifest binding tests."""

    def is_pack_approved_and_verified(self, _pack_id: str) -> tuple[bool, str]:
        """Approve the selected Pack without changing artifact verification."""
        return True, "verified test fixture"


def test_valid_model_evals_manifest_binds_all_declared_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canonical model-evals manifest must be usable by the binding loader."""
    import core_runtime.capability_binding_registration as binding_module

    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    monkeypatch.setattr(
        binding_module,
        "verify_declared_artifacts",
        lambda *_args, **_kwargs: (True, ()),
    )
    manifest = json.loads(
        (ECOSYSTEM / MODEL_EVALS_PACK / "rumi.pack.v3.json").read_text(
            encoding="utf-8"
        )
    )
    expected_contracts = {
        item["id"] for item in manifest["contracts"]["provides"]
    }
    interface_registry = InterfaceRegistry()

    result = register_pack_binding_handlers(
        interface_registry=interface_registry,
        approval_manager=_Approved(),
        ecosystem_dir=str(ECOSYSTEM),
        effective_pack_ids=(MODEL_EVALS_PACK,),
    )

    assert result.ok is True
    assert result.registered == [MODEL_EVALS_PACK]
    assert set(interface_registry.list(prefix="global_contract.provider.")) == {
        f"global_contract.provider.{contract_id}"
        for contract_id in expected_contracts
    }


def test_model_evals_binding_fails_closed_on_tampered_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approval cannot override a Host-detected model-evals artifact tamper."""
    import core_runtime.capability_binding_registration as binding_module

    monkeypatch.setattr(
        binding_module,
        "verify_declared_artifacts",
        lambda *_args, **_kwargs: (False, ("fixture artifact is tampered",)),
    )
    interface_registry = InterfaceRegistry()
    result = register_pack_binding_handlers(
        interface_registry=interface_registry,
        approval_manager=_Approved(),
        ecosystem_dir=str(ECOSYSTEM),
        effective_pack_ids=(MODEL_EVALS_PACK,),
    )

    assert result.ok is False
    assert result.registered == []
    assert interface_registry.list(prefix="global_contract.provider.") == {}
    assert any(
        diagnostic["code"] == "v3_pack_artifact_integrity_failed"
        for diagnostic in result.diagnostics
    )


def test_malformed_model_evals_manifest_cannot_bind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Malformed/unknown v3 schema data is rejected before provider activation."""
    import core_runtime.capability_binding_registration as binding_module

    ecosystem_dir = tmp_path / "ecosystem"
    shutil.copytree(
        ECOSYSTEM / MODEL_EVALS_PACK,
        ecosystem_dir / MODEL_EVALS_PACK,
    )
    manifest_path = ecosystem_dir / MODEL_EVALS_PACK / "rumi.pack.v3.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unknown_schema_key"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        binding_module,
        "verify_declared_artifacts",
        lambda *_args, **_kwargs: (True, ()),
    )

    interface_registry = InterfaceRegistry()
    result = register_pack_binding_handlers(
        interface_registry=interface_registry,
        approval_manager=_Approved(),
        ecosystem_dir=str(ecosystem_dir),
        effective_pack_ids=(MODEL_EVALS_PACK,),
    )

    assert result.ok is False
    assert result.registered == []
    assert interface_registry.list(prefix="global_contract.provider.") == {}
    assert any(
        diagnostic["code"] == "v3_process_manifest_invalid"
        for diagnostic in result.diagnostics
    )
