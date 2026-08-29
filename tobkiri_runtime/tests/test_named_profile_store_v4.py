from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core_runtime.active_profile_store_v4 import (
    ActiveProfileStore,
    ActiveProfileStoreConflict,
    ActiveProfileStoreIntegrityError,
)
from core_runtime.authority.v4 import AuthorityStore
from core_runtime.bootstrap.profile_capture import (
    activation_audit_receipt,
    capture_active_profile,
    capture_default_profile,
    capture_profile,
    host_profile_catalog,
    prepare_default_profile_confirmation,
    prepare_profile_confirmation,
    runtime_user_data_root,
)
from core_runtime.profile_definition_store_v4 import (
    ProfileDefinitionStore,
    ProfileDefinitionStoreError,
)
from core_runtime.runtime_surface_v4 import (
    RuntimeSurfaceError,
    RuntimeSurfaceErrorCode,
    RuntimeSurfaceService,
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


@pytest.mark.parametrize(
    ("case", "snapshot_path"),
    (
        (
            "cross-profile",
            "workspaces/profile-b/activation/activations/profile-a-path.json",
        ),
        (
            "invalid-filename",
            "workspaces/profile-a/activation/activations/not-the-activation.json",
        ),
    ),
)
def test_active_pointer_rejects_unbound_snapshot_path_on_commit(
    tmp_path: Path,
    case: str,
    snapshot_path: str,
) -> None:
    """Commit cannot point Profile A at another workspace or activation file."""

    root = tmp_path / case
    store = ActiveProfileStore(root)
    activation, snapshot, _canonical_path = _write_activation(
        root,
        "profile-a",
        "path",
    )
    path = root / snapshot_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(snapshot) + b"\n")

    with pytest.raises(ActiveProfileStoreIntegrityError, match="snapshot path"):
        store.commit_activation(
            activation,
            activation_snapshot=snapshot,
            activation_snapshot_path=snapshot_path,
        )
    assert store.load() is None


@pytest.mark.parametrize(
    ("case", "snapshot_path"),
    (
        (
            "cross-profile",
            "workspaces/profile-b/activation/activations/profile-a-reload.json",
        ),
        (
            "invalid-filename",
            "workspaces/profile-a/activation/activations/not-the-activation.json",
        ),
    ),
)
def test_active_pointer_rejects_unbound_snapshot_path_on_reload(
    tmp_path: Path,
    case: str,
    snapshot_path: str,
) -> None:
    """Reload cannot follow a persisted pointer outside its bound activation."""

    root = tmp_path / case
    store = ActiveProfileStore(root)
    activation, snapshot, canonical_path = _write_activation(
        root,
        "profile-a",
        "reload",
    )
    store.commit_activation(
        activation,
        activation_snapshot=snapshot,
        activation_snapshot_path=canonical_path,
    )

    path = root / snapshot_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(snapshot) + b"\n")
    pointer = dict(store.load().to_dict())
    pointer["activation_snapshot_path"] = snapshot_path
    pointer["pointer_digest"] = canonical_digest(
        {key: value for key, value in pointer.items() if key != "pointer_digest"}
    )
    store.path.write_bytes(canonical_json(pointer) + b"\n")

    with pytest.raises(ActiveProfileStoreIntegrityError, match="snapshot path"):
        store.load(verify_snapshot=False)
    with pytest.raises(ActiveProfileStoreIntegrityError, match="snapshot path"):
        store.require(verify_snapshot=True)


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
    assert store.legacy_state()["source_document"] == legacy


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


def test_legacy_profile_map_key_and_extra_fields_are_lossless(tmp_path: Path) -> None:
    """Preserve map-key identity and unknown legacy fields during migration."""

    store = ProfileDefinitionStore(tmp_path)
    legacy = {
        "version": 4,
        "active_profile_id": "map-key-a",
        "profiles": {
            "map-key-a": {
                "name": "Mapped A",
                "created_at": 7,
                "unknown_runtime_field": {"nested": [1, 2, 3]},
            }
        },
        "legacy_selection": {"last_view": "conversation"},
    }

    receipt = store.import_legacy_collection(legacy, copy_workspaces=False)

    assert receipt.legacy_id_map == {"map-key-a": "map-key-a"}
    imported = store.get_profile("map-key-a")
    assert imported is not None
    assert imported.profile["unknown_runtime_field"] == {"nested": [1, 2, 3]}
    assert store.legacy_state()["source_document"] == legacy


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


def test_real_disk_named_profiles_keep_execution_and_workspace_state_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise Defaults -> A -> B -> restart -> A on real v4 persistence."""

    monkeypatch.setenv("TOBKIRI_USER_DATA", str(tmp_path / "user-data"))
    user_data = runtime_user_data_root()
    host_profile_catalog()
    definitions = ProfileDefinitionStore(user_data)
    defaults = definitions.get_profile("defaults")
    assert defaults is not None
    profile_a = definitions.duplicate_profile(
        "defaults",
        new_profile_id="profile-a",
        display_name="Profile A",
        expected_profile_revision=defaults.profile_revision,
    )
    profile_b = definitions.duplicate_profile(
        "defaults",
        new_profile_id="profile-b",
        display_name="Profile B",
        expected_profile_revision=defaults.profile_revision,
    )

    def assert_active(expected_profile_id: str):
        active = capture_active_profile()
        pointer = ActiveProfileStore(user_data).require(verify_snapshot=True)
        assert active.resolved.profile["profile_id"] == expected_profile_id
        assert pointer.profile_id == expected_profile_id
        assert pointer.profile_revision == active.resolved.plan["profile_revision"]
        assert pointer.plan_digest == active.resolved.plan["plan_digest"]
        assert pointer.lock_digest == active.resolved.lock["lock_digest"]
        assert pointer.activation_id == active.activation["activation_id"]
        receipt = activation_audit_receipt(active)
        assert receipt["state"] == "committed"
        with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
            reservation = authority.active_activation_reservation(
                active.activation["activation_id"]
            )
        assert reservation is not None
        assert reservation["state"] == "active"
        assert reservation["plan_digest"] == active.activation["plan_digest"]
        assert reservation["fencing_token"] == active.activation["fencing_token"]
        return active

    def write_profile_state(profile_id: str) -> None:
        workspace = user_data / "workspaces" / profile_id
        state = {
            "packs/closure.json": f"pack-state:{profile_id}",
            "conversation/history.json": f"conversation:{profile_id}",
            "credentials/provider.ref": f"credential-ref:{profile_id}",
            "handoff/shell.json": f"shell-handoff:{profile_id}",
        }
        for relative, value in state.items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")

    defaults_active = capture_default_profile(
        confirmation=prepare_default_profile_confirmation()
    )
    assert_active("defaults")
    write_profile_state("defaults")

    active_a = capture_profile(
        "profile-a",
        confirmation=prepare_profile_confirmation("profile-a"),
    )
    assert_active("profile-a")
    write_profile_state("profile-a")

    active_b = capture_profile(
        "profile-b",
        confirmation=prepare_profile_confirmation("profile-b"),
    )
    assert_active("profile-b")
    write_profile_state("profile-b")

    restarted = ActiveProfileStore(user_data).require(verify_snapshot=True)
    assert restarted.profile_id == "profile-b"
    assert_active("profile-b")

    browsing_surface = RuntimeSurfaceService(
        snapshot_loader=capture_active_profile,
        catalog_loader=host_profile_catalog,
    )
    browsing_profile = browsing_surface.read_profile(
        selected_profile_id="profile-a"
    )
    assert browsing_profile["data"]["selection"] == {
        "state": "browsing",
        "selected_profile_id": "profile-a",
        "execution_profile_id": "profile-b",
        "execution_profile_revision": active_b.resolved.plan["profile_revision"],
        "execution_activation_id": active_b.activation["activation_id"],
        "execution_plan_digest": active_b.resolved.plan["plan_digest"],
    }
    assert browsing_profile["data"]["resolved_plan"] is None
    assert browsing_profile["data"]["activation_record"] is None
    with pytest.raises(RuntimeSurfaceError) as stale:
        browsing_surface.read_profile(
            selected_profile_id="profile-a",
            expected_profile_revision="sha256:" + "0" * 64,
            expected_plan_digest=active_b.resolved.plan["plan_digest"],
        )
    assert stale.value.code is RuntimeSurfaceErrorCode.STALE_REVISION
    browsing_operations = browsing_surface.read_advanced(
        "operations",
        selected_profile_id="profile-a",
    )["data"]["operations"]
    assert browsing_operations
    assert all(
        item["invokable"] is False
        and item["invocation_reason"] == "browsing_only"
        for item in browsing_operations
    )
    browsing_settings = browsing_surface.read_settings(
        selected_profile_id="profile-a"
    )
    assert (
        browsing_settings["data"]["runtime_profile_settings"]["state"]
        == "browsing_only"
    )
    browsing_surface.close()
    assert_active("profile-b")

    active_a_again = capture_profile(
        "profile-a",
        confirmation=prepare_profile_confirmation("profile-a"),
    )
    assert active_a_again.resolved.profile["profile_id"] == "profile-a"
    assert_active("profile-a")

    assert len(
        {
            defaults_active.resolved.plan["plan_digest"],
            active_a.resolved.plan["plan_digest"],
            active_b.resolved.plan["plan_digest"],
        }
    ) == 3
    assert ActiveProfileStore(user_data).path == user_data / "profiles" / "active.json"
    assert ActiveProfileStore(user_data).path.parent not in {
        user_data / "workspaces" / profile_id
        for profile_id in ("defaults", "profile-a", "profile-b")
    }
    for profile_id in ("defaults", "profile-a", "profile-b"):
        workspace = user_data / "workspaces" / profile_id
        for relative in (
            "packs/closure.json",
            "conversation/history.json",
            "credentials/provider.ref",
            "handoff/shell.json",
        ):
            assert (workspace / relative).read_text(encoding="utf-8").endswith(
                profile_id
            )
