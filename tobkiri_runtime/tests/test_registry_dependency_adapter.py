"""Profile Resolver dependency closure replacing the legacy Registry adapter."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from ecosystem.defaultspack.domain.runtime_v4 import (
    BundledCatalog,
    ProfileResolutionDenied,
    resolve_default_profile,
)
from tests.v4_batch_support import assert_legacy_registry_fails_closed


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"
SNAPSHOT = "sha256:" + "9" * 64
BINDINGS = {
    "shell.tauri.default|defaultspack.conversation|conversation.turn.v1|complete": "authority-ref:conversation.default",
    "shell.tauri.pack-control|tobkiri.host.pack-control|tobkiri.host.pack-control.v4|catalog.read": "authority-ref:pack.catalog.default",
    "defaultspack.conversation|rumi_file_inspect_pack.file-inspect.service|tobkiri.service.file.inspect.v1|rumi_file_inspect_pack.file-inspect": "authority-ref:file.inspect.default",
}


def _catalog() -> BundledCatalog:
    return BundledCatalog.load(BUNDLE)


def _approved(catalog: BundledCatalog) -> set[str]:
    return {str(item["pack"]["artifact_digest"]) for item in catalog.packs.values()}


def _resolve(catalog: BundledCatalog):
    return resolve_default_profile(
        catalog,
        "defaults",
        approved_artifact_digests=_approved(catalog),
        authority_snapshot_digest=SNAPSHOT,
        authority_bindings=BINDINGS,
        security_epoch=1,
    )


def test_legacy_registry_module_is_not_an_adapter() -> None:
    assert_legacy_registry_fails_closed()


def test_profile_resolver_delegates_dependency_order_to_effective_set() -> None:
    resolved = _resolve(_catalog())
    assert [item["identity"] for item in resolved.lock["effective_set"]] == [
        "defaults-basepack",
        "shell.tauri.default",
        "defaultspack",
        "rumi_file_inspect_pack",
        "tobkiri_host_pack_control",
        "runtime.tauri.application.default",
        "rumi_workspace_mount_pack",
        "rumi_host_authority_bridge_pack",
    ]


def test_profile_resolver_fails_closed_for_missing_dependency() -> None:
    catalog = _catalog()
    profile = copy.deepcopy(catalog.profiles["defaults"])
    profile["packs"] = [
        item for item in profile["packs"] if item["pack_id"] != "rumi_file_inspect_pack"
    ]
    missing = replace(catalog, profiles={"defaults": profile})
    with pytest.raises(ProfileResolutionDenied):
        _resolve(missing)


def test_profile_resolver_fails_closed_for_unapproved_dependency() -> None:
    catalog = _catalog()
    approved = _approved(catalog)
    approved.remove(catalog.packs["rumi_file_inspect_pack"]["pack"]["artifact_digest"])
    with pytest.raises(ProfileResolutionDenied, match="not approved"):
        resolve_default_profile(
            catalog,
            "defaults",
            approved_artifact_digests=approved,
            authority_snapshot_digest=SNAPSHOT,
            authority_bindings=BINDINGS,
            security_epoch=1,
        )


def test_profile_resolver_fails_closed_for_duplicate_selected_pack() -> None:
    catalog = _catalog()
    duplicate = copy.deepcopy(catalog.packs["defaultspack"])
    duplicate["pack"]["id"] = "duplicate-defaultspack"
    duplicate["pack"]["artifact_digest"] = "sha256:" + "8" * 64
    duplicate_catalog = replace(
        catalog,
        packs={**catalog.packs, "duplicate-defaultspack": duplicate},
    )
    with pytest.raises(ProfileResolutionDenied, match="exactly once"):
        resolve_default_profile(
            duplicate_catalog,
            "defaults",
            approved_artifact_digests=_approved(duplicate_catalog),
            authority_snapshot_digest=SNAPSHOT,
            authority_bindings=BINDINGS,
            security_epoch=1,
            additional_pack_ids=("duplicate-defaultspack",),
        )
