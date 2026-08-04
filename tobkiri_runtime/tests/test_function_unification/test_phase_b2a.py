"""Exact v4 ProfileLock/ResolvedPlan checks replacing handler manifests."""

from __future__ import annotations

from pathlib import Path

from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog, resolve_default_profile
from tobkiri_protocol.canonical import canonical_digest
from tests.legacy_authority_contracts import assert_profile_resolver_requires_authority_snapshot


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"
SNAPSHOT = "sha256:" + "9" * 64
BINDINGS = {
    "shell.cli.default|defaultspack.conversation|conversation.turn.v1|complete": (
        "authority-ref:conversation.default"
    ),
    (
        "defaultspack.conversation|rumi_file_inspect_pack.file-inspect.service|"
        "tobkiri.service.file.inspect.v1|rumi_file_inspect_pack.file-inspect"
    ): "authority-ref:file.inspect.default",
}


def _resolved():
    catalog = BundledCatalog.load(BUNDLE)
    approved = {str(item["pack"]["artifact_digest"]) for item in catalog.packs.values()}
    return resolve_default_profile(
        catalog,
        "defaults",
        approved_artifact_digests=approved,
        authority_snapshot_digest=SNAPSHOT,
        authority_bindings=BINDINGS,
        security_epoch=1,
    )


def test_resolved_plan_has_exact_profile_and_lock_digests() -> None:
    resolved = _resolved()
    assert resolved.profile["state"] == "resolved"
    assert resolved.lock["profile_revision"] == canonical_digest(resolved.profile)
    assert resolved.lock["plan_digest"] == resolved.plan["plan_digest"]


def test_resolved_plan_has_one_binding_per_selected_function() -> None:
    resolved = _resolved()
    assert len(resolved.plan["bindings"]) == 2
    assert {
        item["function_principal"]["function_id"]
        for item in resolved.plan["bindings"]
    } == {"defaultspack.conversation", "rumi_file_inspect_pack.file-inspect.service"}


def test_resolved_plan_binds_exact_authority_references() -> None:
    resolved = _resolved()
    assert set(resolved.profile["authority_references"]) == set(BINDINGS.values())
    assert {
        edge["authority_reference"] for edge in resolved.profile["requested_edges"]
    } == set(BINDINGS.values())


def test_profile_resolver_denies_missing_authority_reference() -> None:
    assert_profile_resolver_requires_authority_snapshot()


def test_profile_and_lock_are_immutable_snapshots() -> None:
    resolved = _resolved()
    assert resolved.profile["profile_authority_snapshot_digest"] == SNAPSHOT
    assert resolved.lock["security_epoch"] == 1
