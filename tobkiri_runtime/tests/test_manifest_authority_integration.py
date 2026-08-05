"""Repository gates for classified Pack authority and production loading."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from backend_core.ecosystem.registry import LegacyRegistryUnavailable, Registry
from backend_core.ecosystem.spec.schema.validator import validate_ecosystem
from core_runtime.global_contracts.manifest import load_manifest
from core_runtime.manifest_authority import (
    ManifestAuthorityError,
    load_manifest_authority_catalog,
    validate_manifest_authority_scope,
)
from scripts.offline_legacy_projection import (
    ManifestProjectionError,
    generate_legacy_ecosystem_projection,
    project_legacy_ecosystem,
    source_manifest_identity,
)
from scripts.migrate_manifest_authority import _normalize_artifact_index
from core_runtime.pack_artifact_integrity import verify_declared_artifacts
from core_runtime.resolved_profile import ResolutionInput, resolve_profile

ROOT = Path(__file__).resolve().parents[1]
ECOSYSTEM = ROOT / "ecosystem"


def test_every_repository_pack_has_one_explicit_authority() -> None:
    catalog = load_manifest_authority_catalog()
    direct_pack_ids = tuple(
        sorted(
            path.name
            for path in ECOSYSTEM.iterdir()
            if path.is_dir()
            and path.name != "setup_pack"
            and not path.name.startswith(".")
        )
    )

    validate_manifest_authority_scope(
        direct_pack_ids,
        require_complete_catalog=True,
    )
    assert len(catalog) == 141
    assert list(catalog.values()).count("v3-authoritative") == 95
    assert list(catalog.values()).count("legacy-authoritative") == 44
    assert list(catalog.values()).count("modern-only") == 2
    assert catalog["defaults"] == "modern-only"
    assert catalog["defaultspack"] == "modern-only"


def test_authority_scope_rejects_missing_extra_and_implicit_inputs() -> None:
    catalog = load_manifest_authority_catalog()
    pack_ids = tuple(catalog)

    with pytest.raises(ManifestAuthorityError, match="must be explicit"):
        validate_manifest_authority_scope(None)
    with pytest.raises(ManifestAuthorityError, match="extra=.*injected_pack"):
        validate_manifest_authority_scope((*pack_ids, "injected_pack"))
    with pytest.raises(ManifestAuthorityError, match="stale="):
        validate_manifest_authority_scope(
            pack_ids[:-1],
            require_complete_catalog=True,
        )

    validate_manifest_authority_scope(pack_ids[:1])


def test_all_authoritative_manifests_and_projections_are_valid() -> None:
    catalog = load_manifest_authority_catalog()

    for pack_id, authority in sorted(catalog.items()):
        pack_root = ECOSYSTEM / pack_id
        ecosystem_path = pack_root / "ecosystem.json"
        if authority == "modern-only":
            assert pack_id in {"defaults", "defaultspack"}
            assert not ecosystem_path.exists()
            assert not (pack_root / "rumi.pack.v3.json").exists()
            assert (pack_root / "pack.v4.json").is_file()
            continue
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


def test_v3_artifact_sidecar_generator_refreshes_hash_without_projection_rebind(
    tmp_path: Path,
) -> None:
    """The authority generator refreshes orphan v3 sidecars deterministically."""
    pack_root = tmp_path / "rumi_file_inspect_pack"
    runtime = pack_root / "runtime"
    runtime.mkdir(parents=True)
    source = runtime / "inspect.py"
    source.write_text("print('current')\n", encoding="utf-8")
    artifact_index = pack_root / "artifact-manifest.json"
    artifact_index.write_text(
        '{"schema_version":"rumi.artifact-manifest.v1",'
        '"artifacts":[{"path":"runtime/inspect.py",'
        '"sha256":"' + "0" * 64 + '","role":"runtime"}]}\n',
        encoding="utf-8",
    )

    assert _normalize_artifact_index(
        pack_root,
        {},
        check=False,
        include_unreferenced_sidecar=True,
    ) is None
    first = artifact_index.read_bytes()
    assert str(json.loads(first)["artifacts"][0]["sha256"]) == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()

    assert _normalize_artifact_index(
        pack_root,
        {},
        check=True,
        include_unreferenced_sidecar=True,
    ) is None
    assert artifact_index.read_bytes() == first


def test_referenced_artifact_sidecar_persists_refreshed_hash(
    tmp_path: Path,
) -> None:
    """Referenced indexes must write the same digest used for provenance."""
    pack_root = tmp_path / "referenced_pack"
    runtime = pack_root / "runtime"
    runtime.mkdir(parents=True)
    source = runtime / "adapter.py"
    source.write_text("VALUE = 'current'\n", encoding="utf-8")
    artifact_index = pack_root / "artifact-manifest.json"
    artifact_index.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "path": "runtime/adapter.py",
                        "sha256": "sha256:" + "0" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ecosystem = {
        "metadata": {
            "integrity": {"artifact_manifest": "artifact-manifest.json"}
        }
    }

    index_hash = _normalize_artifact_index(
        pack_root,
        ecosystem,
        check=False,
    )
    payload = json.loads(artifact_index.read_text(encoding="utf-8"))
    expected = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()

    assert payload["artifacts"][0]["sha256"] == expected
    assert index_hash == "sha256:" + hashlib.sha256(
        artifact_index.read_bytes()
    ).hexdigest()
    assert _normalize_artifact_index(pack_root, ecosystem, check=True) == index_hash


def test_removed_registry_rejects_runtime_discovery(tmp_path: Path) -> None:
    """Pack v4 runtime must refuse the removed filesystem registry path."""
    with pytest.raises(LegacyRegistryUnavailable, match="removed"):
        Registry(str(tmp_path / "ecosystem")).load_all_packs()


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


def test_removed_binding_authorities_are_not_importable() -> None:
    """v4 composition must not restore deleted Core binding registries."""
    for module_name in (
        "core_runtime.capability_binding_registration",
        "core_runtime.function_registry",
        "core_runtime.interface_registry",
    ):
        assert importlib.util.find_spec(module_name) is None
