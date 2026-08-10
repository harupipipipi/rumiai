"""Review-C regressions for versioning, artifacts, scopes, and provenance."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core_runtime.authority.v4 import AuthorityStore
from ecosystem.defaultspack.domain.runtime_v4 import (
    ActivationStore,
    BundledCatalog,
    ProfileResolutionDenied,
    resolve_default_profile,
)
from tests.conformance_support.packaged_profile import build_packaged_profile_bundle
from tobkiri_protocol.canonical import canonical_digest, canonical_json
from tobkiri_protocol.profile_scope import normalize_requested_scope_template
from tobkiri_protocol.platform_artifact import verify_platform_artifact
from tobkiri_protocol.provenance import (
    normative_generated_provenance,
    trusted_source_commit,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"
FROZEN = Path(__file__).parent / "fixtures/profile_v4/pre-e853-activation.json"
SOURCE_COMMIT = "a9ea44934646b6b353ad2bcab294a35d3b99556d"


def _edge_key(edge: dict[str, object]) -> str:
    return "|".join(
        str(edge[key])
        for key in (
            "caller_function_id",
            "target_provider_id",
            "contract_id",
            "operation_id",
        )
    )


def _packaged_catalog(tmp_path: Path) -> BundledCatalog:
    bundle = build_packaged_profile_bundle(
        SOURCE_BUNDLE,
        tmp_path,
        source_commit=SOURCE_COMMIT,
    )
    return BundledCatalog.load(bundle)


def _resolve(catalog: BundledCatalog):
    profile = catalog.profiles["defaults"]
    return resolve_default_profile(
        catalog,
        "defaults",
        approved_artifact_digests={
            str(manifest["pack"]["artifact_digest"])
            for manifest in catalog.packs.values()
        },
        authority_snapshot_digest="sha256:" + "9" * 64,
        authority_bindings={
            _edge_key(edge): "authority-ref:test."
            + canonical_digest(_edge_key(edge)).removeprefix("sha256:")
            for edge in profile["requested_edges"]
        },
        security_epoch=1,
    )


def test_source_checkout_profile_is_explicitly_unavailable() -> None:
    catalog = BundledCatalog.load(SOURCE_BUNDLE)
    assert catalog.shells["shell.tauri.default"]["availability"] == "build_required"
    assert catalog.shells["shell.tauri.default"]["launch"]["variants"] == []
    with pytest.raises(ProfileResolutionDenied, match="Shell artifact is unavailable"):
        _resolve(catalog)


def test_packaged_artifact_resolves_activates_and_restarts(tmp_path: Path) -> None:
    catalog = _packaged_catalog(tmp_path)
    resolved = _resolve(catalog)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = AuthorityStore(tmp_path / "authority.sqlite3")
    store = ActivationStore(
        tmp_path / "state",
        workspace,
        profile_id="defaults",
        authority=authority,
        catalog=catalog,
    )
    activation = store.activate(
        resolved,
        activation_id="activation:defaults-packaged",
        created_at="2026-08-10T00:00:00Z",
    )
    assert activation["activation_api_version"] == "io.tobkiri.activation-record.v2"
    assert store.load_active_snapshot().resolved.plan == resolved.plan


@pytest.mark.parametrize("field", ("platform", "architecture", "bundle_identity"))
def test_packaged_artifact_metadata_mismatch_is_rejected(
    tmp_path: Path, field: str
) -> None:
    catalog = _packaged_catalog(tmp_path)
    shell = copy.deepcopy(catalog.shells["shell.tauri.default"])
    replacement = {
        "platform": "linux",
        "architecture": "x86_64",
        "bundle_identity": "io.tobkiri.wrong",
    }[field]
    shell["launch"]["variants"][0][field] = replacement
    tampered = type(catalog)(
        root=catalog.root,
        packs=catalog.packs,
        bases=catalog.bases,
        shells={**catalog.shells, "shell.tauri.default": shell},
        profiles=catalog.profiles,
        artifact_root=catalog.artifact_root,
    )
    with pytest.raises(ProfileResolutionDenied):
        _resolve(tampered)


@pytest.mark.parametrize("case", ("missing", "digest", "sentinel", "symlink"))
def test_packaged_artifact_path_digest_and_symlink_rejection(
    tmp_path: Path, case: str
) -> None:
    catalog = _packaged_catalog(tmp_path)
    variant = copy.deepcopy(
        catalog.shells["shell.tauri.default"]["launch"]["variants"][0]
    )
    executable = (
        catalog.artifact_root
        / "Tobkiri.app/Contents/MacOS/tobkiri"
    )
    if case == "missing":
        variant["relative_path"] = "Missing.app"
    elif case == "digest":
        variant["artifact_digest"] = "sha256:" + "1" * 64
    elif case == "sentinel":
        variant["artifact_digest"] = "sha256:" + "d" * 64
    else:
        outside = tmp_path / "outside"
        outside.write_bytes(executable.read_bytes())
        executable.unlink()
        executable.symlink_to(outside)
    with pytest.raises(Exception):
        verify_platform_artifact(catalog.artifact_root, variant)


def test_requested_scope_normalization_denies_expansion_and_is_canonical() -> None:
    semantics = "sha256:" + "1" * 64
    normalized = normalize_requested_scope_template(
        {}, contract_id="example.echo.v1", operation_id="echo", semantics_digest=semantics
    )
    assert normalized["dimensions"] == {
        "contract": ["example.echo.v1"],
        "operation": ["echo"],
    }
    with pytest.raises(Exception, match="wildcards|does not match"):
        normalize_requested_scope_template(
            {"dimensions": {"operation": ["*"]}},
            contract_id="example.echo.v1",
            operation_id="echo",
            semantics_digest=semantics,
        )


def _write_frozen_activation(
    state: Path, workspace: Path, authority: AuthorityStore
) -> None:
    fixture = json.loads(FROZEN.read_text(encoding="utf-8"))
    activation = fixture["activation"]
    reservation_id, fencing_token = authority.reserve_activation(
        activation_id=activation["activation_id"],
        profile_id=activation["profile_id"],
        plan_digest=activation["plan_digest"],
        profile_authority_digest=activation[
            "profile_authority_snapshot_digest"
        ],
        security_epoch=activation["security_epoch"],
    )
    assert fencing_token == activation["fencing_token"]
    for before, after in (
        ("prepared", "ready_without_authority"),
        ("ready_without_authority", "committing"),
        ("committing", "active"),
    ):
        authority.transition_activation(
            reservation_id, expected_state=before, new_state=after
        )
    workspace_digest = canonical_digest(
        {"workspace_root": str(workspace.resolve())}
    )
    envelope = {
        "schema": "io.tobkiri.defaultspack-activation-envelope.v1",
        "workspace_digest": workspace_digest,
        **{
            key: fixture[key]
            for key in ("profile", "lock", "plan", "activation")
        },
    }
    envelope_path = state / "activations/defaults-pre-e853.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_bytes(canonical_json(envelope) + b"\n")
    pointer = {
        "schema": "io.tobkiri.defaultspack-active-pointer.v1",
        "activation_id": activation["activation_id"],
        "envelope_path": envelope_path.name,
        "envelope_digest": canonical_digest(envelope),
        "workspace_digest": workspace_digest,
    }
    (state / "active.json").write_bytes(canonical_json(pointer) + b"\n")


def test_frozen_pre_e853_restart_migrates_once_and_tamper_fails(
    tmp_path: Path,
) -> None:
    catalog = _packaged_catalog(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    authority = AuthorityStore(tmp_path / "authority.sqlite3")
    _write_frozen_activation(state, workspace, authority)
    store = ActivationStore(
        state,
        workspace,
        profile_id="defaults",
        authority=authority,
        catalog=catalog,
    )
    migrated = store.load_active_snapshot()
    assert migrated.activation["activation_api_version"] == "io.tobkiri.activation-record.v2"
    assert migrated.resolved.lock["lock_api_version"] == "io.tobkiri.profile-lock.v5"
    assert store.load_active_snapshot().activation == migrated.activation


def test_frozen_pre_e853_tamper_and_migration_crash_fail_closed(
    tmp_path: Path,
) -> None:
    catalog = _packaged_catalog(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    authority = AuthorityStore(tmp_path / "authority.sqlite3")
    _write_frozen_activation(state, workspace, authority)
    pointer = json.loads((state / "active.json").read_text(encoding="utf-8"))
    envelope_path = state / "activations" / pointer["envelope_path"]
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["plan"]["security_epoch"] = 2
    envelope_path.write_bytes(canonical_json(envelope) + b"\n")
    pointer["envelope_digest"] = canonical_digest(envelope)
    (state / "active.json").write_bytes(canonical_json(pointer) + b"\n")
    store = ActivationStore(
        state,
        workspace,
        profile_id="defaults",
        authority=authority,
        catalog=catalog,
    )
    with pytest.raises(ProfileResolutionDenied, match="predecessor is stale"):
        store.load_active_snapshot()

    clean_state = tmp_path / "clean-state"
    clean_authority = AuthorityStore(tmp_path / "clean-authority.sqlite3")
    _write_frozen_activation(clean_state, workspace, clean_authority)

    def crash(stage: str) -> None:
        if stage == "after_authority_commit":
            raise RuntimeError("migration crash")

    crashing = ActivationStore(
        clean_state,
        workspace,
        profile_id="defaults",
        authority=clean_authority,
        catalog=catalog,
        fault=crash,
    )
    with pytest.raises(RuntimeError, match="migration crash"):
        crashing.load_active_snapshot()
    recovered = ActivationStore(
        clean_state,
        workspace,
        profile_id="defaults",
        authority=clean_authority,
        catalog=catalog,
    ).load_active_snapshot()
    assert recovered.activation["activation_api_version"] == (
        "io.tobkiri.activation-record.v2"
    )


def test_normative_generator_rejects_dirty_implicit_commit() -> None:
    with pytest.raises(Exception, match="dirty working tree"):
        trusted_source_commit(ROOT.parent)


def test_normative_provenance_is_non_self_referential_and_source_bound() -> None:
    first = normative_generated_provenance(
        source_path="source.json",
        payload={"value": 1},
        repository_commit_value=SOURCE_COMMIT,
        generator="test",
        generator_version="1",
    )
    second = normative_generated_provenance(
        source_path="source.json",
        payload={"value": 2},
        repository_commit_value=SOURCE_COMMIT,
        generator="test",
        generator_version="1",
    )
    assert first["source_digest"] != second["source_digest"]
    assert first["repository_tree"] != second["repository_tree"]
    assert "provenance" not in json.dumps({"value": 1})
    with pytest.raises(Exception, match="exact repository commit"):
        normative_generated_provenance(
            source_path="source.json",
            payload={"value": 1},
            repository_commit_value="working-tree",
            generator="test",
            generator_version="1",
        )
