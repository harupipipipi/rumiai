from __future__ import annotations

import copy
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from core_runtime.authority.v4 import AuthorityDenied, AuthorityStore
from ecosystem.defaultspack.domain.runtime_v4 import (
    ActivationStore,
    BundleIntegrityError,
    BundledCatalog,
    ProfileResolutionDenied,
    resolve_default_profile,
)

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = ROOT / "ecosystem" / "defaultspack" / "v4"
SNAPSHOT_DIGEST = "sha256:" + "9" * 64
AUTHORITY_BINDINGS = {
    "shell.tauri.default|defaultspack.conversation|conversation.turn.v1|complete": (
        "authority-ref:conversation.default"
    ),
    (
        "defaultspack.conversation|rumi_file_inspect_pack.file-inspect.service|"
        "tobkiri.service.file.inspect.v1|rumi_file_inspect_pack.file-inspect"
    ): "authority-ref:file.inspect.default",
}


def _catalog() -> BundledCatalog:
    return BundledCatalog.load(BUNDLE_ROOT)


def _approved(catalog: BundledCatalog) -> set[str]:
    return {
        str(manifest["pack"]["artifact_digest"])
        for manifest in catalog.packs.values()
    }


def _resolve(catalog: BundledCatalog | None = None):
    selected_catalog = catalog or _catalog()
    return resolve_default_profile(
        selected_catalog,
        "defaults",
        approved_artifact_digests=_approved(selected_catalog),
        authority_snapshot_digest=SNAPSHOT_DIGEST,
        authority_bindings=AUTHORITY_BINDINGS,
        security_epoch=7,
    )


def _authority(path: Path) -> AuthorityStore:
    store = AuthorityStore(path)
    while store.security_epoch < 7:
        store.advance_security_epoch("test fixture epoch")
    return store


def test_bundle_is_protocol_v4_and_resolves_exact_dependency_closure() -> None:
    catalog = _catalog()
    resolved = _resolve(catalog)

    assert set(catalog.packs) == {
        "defaults-basepack",
        "defaultspack",
        "rumi_file_inspect_pack",
        "rumi_host_authority_bridge_pack",
        "rumi_workspace_mount_pack",
        "runtime.tauri.application.default",
        "dev.tauri.toolchain.default",
        "shell.cli.default",
        "shell.tauri.default",
    }
    assert resolved.profile["profile_api_version"] == "io.tobkiri.profile.v4"
    assert resolved.profile["state"] == "resolved"
    assert resolved.profile["shell"]["provider_id"] == "shell.tauri.default"
    assert "shell.cli.default" not in {
        item["identity"] for item in resolved.lock["effective_set"]
    }
    assert resolved.profile["profile_authority_snapshot_digest"] == SNAPSHOT_DIGEST
    assert {item["pack_id"] for item in resolved.profile["packs"]} == {
        "defaultspack",
        "rumi_file_inspect_pack",
        "rumi_host_authority_bridge_pack",
        "rumi_workspace_mount_pack",
        "runtime.tauri.application.default",
    }
    roles = {
        item["pack_id"]: item["role"] for item in resolved.profile["packs"]
    }
    assert roles["runtime.tauri.application.default"] == "application"
    assert "dev.tauri.toolchain.default" not in {
        item["identity"] for item in resolved.lock["effective_set"]
    }
    assert [item["function_principal"]["function_id"] for item in resolved.plan["bindings"]] == [
        "defaultspack.conversation",
        "rumi_file_inspect_pack.file-inspect.service",
    ]
    assert resolved.lock["plan_digest"] == resolved.plan["plan_digest"]


def test_duplicate_pack_and_legacy_route_authorities_are_absent() -> None:
    from ecosystem.defaultspack.domain.function_runtime.compat_aliases import (
        compatibility_alias_allowed,
    )
    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    defaultspack_root = ROOT / "ecosystem" / "defaultspack"
    defaults_root = ROOT / "ecosystem" / "defaults"
    assert {path.name for path in defaults_root.iterdir()} == {
        "artifact-index.v4.json",
        "contracts.v4.json",
        "executables.v4.json",
        "pack.v4.json",
    }
    assert not (defaultspack_root / "ecosystem.json").exists()
    assert not (defaultspack_root / "permissions.json").exists()
    assert not (defaultspack_root / "routes.json").exists()
    assert not (defaultspack_root / "compat_aliases.yaml").exists()
    assert not (defaultspack_root / "docs" / "legacy_http_routes.yaml").exists()
    assert not (defaultspack_root / "domain" / "pack_architecture").exists()

    routes = canonical_http_route_specs()
    assert routes
    assert all(route.handler_name for route in routes)
    assert not any(route.block_module for route in routes)
    assert not any(route.fallback_block_module for route in routes)
    assert not any(route.legacy_block_module for route in routes)
    assert compatibility_alias_allowed("defaults.chat.send") is False


def test_bundle_rejects_manifest_hash_drift_and_unlisted_artifacts(tmp_path: Path) -> None:
    copied = tmp_path / "v4"
    shutil.copytree(BUNDLE_ROOT, copied)
    manifest = copied / "packs" / "defaultspack.pack.v4.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="digest changed"):
        BundledCatalog.load(copied)

    catalog = _catalog()
    approved = _approved(catalog)
    approved.remove(catalog.packs["rumi_file_inspect_pack"]["pack"]["artifact_digest"])
    with pytest.raises(ProfileResolutionDenied, match="not approved: rumi_file_inspect_pack"):
        resolve_default_profile(
            catalog,
            "defaults",
            approved_artifact_digests=approved,
            authority_snapshot_digest=SNAPSHOT_DIGEST,
            authority_bindings=AUTHORITY_BINDINGS,
            security_epoch=7,
        )


def test_foundational_conversation_provider_is_exactly_one() -> None:
    catalog = _catalog()
    missing_manifest = copy.deepcopy(catalog.packs["defaultspack"])
    missing_manifest["functions"] = []
    missing_manifest["contracts"] = []
    missing = replace(
        catalog,
        packs={**catalog.packs, "defaultspack": missing_manifest},
    )
    with pytest.raises(ProfileResolutionDenied, match="exactly once; found 0"):
        _resolve(missing)

    duplicate = copy.deepcopy(catalog.packs["defaultspack"])
    duplicate["pack"]["id"] = "duplicate-conversation"
    duplicate["pack"]["artifact_digest"] = "sha256:" + "8" * 64
    duplicate_catalog = replace(
        catalog,
        packs={**catalog.packs, "duplicate-conversation": duplicate},
    )
    with pytest.raises(ProfileResolutionDenied, match="exactly once; found 2"):
        resolve_default_profile(
            duplicate_catalog,
            "defaults",
            approved_artifact_digests=_approved(duplicate_catalog),
            authority_snapshot_digest=SNAPSHOT_DIGEST,
            authority_bindings=AUTHORITY_BINDINGS,
            security_epoch=7,
            additional_pack_ids=("duplicate-conversation",),
        )


def test_requested_pack_dependency_and_authority_references_are_mandatory() -> None:
    catalog = _catalog()
    profile = copy.deepcopy(catalog.profiles["defaults"])
    profile["packs"] = [
        item
        for item in profile["packs"]
        if item["pack_id"] != "rumi_file_inspect_pack"
    ]
    missing_dependency = replace(catalog, profiles={"defaults": profile})
    with pytest.raises(ProfileResolutionDenied, match="must resolve exactly once; found 0"):
        _resolve(missing_dependency)

    with pytest.raises(ProfileResolutionDenied, match="Authority Kernel reference is missing"):
        resolve_default_profile(
            catalog,
            "defaults",
            approved_artifact_digests=_approved(catalog),
            authority_snapshot_digest=SNAPSHOT_DIGEST,
            authority_bindings={},
            security_epoch=7,
        )


def test_activation_restart_is_atomic_and_stale_records_deny(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = _authority(tmp_path / "authority.sqlite3")
    store = ActivationStore(
        tmp_path / "state", workspace, profile_id="defaults", authority=authority
    )
    resolved = _resolve()
    activation = store.activate(
        resolved,
        activation_id="activation:defaults-0001",
        created_at="2026-08-05T00:00:00Z",
    )
    assert activation["state"] == "active"
    assert store.load_active().plan == resolved.plan

    pointer = json.loads((tmp_path / "state" / "active.json").read_text(encoding="utf-8"))
    envelope_path = tmp_path / "state" / "activations" / pointer["envelope_path"]
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["lock"]["security_epoch"] = 6
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ProfileResolutionDenied, match="envelope digest changed"):
        store.load_active()


def test_new_activation_atomically_retires_the_previous_authority(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = _authority(tmp_path / "authority.sqlite3")
    store = ActivationStore(
        tmp_path / "state", workspace, profile_id="defaults", authority=authority
    )
    resolved = _resolve()

    first = store.activate(
        resolved,
        activation_id="activation:defaults-first",
        created_at="2026-08-05T00:00:00Z",
    )
    second = store.activate(
        resolved,
        activation_id="activation:defaults-second",
        created_at="2026-08-05T00:01:00Z",
    )

    assert second["fencing_token"] > first["fencing_token"]
    assert authority.active_activation_reservation(first["activation_id"]) is None
    active = authority.active_activation_reservation(second["activation_id"])
    assert active is not None
    assert active["state"] == "active"
    assert (
        store.load_active_snapshot().activation["activation_id"]
        == second["activation_id"]
    )


def test_workspace_traversal_symlink_escape_and_cross_workspace_restart_deny(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    authority = _authority(tmp_path / "authority.sqlite3")
    store = ActivationStore(
        tmp_path / "state", workspace, profile_id="defaults", authority=authority
    )
    assert store.resolve_workspace_path("notes/item.txt") == workspace / "notes" / "item.txt"
    with pytest.raises(ProfileResolutionDenied, match="traversal-free"):
        store.resolve_workspace_path("../other/secret.txt")
    with pytest.raises(ProfileResolutionDenied, match="traversal-free"):
        store.resolve_workspace_path(str(other / "secret.txt"))

    link = workspace / "outside"
    link.symlink_to(other, target_is_directory=True)
    with pytest.raises(ProfileResolutionDenied, match="escapes"):
        store.resolve_workspace_path("outside/secret.txt")

    store.activate(
        _resolve(),
        activation_id="activation:defaults-0002",
        created_at="2026-08-05T00:00:00Z",
    )
    other_store = ActivationStore(
        tmp_path / "state", other, profile_id="defaults", authority=authority
    )
    with pytest.raises(ProfileResolutionDenied, match="another workspace"):
        other_store.load_active()


def test_activation_journal_recovers_only_authority_committed_candidate(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = _authority(tmp_path / "authority.sqlite3")

    def crash(stage: str) -> None:
        if stage == "after_authority_commit":
            raise RuntimeError("simulated crash after authority commit")

    crashing = ActivationStore(
        tmp_path / "state",
        workspace,
        profile_id="defaults",
        authority=authority,
        fault=crash,
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        crashing.activate(
            _resolve(),
            activation_id="activation:defaults-crash",
            created_at="2026-08-05T00:00:00Z",
        )
    assert (tmp_path / "state" / "pending.json").is_file()

    recovered = ActivationStore(
        tmp_path / "state",
        workspace,
        profile_id="defaults",
        authority=authority,
    ).load_active_snapshot()
    assert recovered.activation["state"] == "active"
    assert recovered.activation["state_generation"] == 4
    assert not (tmp_path / "state" / "pending.json").exists()
    states = [
        event["event_state"]
        for event in authority.audit_events()
        if event["event_type"] == "activation"
    ]
    assert states == [
        "prepared",
        "ready_without_authority",
        "committing",
        "active",
    ]


def test_activation_candidate_aborts_on_epoch_revoke_and_token_is_not_reused(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = _authority(tmp_path / "authority.sqlite3")

    def revoke(stage: str) -> None:
        if stage == "ready_without_authority":
            authority.advance_security_epoch("emergency revoke during activation")

    store = ActivationStore(
        tmp_path / "state",
        workspace,
        profile_id="defaults",
        authority=authority,
        fault=revoke,
    )
    with pytest.raises(AuthorityDenied, match="stale SecurityEpoch|state fence"):
        store.activate(
            _resolve(),
            activation_id="activation:defaults-revoked",
            created_at="2026-08-05T00:00:00Z",
        )
    assert not (tmp_path / "state" / "active.json").exists()
    assert not (tmp_path / "state" / "pending.json").exists()
    reservations = [
        event["payload"]
        for event in authority.audit_events()
        if event["event_type"] == "activation"
        and event["event_state"] == "prepared"
    ]
    assert reservations[0]["fencing_token"] == 1
