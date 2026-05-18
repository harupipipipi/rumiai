from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch

from core_runtime.profile_workspace import ProfileWorkspaceManager
from core_runtime.startup_profiles import StartupProfileManager

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_startup_profiles import _FakeActiveEcosystem, _discover_locations, _startup_graph, _write_pack


def _manager(tmp_path: Path, eco_root: Path) -> tuple[StartupProfileManager, list]:
    _write_pack(
        eco_root,
        "defaultspack",
        identity="rumi:ecosystem/defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(
        storage_path=tmp_path / "user_data" / "settings" / "startup_profiles.json",
        profile_workspace_manager=ProfileWorkspaceManager(tmp_path / "user_data"),
    )
    return manager, locations


def test_startup_profile_launch_initializes_workspace(tmp_path: Path):
    manager, locations = _manager(tmp_path, tmp_path / "ecosystem")
    active = _FakeActiveEcosystem()

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        with patch("backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager", return_value=active):
            with patch("core_runtime.api.control_panel_handlers.request_kernel_restart"):
                created = manager.create_profile({"profile_id": "p1", "base_pack": "defaultspack", "name": "Test"})
                response = manager.launch_profile(created["profile"]["profile_id"])

    assert response["launched"] is True
    assert Path(response["profile_workspace"]["database_path"]) == tmp_path / "user_data" / "profiles" / "p1" / "database" / "rumi.sqlite"
    assert (tmp_path / "user_data" / "profiles" / "p1" / "profile.yaml").is_file()
    assert active.metadata["startup_profile_workspace"]["profile_id"] == "p1"
    assert Path(active.metadata["startup_profile_database_path"]) == tmp_path / "user_data" / "profiles" / "p1" / "database" / "rumi.sqlite"


def test_list_profiles_payload_includes_workspace_paths(tmp_path: Path):
    manager, locations = _manager(tmp_path, tmp_path / "ecosystem")
    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "p1", "base_pack": "defaultspack"})
        payload = manager.list_profiles_payload()

    profile = payload["profiles"][0]
    assert profile["profile_workspace"]["profile_id"] == "p1"
    assert Path(profile["profile_workspace"]["user_data_dir"]) == tmp_path / "user_data" / "profiles" / "p1" / "user_data"
