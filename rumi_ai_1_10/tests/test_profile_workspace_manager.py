from __future__ import annotations

from pathlib import Path

import pytest

from core_runtime.profile_workspace import ProfileWorkspaceManager


def _profile(profile_id: str = "default-profile") -> dict:
    return {
        "version": 3,
        "profile_id": profile_id,
        "name": "Default Profile",
        "base_pack": "defaultspack",
        "graph_id": "defaultspack.startup",
        "packs": ["defaultspack"],
        "node_overrides": {},
        "surfaces": {"preferred": "browser", "enabled": ["browser"]},
    }


def test_initialize_profile_workspace_creates_expected_tree(tmp_path: Path):
    manager = ProfileWorkspaceManager(tmp_path)
    paths = manager.initialize_profile_workspace(_profile())

    assert paths.root == tmp_path / "profiles" / "default-profile"
    assert paths.profile_file.is_file()
    assert paths.user_data_dir.is_dir()
    assert paths.database_dir.is_dir()
    assert paths.database_path.is_file()
    assert (paths.startup_dir / "launch.yaml").is_file()
    assert (paths.startup_dir / "surface.yaml").is_file()
    assert paths.flows_dir.is_dir()
    assert paths.prompts_dir.is_dir()
    assert paths.snapshots_dir.is_dir()
    assert (paths.permissions_dir / "grants.yaml").is_file()
    assert (paths.permissions_dir / "tool_policy.yaml").is_file()
    assert (paths.permissions_dir / "approvals.yaml").is_file()
    assert (paths.audit_dir / "events.jsonl").is_file()


@pytest.mark.parametrize("profile_id", ["", "../x", "x/../y", "x\\y", "abc..def"])
def test_profile_id_rejects_path_traversal(tmp_path: Path, profile_id: str):
    manager = ProfileWorkspaceManager(tmp_path)
    with pytest.raises(ValueError):
        manager.paths_for_profile(profile_id)


def test_profile_yaml_roundtrip(tmp_path: Path):
    manager = ProfileWorkspaceManager(tmp_path)
    profile = _profile("roundtrip")
    manager.initialize_profile_workspace(profile)
    profile["name"] = "Updated"
    manager.save_profile_yaml("roundtrip", profile)

    loaded = manager.load_profile_yaml("roundtrip")
    assert loaded["profile_id"] == "roundtrip"
    assert loaded["name"] == "Updated"


def test_profile_database_path_is_profile_scoped(tmp_path: Path):
    manager = ProfileWorkspaceManager(tmp_path)
    assert manager.profile_database_path("p1") == tmp_path / "profiles" / "p1" / "database" / "rumi.sqlite"


def test_profile_user_data_dir_is_profile_scoped(tmp_path: Path):
    manager = ProfileWorkspaceManager(tmp_path)
    assert manager.profile_user_data_dir("p1") == tmp_path / "profiles" / "p1" / "user_data"
