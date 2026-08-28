from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core_runtime.active_profile_store_v4 import (
    ActiveProfileStore,
    ActiveProfileStoreConflict,
    ActiveProfileStoreIntegrityError,
)
from core_runtime.profile_definition_store_v4 import (
    ProfileDefinitionStore,
    ProfileDefinitionStoreError,
)
from tobkiri_protocol.canonical import canonical_digest, canonical_json


def _definition(profile_id: str, name: str) -> dict[str, object]:
    return {
        "profile_api_version": "io.tobkiri.profile.v5",
        "profile_id": profile_id,
        "display_name": name,
        "mode": "interactive",
        "packs": [{"pack_id": "example-pack", "artifact_digest": None}],
    }


def _write_activation(
    root: Path,
    profile_id: str,
    marker: str,
) -> tuple[dict[str, object], dict[str, object], str]:
    profile_revision = canonical_digest({"profile": profile_id, "marker": marker})
    plan_digest = canonical_digest({"plan": profile_id, "marker": marker})
    lock_digest = canonical_digest({"lock": profile_id, "marker": marker})
    activation_id = f"activation:{profile_id}-{marker}"
    snapshot = {
        "profile": {"profile_id": profile_id},
        "lock": {"lock_digest": lock_digest},
        "plan": {
            "profile_revision": profile_revision,
            "plan_digest": plan_digest,
        },
        "activation": {
            "profile_id": profile_id,
            "profile_revision": profile_revision,
            "activation_id": activation_id,
            "plan_digest": plan_digest,
            "lock_digest": lock_digest,
            "state": "active",
        },
    }
    relative = (
        Path("workspaces")
        / profile_id
        / "activation"
        / "activations"
        / f"{activation_id.removeprefix('activation:')}.json"
    )
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(snapshot) + b"\n")
    return dict(snapshot["activation"]), snapshot, relative.as_posix()


def test_named_profile_crud_creates_immutable_successors_and_tombstones(
    tmp_path: Path,
) -> None:
    store = ProfileDefinitionStore(tmp_path, clock=lambda: 100)
    defaults = store.bootstrap_defaults(_definition("defaults", "Defaults"))
    profile_a = store.create_profile(_definition("profile-a", "Profile A"))
    updated = store.update_profile(
        "profile-a",
        patch={"display_name": "Profile A edited"},
        expected_profile_revision=profile_a.profile_revision,
    )
    duplicate = store.duplicate_profile(
        "profile-a",
        new_profile_id="profile-b",
        expected_profile_revision=updated.profile_revision,
    )
    deleted = store.delete_profile(
        "profile-b",
        expected_profile_revision=duplicate.profile_revision,
    )

    assert defaults.profile_id == "defaults"
    assert updated.parent_revision == profile_a.profile_revision
    assert updated.profile_revision != profile_a.profile_revision
    assert duplicate.profile_id == "profile-b"
    assert deleted.tombstone is True
    assert store.get_profile("profile-b") is None
    assert store.get_profile("profile-b", include_tombstone=True) == deleted
    revisions = store.snapshot()["profiles"][1]["revisions"]
    assert [item["profile_revision"] for item in revisions] == [
        profile_a.profile_revision,
        updated.profile_revision,
    ]


def test_active_pointer_switch_restart_cas_and_workspace_isolation(
    tmp_path: Path,
) -> None:
    pointer_store = ActiveProfileStore(tmp_path, clock=lambda: 200)
    committed = None
    snapshots: dict[str, tuple[dict[str, object], dict[str, object], str]] = {}
    for profile_id in ("defaults", "profile-a", "profile-b", "profile-a"):
        marker = f"run-{len(snapshots)}-{profile_id}"
        activation, snapshot, relative = _write_activation(
            tmp_path,
            profile_id,
            marker,
        )
        snapshots[profile_id] = (activation, snapshot, relative)
        committed = pointer_store.commit_activation(
            activation,
            activation_snapshot=snapshot,
            activation_snapshot_path=relative,
            expected=committed,
        )
        workspace = tmp_path / "workspaces" / profile_id
        for relative_state in (
            "packs/closure.json",
            "conversation/history.json",
            "settings/runtime.json",
            "credentials/provider.ref",
            "handoff/shell.json",
        ):
            state_path = workspace / relative_state
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(marker, encoding="utf-8")

    restarted = ActiveProfileStore(tmp_path).require(verify_snapshot=True)
    assert restarted.profile_id == "profile-a"
    assert restarted.generation == 4
    for profile_id in ("defaults", "profile-a", "profile-b"):
        expected_marker = snapshots[profile_id][0]["activation_id"].removeprefix(
            f"activation:{profile_id}-"
        )
        workspace = tmp_path / "workspaces" / profile_id
        values = {
            (workspace / relative_state).read_text(encoding="utf-8")
            for relative_state in (
                "packs/closure.json",
                "conversation/history.json",
                "settings/runtime.json",
                "credentials/provider.ref",
                "handoff/shell.json",
            )
        }
        assert values == {expected_marker}

    defaults_workspace = tmp_path / "workspaces" / "defaults"
    shutil.rmtree(defaults_workspace)
    assert ActiveProfileStore(tmp_path).require().profile_id == "profile-a"

    activation_b, snapshot_b, relative_b = snapshots["profile-b"]
    with pytest.raises(ActiveProfileStoreConflict):
        pointer_store.commit_activation(
            activation_b,
            activation_snapshot=snapshot_b,
            activation_snapshot_path=relative_b,
            expected=None,
        )


def test_active_pointer_rejects_memory_disk_mismatch(tmp_path: Path) -> None:
    store = ActiveProfileStore(tmp_path)
    activation, snapshot, relative = _write_activation(
        tmp_path,
        "profile-a",
        "run-tamper",
    )
    tampered = {**snapshot, "profile": {"profile_id": "profile-b"}}
    with pytest.raises(ActiveProfileStoreIntegrityError):
        store.commit_activation(
            activation,
            activation_snapshot=tampered,
            activation_snapshot_path=relative,
        )


def test_legacy_collection_preserves_order_selection_timestamps_and_workspaces(
    tmp_path: Path,
) -> None:
    store = ProfileDefinitionStore(tmp_path, clock=lambda: 999)
    store.bootstrap_defaults(_definition("defaults", "Defaults"))
    legacy_root = tmp_path / "legacy"
    for profile_id in ("Work A", "work-b"):
        workspace = legacy_root / "profiles" / profile_id
        workspace.mkdir(parents=True)
        (workspace / "state.db").write_text(profile_id, encoding="utf-8")
    legacy = {
        "version": 3,
        "active_profile_id": "work-b",
        "last_launched_profile_id": "Work A",
        "profiles": [
            {
                "profile_id": "Work A",
                "name": "Work A",
                "created_at": 10,
                "updated_at": 11,
                "graph_ports": {"input": "node-a"},
            },
            {
                "profile_id": "work-b",
                "name": "Work B",
                "created_at": 20,
                "updated_at": 21,
                "node_overrides": {"tool": "node-b"},
            },
        ],
    }

    receipt = store.import_legacy_collection(
        legacy,
        legacy_workspace_root=legacy_root,
    )
    profiles = store.list_profiles()
    assert [item.profile_id for item in profiles] == ["defaults", "work-a", "work-b"]
    assert [item.order for item in profiles] == [0, 1, 2]
    assert (profiles[1].created_at, profiles[1].updated_at) == (10, 11)
    assert profiles[1].profile["graph_ports"] == {"input": "node-a"}
    assert profiles[2].profile["node_overrides"] == {"tool": "node-b"}
    assert receipt.active_profile_id == "work-b"
    assert receipt.last_launched_profile_id == "work-a"
    assert (tmp_path / "workspaces" / "work-a" / "state.db").read_text() == "Work A"
    assert (tmp_path / "workspaces" / "work-b" / "state.db").read_text() == "work-b"


def test_legacy_defaults_id_does_not_replace_bootstrap_template(
    tmp_path: Path,
) -> None:
    """Preserve a legacy Defaults Profile under a non-reserved ID."""

    store = ProfileDefinitionStore(tmp_path)
    receipt = store.import_legacy_collection(
        {
            "profiles": [
                {"profile_id": "defaults", "display_name": "My old Defaults"}
            ],
            "active_profile_id": "defaults",
        },
        copy_workspaces=False,
    )

    assert receipt.legacy_id_map == {"defaults": "defaults-2"}
    assert receipt.active_profile_id == "defaults-2"
    assert store.get_profile("defaults") is None
    assert store.get_profile("defaults-2") is not None


def test_legacy_workspace_failure_rolls_back_registry(tmp_path: Path) -> None:
    store = ProfileDefinitionStore(tmp_path)
    legacy_root = tmp_path / "legacy"
    workspace = legacy_root / "profiles" / "profile-a"
    workspace.mkdir(parents=True)
    (workspace / "bad-link").symlink_to(tmp_path / "outside")
    legacy = {"profiles": [{"profile_id": "profile-a", "name": "A"}]}

    with pytest.raises(ProfileDefinitionStoreError):
        store.import_legacy_collection(
            legacy,
            legacy_workspace_root=legacy_root,
        )
    assert store.list_profiles() == ()
    assert not store.exists()
